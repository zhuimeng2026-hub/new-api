#!/usr/bin/env python3
"""
new-api 监控守护进程
通过企业微信智能机器人 WebSocket 长连接推送告警，无需固定 IP

用法:
  python3 monitor_daemon.py              # 前台运行
  python3 monitor_daemon.py --daemon     # 后台运行

首次使用：给机器人发一条消息（私聊或群里@机器人），机器人会记录 chatid，
后续监控告警会自动推送到这些会话。
"""

import asyncio
import json
import os
import sys
import time
import uuid
import signal
from datetime import datetime
from pathlib import Path

import aiohttp
import websockets

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent

# 企业微信智能机器人
BOT_ID = "aibEKsg0ZHQnzCVCvCUrwOU9DCY0JGNzFi5"
BOT_SECRET = "eYoYuALDBOJzaMOsLkfFX6MiEobDjYde30EDTzWYxfk"
WSS_URL = "wss://openws.work.weixin.qq.com"

# 从 .env 读取 new-api 配置
def _read_env(key: str, default: str = "") -> str:
    env_file = SCRIPT_DIR / ".env"
    if not env_file.exists():
        return os.environ.get(key, default)
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return val
    return os.environ.get(key, default)

API_URL = _read_env("new_api_url", "https://aikey.aixifs.com").rstrip("/")
ADMIN_KEY = _read_env("new_admin_key", "")

# 监控参数
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # 检查间隔(秒), 默认5分钟
MONITOR_CHANNELS = os.environ.get("MONITOR_CHANNELS", "")      # 重点渠道, 逗号分隔
QUOTA_THRESHOLD = int(os.environ.get("QUOTA_THRESHOLD", "0"))   # 额度告警阈值

# 状态文件
STATE_DIR = Path(os.environ.get("STATE_DIR", "/tmp"))
CHATIDS_FILE = STATE_DIR / "newapi-monitor-chatids.json"
STATE_FILE = STATE_DIR / "newapi-monitor-state.json"

# ============================================================
# ChatID 管理
# ============================================================
def load_chatids() -> dict:
    """加载已知的 chatid 列表, 格式: {chatid: chat_type}"""
    if CHATIDS_FILE.exists():
        try:
            return json.loads(CHATIDS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}

def save_chatids(chatids: dict):
    CHATIDS_FILE.write_text(json.dumps(chatids, ensure_ascii=False))

def record_chatid(chatid: str, chat_type: int):
    """记录一个新的 chatid"""
    chatids = load_chatids()
    if chatid not in chatids:
        chatids[chatid] = chat_type
        save_chatids(chatids)
        ts = datetime.now().strftime("%H:%M:%S")
        ctype = "群聊" if chat_type == 2 else "单聊"
        print(f"[{ts}] 新会话已记录: {chatid} ({ctype}), 当前共 {len(chatids)} 个会话")

