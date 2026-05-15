#!/usr/bin/env python3
"""
new-api 监控脚本 (飞书版)
每5分钟通过 cron 执行，异常时推送飞书消息

用法:
  ./monitor_feishu.py           # 单次检查
  ./monitor_feishu.py --cron    # cron 模式 (静默, 仅异常时通知)
  ./monitor_feishu.py --test    # 测试飞书通知链路

配置来源 (优先级: 环境变量 > .env 文件 > 默认值):
  FEISHU_APP_ID, FEISHU_APP_SECRET  — 飞书自建应用凭证
  FEISHU_RECEIVE_ID                  — 消息接收者 (chat_id 或 open_id)
  FEISHU_RECEIVE_TYPE                — chat_id 或 open_id
  QUOTA_THRESHOLD                    — 额度告警阈值 (默认 0=不检查)
  MONITOR_CHANNELS                   — 重点渠道 (预留)

飞书权限: im:message:send
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
STATE_FILE = Path("/tmp/newapi-feishu-monitor.state")
TOKEN_FILE = Path("/tmp/newapi-feishu-token.json")
ALERT_LOG = Path("/tmp/newapi-feishu-alert.log")

# 告警冷却 (秒)
COOLDOWN_DOWN = 1200     # 服务不可达: 20分钟
COOLDOWN_ERROR = 900     # 错误日志:   15分钟
COOLDOWN_QUOTA = 1800    # 额度异常:   30分钟

# 北京时间
CST = timezone(timedelta(hours=8))


def _read_env(key: str, default: str = "") -> str:
    """从环境变量或 .env 文件读取配置"""
    val = os.environ.get(key, "")
    if val:
        return val
    env_file = SCRIPT_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                return val
    return default


FEISHU_APP_ID = _read_env("FEISHU_APP_ID", "cli_a95ee4e7f1ba5bb4")
FEISHU_APP_SECRET = _read_env("FEISHU_APP_SECRET", "mv1uRalnsXqfKDsskIFcTdVaANMV01Ot")
FEISHU_RECEIVE_ID = _read_env("FEISHU_RECEIVE_ID", "")
FEISHU_RECEIVE_TYPE = _read_env("FEISHU_RECEIVE_TYPE", "chat_id")
API_URL = _read_env("new_api_url", "https://aikey.aixifs.com").rstrip("/")
ADMIN_KEY = _read_env("new_admin_key", "")
API_USER = _read_env("New-Api-User", "1")
QUOTA_THRESHOLD = int(_read_env("QUOTA_THRESHOLD", "0"))
MONITOR_CHANNELS = _read_env("MONITOR_CHANNELS", "")
CHECK_INTERVAL = 300  # 秒


# ============================================================
# 状态文件
# ============================================================
def read_state() -> dict:
    if STATE_FILE.exists():
        try:
            state = {}
            for line in STATE_FILE.read_text().splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    state[k] = v
            return state
        except OSError:
            pass
    return {}


def write_state(state: dict):
    STATE_FILE.write_text("\n".join(f"{k}={v}" for k, v in state.items()) + "\n")


def state_get(key: str) -> str:
    return read_state().get(key, "")


def state_set(key: str, value: str):
    s = read_state()
    s[key] = value
    write_state(s)


# ============================================================
# 本地告警日志
# ============================================================
def alert_log(title: str, content: str):
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    with open(ALERT_LOG, "a") as f:
        f.write(f"[{ts}] {title}\n{content}\n---\n")


# ============================================================
# 飞书 API
# ============================================================
def feishu_get_token() -> str | None:
    """获取飞书 tenant_access_token，带缓存"""
    now_ts = int(time.time())
    if TOKEN_FILE.exists():
        try:
            cache = json.loads(TOKEN_FILE.read_text())
            if now_ts - cache.get("ts", 0) < 7100:
                return cache.get("token", "")
        except (json.JSONDecodeError, OSError):
            pass

    # 请求新 token
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("code") != 0:
            print(f"[错误] 获取飞书 token 失败: {data}", file=sys.stderr)
            return None
        token = data["tenant_access_token"]
        TOKEN_FILE.write_text(json.dumps({"token": token, "ts": now_ts}))
        return token
    except Exception as e:
        print(f"[错误] 获取飞书 token 异常: {e}", file=sys.stderr)
        return None


def feishu_clear_token_cache():
    """清除 token 缓存"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()