# ============================================================
# 企业微信消息发送
# ============================================================
class WeComBot:
    def __init__(self):
        self.ws = None
        self.req_id_counter = 0
        self._running = True

    def next_req_id(self) -> str:
        self.req_id_counter += 1
        return f"monitor_{self.req_id_counter}_{uuid.uuid4().hex[:8]}"

    async def connect(self):
        """建立 WebSocket 连接"""
        print(f"[{datetime.now():%H:%M:%S}] 正在连接企业微信智能机器人...")
        self.ws = await websockets.connect(WSS_URL, ping_interval=None)
        print(f"[{datetime.now():%H:%M:%S}] WebSocket 已连接")
        return True

    async def subscribe(self):
        """发送订阅并等待响应"""
        req_id = self.next_req_id()
        msg = {"cmd": "aibot_subscribe", "headers": {"req_id": req_id},
               "body": {"bot_id": BOT_ID, "secret": BOT_SECRET}}
        await self.ws.send(json.dumps(msg))
        try:
            resp = await asyncio.wait_for(self.ws.recv(), timeout=10)
            data = json.loads(resp)
            if data.get("errcode") == 0:
                print(f"[{datetime.now():%H:%M:%S}] 订阅成功")
                return True
            print(f"[{datetime.now():%H:%M:%S}] 订阅失败: {resp}")
            return False
        except asyncio.TimeoutError:
            print(f"[{datetime.now():%H:%M:%S}] 订阅超时")
            return False

    async def _send(self, cmd: str, body: dict | None = None):
        """发送命令 (fire-and-forget)"""
        if not self.ws:
            return
        msg = {"cmd": cmd, "headers": {"req_id": self.next_req_id()}}
        if body is not None:
            msg["body"] = body
        try:
            await self.ws.send(json.dumps(msg))
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] 发送失败: {e}")

    async def send_markdown(self, chatid: str, chat_type: int, content: str):
        await self._send("aibot_send_msg", {
            "chatid": chatid, "chat_type": chat_type,
            "msgtype": "markdown", "markdown": {"content": content},
        })

    async def broadcast(self, content: str):
        chatids = load_chatids()
        if not chatids:
            print(f"[{datetime.now():%H:%M:%S}] 没有已知会话, 跳过通知")
            return
        for chatid, chat_type in chatids.items():
            await self.send_markdown(chatid, chat_type, content)
            await asyncio.sleep(0.5)

    async def run_forever(self):
        """主循环: recv + ping heartbeats + message processing"""
        last_ping = time.time()
        try:
            while self._running and self.ws:
                # 使用 asyncio.wait 而不是 asyncio.wait_for, 更健壮
                recv_task = asyncio.create_task(self.ws.recv())
                done, _ = await asyncio.wait([recv_task], timeout=15)
                if recv_task not in done:
                    recv_task.cancel()
                    # 超时, 检查是否需要发心跳
                    now = time.time()
                    if now - last_ping >= 25:
                        await self._send("ping")
                        last_ping = now
                    continue

                raw = recv_task.result()
                data = json.loads(raw)
                cmd = data.get("cmd", "")

                if not cmd and "errcode" in data:
                    continue  # ping 响应

                if cmd == "aibot_msg_callback":
                    body = data.get("body", {})
                    chatid = body.get("chatid", "")
                    chat_type = body.get("chattype", "single")
                    ct = 2 if chat_type == "group" else 1
                    msgtype = body.get("msgtype", "")
                    if chatid:
                        record_chatid(chatid, ct)
                        print(f"[{datetime.now():%H:%M:%S}] 收到消息: chatid={chatid}, type={chat_type}, msgtype={msgtype}")
                        text = ""
                        if msgtype == "text":
                            text = body.get("text", {}).get("content", "")
                        elif msgtype == "mixed":
                            items = body.get("mixed", {}).get("item", [])
                            text = " ".join(i.get("text", {}).get("content", "") for i in items if i.get("msgtype") == "text")
                        if "ping" in text.lower() or "测试" in text:
                            await self.send_markdown(
                                chatid, ct,
                                "pong! 监控助手已就绪\n"
                                f"> 检查间隔: {CHECK_INTERVAL}秒\n"
                                f"> 目标: {API_URL}\n"
                                f"> 已知会话: {len(load_chatids())}个"
                            )
                elif cmd == "aibot_event_callback":
                    print(f"[{datetime.now():%H:%M:%S}] 事件回调: {data.get('body', {})}")
                else:
                    print(f"[{datetime.now():%H:%M:%S}] 其他消息: cmd={cmd}")
        except websockets.ConnectionClosed as e:
            print(f"[{datetime.now():%H:%M:%S}] WebSocket 断开: {e}")
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] 主循环异常: {e}")
        finally:
            self._running = False

    async def close(self):
        self._running = False
        if self.ws:
            await self.ws.close()


# ============================================================
# new-api 监控检查
# ============================================================
class Monitor:
    def __init__(self):
        self.http: aiohttp.ClientSession | None = None
        self.last_ts: int = 0
        self.state: dict = {}

    async def start(self):
        connector = aiohttp.TCPConnector(force_close=True)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        self.http = aiohttp.ClientSession(connector=connector, timeout=timeout)

        # 加载上次检查的时间戳
        if STATE_FILE.exists():
            try:
                self.state = json.loads(STATE_FILE.read_text())
                self.last_ts = self.state.get("last_ts", 0)
            except (json.JSONDecodeError, OSError):
                pass

    async def stop(self):
        if self.http:
            await self.http.close()

    def _save_state(self):
        self.state["last_ts"] = int(time.time())
        STATE_FILE.write_text(json.dumps(self.state))

    async def _api_call(self, path: str) -> tuple[int, dict]:
        """调用 new-api, 返回 (http_code, body_dict)"""
        url = f"{API_URL}/api{path}"
        headers = {"Authorization": ADMIN_KEY}
        try:
            async with self.http.get(url, headers=headers) as resp:
                body = await resp.json()
                return resp.status, body
        except aiohttp.ClientError as e:
            return 0, {"error": str(e)}
        except asyncio.TimeoutError:
            return 0, {"error": "timeout"}

    # ---- 检查 1: 服务存活 ----
    async def check_service_alive(self) -> str | None:
        """返回 None 表示正常, 返回字符串表示告警内容"""
        try:
            url = f"{API_URL}/api/status"
            async with self.http.get(url) as resp:
                if resp.status != 200:
                    return f"> HTTP 状态码: **{resp.status}**\n> 地址: {API_URL}/api/status"
                body = await resp.json()
                if not body.get("success"):
                    return f"> 服务返回异常: {body.get('message', 'unknown')}"
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            return f"> 服务不可达: {e}\n> 地址: {API_URL}/api/status"
        return None

    # ---- 检查 2: 错误日志 ----
    async def check_error_logs(self) -> str | None:
        now_ts = int(time.time())
        start_ts = self.last_ts if self.last_ts > 0 else (now_ts - CHECK_INTERVAL)
        end_ts = now_ts

        code, body = await self._api_call(
            f"/log/?type=5&start_timestamp={start_ts}&end_timestamp={end_ts}&page=0&page_size=50"
        )
        if code != 200:
            return f"> 错误日志 API 返回 HTTP **{code}**\n> 地址: /api/log?type=5"
        if not body.get("success"):
            return None  # 静默, 可能权限不足

        data = body.get("data", {})
        total = data.get("total", 0)
        if total == 0:
            return None

        items = data.get("items", [])
        lines = []
        for item in items[:10]:
            ch = item.get("channel_name", "system")
            model = item.get("model_name", "")
            content = (item.get("content", "") or "")[:100]
            lines.append(f"- [{ch}] {model} → {content}")

        t1 = datetime.fromtimestamp(start_ts).strftime("%H:%M:%S")
        t2 = datetime.fromtimestamp(end_ts).strftime("%H:%M:%S")
        return (
            f"> 时间: {t1} ~ {t2}\n"
            + "\n".join(lines)
            + f"\n\n> 共 **{total}** 条错误"
        )

    # ---- 检查 3: 渠道报错 ----
    async def check_channel_errors(self) -> str | None:
        now_ts = int(time.time())
        start_ts = now_ts - CHECK_INTERVAL
        end_ts = now_ts

        code, body = await self._api_call(
            f"/log/?type=5&start_timestamp={start_ts}&end_timestamp={end_ts}&page=0&page_size=200"
        )
        if code != 200:
            return f"> 渠道报错 API 返回 HTTP **{code}**\n> 地址: /api/log?type=5"
        if not body.get("success"):
            return None

        items = body.get("data", {}).get("items", [])
        # 按渠道归类
        channel_map: dict[str, dict] = {}
        for item in items:
            ch_name = item.get("channel_name", "")
            if not ch_name or item.get("channel", 0) == 0:
                continue
            if ch_name not in channel_map:
                channel_map[ch_name] = {"count": 0, "models": set()}
            channel_map[ch_name]["count"] += 1
            model = item.get("model_name", "")
            if model:
                channel_map[ch_name]["models"].add(model)

        if not channel_map:
            return None

        lines = []
        for ch_name, info in sorted(channel_map.items(), key=lambda x: -x[1]["count"]):
            models = ", ".join(sorted(info["models"]))
            lines.append(f"- **{ch_name}**: {info['count']}次 | {models}")

        return "\n".join(lines) + f"\n\n> 共 {len(channel_map)} 个渠道报错"

    # ---- 检查 4: 额度异常 ----
    async def check_quota_anomaly(self) -> str | None:
        now_ts = int(time.time())
        start_ts = now_ts - CHECK_INTERVAL
        end_ts = now_ts

        code, body = await self._api_call(
            f"/log/stat?type=2&start_timestamp={start_ts}&end_timestamp={end_ts}"
        )
        if code != 200:
            return f"> 额度统计 API 返回 HTTP **{code}**\n> 地址: /api/log/stat?type=2"
        if not body.get("success"):
            return None

        data = body.get("data", {})
        quota = data.get("quota", 0)
        rpm = data.get("rpm", 0)
        tpm = data.get("tpm", 0)

        prev_quota = self.state.get("prev_quota", 0)
        quota_diff = quota - prev_quota

        self.state["prev_quota"] = quota
        self.state["prev_rpm"] = rpm
        self.state["prev_tpm"] = tpm

        if QUOTA_THRESHOLD > 0 and quota_diff > QUOTA_THRESHOLD:
            return (
                f"> 5分钟内消耗: **{quota_diff}** (阈值: {QUOTA_THRESHOLD})\n"
                f"> 当前 RPM: {rpm} | TPM: {tpm}"
            )
        return None

    async def run_checks(self) -> list[tuple[str, str]]:
        """运行所有检查, 返回 [(标题, 内容), ...]"""
        alerts = []

        # 检查 1: 服务存活
        err = await self.check_service_alive()
        if err:
            alerts.append(("服务不可达", err))
            self._save_state()
            return alerts  # 服务不可达时跳过后续检查

        # 检查 2-4 (并发)
        results = await asyncio.gather(
            self.check_error_logs(),
            self.check_channel_errors(),
            self.check_quota_anomaly(),
        )
        titles = ["发现错误日志", "渠道报错汇总", "额度消耗异常"]
        for title, result in zip(titles, results):
            if result:
                alerts.append((title, result))

        self._save_state()
        return alerts