def feishu_send(title: str, content: str) -> bool:
    """发送飞书消息，返回是否成功"""
    if not FEISHU_RECEIVE_ID:
        return False

    token = feishu_get_token()
    if not token:
        return False

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "new-api 监控告警"},
            "template": "red",
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": content}},
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"{datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} | 目标: {API_URL}",
                    }
                ],
            },
        ],
    }

    body = {
        "receive_id": FEISHU_RECEIVE_ID,
        "msg_type": "interactive",
        "content": json.dumps(card, ensure_ascii=False),
    }

    req = urllib.request.Request(
        f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={FEISHU_RECEIVE_TYPE}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        code = data.get("code", -1)
        if code == 0:
            return True

        # token 失效 → 清除缓存，重试一次
        if code == 99991663:
            feishu_clear_token_cache()
            token2 = feishu_get_token()
            if token2 and token2 != token:
                req2 = urllib.request.Request(
                    f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={FEISHU_RECEIVE_TYPE}",
                    data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {token2}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                )
                try:
                    resp2 = urllib.request.urlopen(req2, timeout=15)
                    data2 = json.loads(resp2.read())
                    if data2.get("code") == 0:
                        return True
                    print(f"[通知失败] 重试后飞书返回: {data2}", file=sys.stderr)
                except Exception as e:
                    print(f"[通知失败] 重试异常: {e}", file=sys.stderr)
                return False
            return False

        print(f"[通知失败] 飞书返回: {data}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[通知失败] 请求异常: {e}", file=sys.stderr)
        return False


# ============================================================
# 告警去重
# ============================================================
def should_send(alert_key: str, cooldown: int) -> bool:
    """检查告警是否在冷却期外。调用即视为"准备发送"，不预先更新状态。"""
    last_sent = state_get(f"last_alert_{alert_key}")
    now = int(time.time())
    if last_sent and (now - int(last_sent)) < cooldown:
        return False
    return True


def mark_sent(alert_key: str):
    """发送成功后更新冷却时间戳"""
    state_set(f"last_alert_{alert_key}", str(int(time.time())))


# ============================================================
# new-api API 调用
# ============================================================
def api_call(path: str) -> tuple[int, dict]:
    """调用 new-api，返回 (http_code, body_dict)"""
    url = f"{API_URL}/api{path}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", ADMIN_KEY)
    req.add_header("New-Api-User", API_USER)
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read())
        return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


# ============================================================
# 检查项
# ============================================================
def check_service_alive() -> str | None:
    """检查服务存活，返回告警内容或 None"""
    url = f"{API_URL}/api/status"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=15)
        if resp.status != 200:
            return f"HTTP 状态码: **{resp.status}**\n地址: {url}"
        body = json.loads(resp.read())
        if not body.get("success"):
            return f"服务返回异常: {body.get('message', 'unknown')}"
        return None
    except urllib.error.HTTPError as e:
        return f"HTTP 状态码: **{e.code}**\n地址: {url}"
    except Exception as e:
        return f"服务不可达: {e}\n地址: {url}"


def check_error_logs() -> str | None:
    """检查错误日志，返回告警内容或 None"""
    now_ts = int(time.time())
    last_ts_str = state_get("last_ts")
    start_ts = int(last_ts_str) if last_ts_str else (now_ts - CHECK_INTERVAL)
    end_ts = now_ts

    code, body = api_call(
        f"/log/?type=5&start_timestamp={start_ts}&end_timestamp={end_ts}&page=0&page_size=200"
    )
    if code != 200:
        alert_log("错误日志API异常", f"HTTP: {code}")
        if should_send("error", COOLDOWN_ERROR):
            sent = feishu_send("错误日志 API 异常",
                               f"**HTTP 状态码**: {code}\n**地址**: /api/log?type=5")
            if sent:
                mark_sent("error")
        return None

    if not body.get("success"):
        return None

    data = body.get("data", {})
    total = data.get("total", 0)
    if total == 0:
        state_set("last_ts", str(end_ts))
        return None

    items = data.get("items", [])

    # 构建消息
    t1 = datetime.fromtimestamp(start_ts, CST).strftime("%H:%M:%S")
    t2 = datetime.fromtimestamp(end_ts, CST).strftime("%H:%M:%S")
    content = f"**时间**: {t1} ~ {t2}  |  **共 {total} 条**\n\n"

    # 错误详情 (前8条)
    detail_lines = []
    for item in items[:8]:
        ch = item.get("channel_name", "system")
        model = item.get("model_name", "")
        text = (item.get("content", "") or "")[:80]
        detail_lines.append(f"- [{ch}] {model} → {text}")
    if detail_lines:
        content += "**错误详情:**\n" + "\n".join(detail_lines) + "\n"

    # 按渠道归类
    channel_map: dict[str, dict] = {}
    for item in items:
        ch = item.get("channel_name", "")
        if not ch or item.get("channel", 0) == 0:
            continue
        if ch not in channel_map:
            channel_map[ch] = {"count": 0, "models": set()}
        channel_map[ch]["count"] += 1
        model = item.get("model_name", "")
        if model:
            channel_map[ch]["models"].add(model)

    if channel_map:
        content += "\n**按渠道:**\n"
        for ch_name, info in sorted(channel_map.items(), key=lambda x: -x[1]["count"]):
            models = ", ".join(sorted(info["models"]))
            content += f"> **{ch_name}**: {info['count']}次 | {models}\n"

    state_set("last_ts", str(end_ts))

    # 始终写本地日志
    alert_log(f"发现 {total} 条错误", content)

    # 检查冷却期
    if not should_send("error", COOLDOWN_ERROR):
        return None

    # 尝试发送飞书
    sent = feishu_send(f"发现 {total} 条错误", content)
    if sent:
        mark_sent("error")
    return None


def check_quota_anomaly() -> str | None:
    """检查额度异常消耗，返回告警内容或 None"""
    if QUOTA_THRESHOLD <= 0:
        return None

    now_ts = int(time.time())
    start_ts = now_ts - CHECK_INTERVAL
    end_ts = now_ts

    code, body = api_call(
        f"/log/stat?type=2&start_timestamp={start_ts}&end_timestamp={end_ts}"
    )
    if code != 200:
        alert_log("额度统计API异常", f"HTTP: {code}")
        return None

    if not body.get("success"):
        return None

    data = body.get("data", {})
    quota = data.get("quota", 0)
    rpm = data.get("rpm", 0)
    tpm = data.get("tpm", 0)

    prev_quota_str = state_get("prev_quota")
    prev_quota = int(prev_quota_str) if prev_quota_str else 0
    state_set("prev_quota", str(quota))

    quota_diff = quota - prev_quota
    if quota_diff > QUOTA_THRESHOLD:
        content = (
            f"**5分钟内消耗**: {quota_diff} (阈值: {QUOTA_THRESHOLD})\n"
            f"**RPM**: {rpm} | **TPM**: {tpm}"
        )
        alert_log("额度消耗异常", content)
        if should_send("quota", COOLDOWN_QUOTA):
            sent = feishu_send("额度消耗异常", content)
            if sent:
                mark_sent("quota")
        return content
    return None


# ============================================================
# 主流程
# ============================================================
def main():
    cron_mode = "--cron" in sys.argv

    if "--test" in sys.argv:
        content = (
            f"**new-api 监控测试**\n"
            f"> 飞书通知链路正常\n"
            f"> 目标: {API_URL}\n"
            f"> 时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        ok = feishu_send("测试消息", content)
        if ok:
            print("测试消息已发送")
        else:
            print("测试消息发送失败，请检查飞书配置", file=sys.stderr)
            sys.exit(1)
        return

    if not cron_mode:
        print(f"======== {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} ========")

    errors = 0

    # 检查 1: 服务存活
    if not cron_mode:
        print("[检查1] 服务存活...")
    alert = check_service_alive()
    if alert:
        alert_log("服务不可达", alert)
        if should_send("down", COOLDOWN_DOWN):
            sent = feishu_send("服务不可达", f"**{alert}**")
            if sent:
                mark_sent("down")
        errors += 1
        if not cron_mode:
            print(f"  异常: {alert}")
    else:
        if not cron_mode:
            print("  OK")

    # 服务正常才继续后续检查
    if errors == 0:
        if not cron_mode:
            print("[检查2] 错误日志+渠道分析...")
        check_error_logs()

        if not cron_mode:
            print("[检查3] 额度消耗...")
        result = check_quota_anomaly()
        if result:
            errors += 1
            if not cron_mode:
                print(f"  异常: {result}")
        else:
            if not cron_mode:
                if QUOTA_THRESHOLD <= 0:
                    print("  未设置阈值, 跳过")
                else:
                    print("  OK")

    if not cron_mode:
        if errors == 0:
            print("全部检查通过")
        else:
            print(f"发现 {errors} 项异常")
        print()


if __name__ == "__main__":
    main()