# ============================================================
# 主循环
# ============================================================
def format_alert(api_url: str, alerts: list[tuple[str, str]]) -> str:
    lines = [f"## new-api 监控告警", f"> 目标: {api_url}", f"> 时间: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for title, content in alerts:
        lines.append(f"### {title}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


async def main():
    print("=" * 50)
    print("new-api 监控守护进程")
    print(f"目标: {API_URL}")
    print(f"检查间隔: {CHECK_INTERVAL}秒")
    print(f"已知会话: {len(load_chatids())}个")
    print("=" * 50)

    monitor = Monitor()
    await monitor.start()

    bot = WeComBot()

    # 连接 → 订阅 → 再启动 reader 和 heartbeat
    while True:
        try:
            await bot.connect()
            break
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] 连接失败: {e}, 5秒后重试...")
            await asyncio.sleep(5)

    while not await bot.subscribe():
        print(f"[{datetime.now():%H:%M:%S}] 5秒后重试...")
        await asyncio.sleep(5)

    reader_task = asyncio.create_task(bot.run_forever())

    # 主循环
    async def check_loop():
        # 首次延迟 10 秒, 让 bot 有时间接收消息
        await asyncio.sleep(10)
        while bot._running:
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"[{ts}] 执行监控检查...")
                alerts = await monitor.run_checks()
                if alerts:
                    content = format_alert(API_URL, alerts)
                    print(f"[{ts}] 发现 {len(alerts)} 项异常, 推送通知...")
                    await bot.broadcast(content)
                else:
                    print(f"[{ts}] 一切正常")
            except Exception as e:
                print(f"[{ts}] 检查异常: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

    check_task = asyncio.create_task(check_loop())

    # 等待任意任务结束 (listen 断连时触发重连)
    done, pending = await asyncio.wait(
        [reader_task, check_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    # 清理
    for task in pending:
        task.cancel()
    await bot.close()
    await monitor.stop()
    print(f"[{datetime.now():%H:%M:%S}] 守护进程退出")


def run_daemon():
    """后台运行"""
    pid = os.fork()
    if pid > 0:
        print(f"守护进程已启动, PID: {pid}")
        sys.exit(0)
    os.setsid()
    # 重定向标准输出
    log_file = STATE_DIR / "newapi-monitor.log"
    sys.stdout = open(log_file, "a", buffering=1)
    sys.stderr = sys.stdout
    asyncio.run(_run())


async def _run():
    while True:
        try:
            await main()
        except Exception as e:
            print(f"[{datetime.now():%H:%M:%S}] 致命异常: {e}")
        print(f"[{datetime.now():%H:%M:%S}] 10秒后重连...")
        await asyncio.sleep(10)


if __name__ == "__main__":
    if "--daemon" in sys.argv:
        run_daemon()
    else:
        try:
            asyncio.run(_run())
        except KeyboardInterrupt:
            print("\n用户中断")
