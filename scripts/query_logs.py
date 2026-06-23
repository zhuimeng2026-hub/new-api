#!/usr/bin/env python3
"""快速查询 new-api 请求日志 — 出问题就用它

用法:
  python3 query_logs.py                           # 消耗(左) | 错误(右) 各5条, 分栏显示
  python3 query_logs.py --ip 1.14.182.208         # 按 IP 过滤
  python3 query_logs.py --token mytoken           # 按令牌名称过滤
  python3 query_logs.py --error socket            # 按错误信息关键词过滤
  python3 query_logs.py -n 20                     # 查最近 20 条
  python3 query_logs.py --type 5                  # 仅错误日志 (单栏)
  python3 query_logs.py --type 2                  # 仅消耗日志 (单栏)
  python3 query_logs.py --type 0                  # 全部类型 (单栏)
"""

import argparse
import json
import subprocess
import sys
from collections import Counter


def load_env():
    env = {}
    try:
        for line in open("/opt/new-api/.env"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        print("错误: /opt/new-api/.env 不存在")
        sys.exit(1)
    return env


def build_api_base(raw_url):
    base = raw_url.rstrip("/")
    if base.endswith("/channel"):
        base = base[:-8]
    if not base.endswith("/api"):
        base += "/api"
    return base


def api_get(api_base, admin_key, admin_user, path, params=None):
    url = f"{api_base}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    r = subprocess.run(
        [
            "curl", "-s",
            "-H", f"Authorization: Bearer {admin_key}",
            "-H", f"New-Api-User: {admin_user}",
            url,
        ],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(r.stdout)


def ts_to_short(ts):
    """Unix timestamp -> '06-23 17:36'"""
    if not ts:
        return "?" * 11
    from datetime import datetime, timezone, timedelta
    dt = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8)))
    return dt.strftime("%m-%d %H:%M")


def parse_other(other_str):
    if not other_str:
        return {}
    try:
        return json.loads(other_str)
    except (json.JSONDecodeError, TypeError):
        return {}


TYPE_LABELS = {0: "全部", 1: "充值", 2: "消耗", 3: "管理", 4: "系统", 5: "错误", 6: "退款"}


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------

def fmt_consume(item, w):
    """type=2 消耗日志 -> 3行"""
    ts = ts_to_short(item.get("created_at"))
    ch_id = item.get("channel") or item.get("channel_id", "")
    ch_name = item.get("channel_name", "?")
    model = item.get("model_name", "?")
    quota = item.get("quota", 0)
    use_time = item.get("use_time", 0)
    other = parse_other(item.get("other"))
    content = (item.get("content") or "")
    token_name = item.get("token_name") or ""

    line1 = f"[{ts}] [{ch_id}]{ch_name}"
    line2 = f"  {model}  q={quota}  {use_time}ms"
    # 第3行: 优先显示错误内容; 空则标 ⚠ + 路径
    parts = []
    if content:
        parts.append(content[:w - 2])
    else:
        parts.append("⚠ 无错误消息")
    path = other.get("request_path", "")
    if path:
        path_short = path[4:] if path.startswith("/v1/") else path
        parts.append(path_short[:w - 12])
    frt = other.get("frt", -1000)
    if frt > 0:
        parts.append(f"frt={frt}ms")
    if token_name:
        parts.append(f"tk={token_name[:8]}")
    line3 = ("  " + " | ".join(parts)) if parts else ""

    return [line1[:w], line2[:w], line3[:w]]


def fmt_error(item, w):
    """type=5 错误日志 -> 3行"""
    ts = ts_to_short(item.get("created_at"))
    ch_id = item.get("channel") or item.get("channel_id", "")
    ch_name = item.get("channel_name", "?")
    model = item.get("model_name", "?")
    quota = item.get("quota", 0)
    use_time = item.get("use_time", 0)
    other = parse_other(item.get("other"))
    content = (item.get("content") or "")

    line1 = f"[{ts}] [{ch_id}]{ch_name}"
    # 第2行: 模型 + 重试链
    line2 = f"  {model}  q={quota}  {use_time}ms"
    uc = other.get("admin_info", {}).get("use_channel") if isinstance(other.get("admin_info"), dict) else None
    if uc and len(uc) > 1:
        line2 += "  →" + "→".join(str(x) for x in uc)
    # 第3行: HTTP码 + 错误消息
    parts = []
    if other.get("error_code"):
        parts.append(f"HTTP{other['error_code']}")
    if content:
        parts.append(content[:w - 15])
    line3 = ("  " + " | ".join(parts)) if parts else ""

    return [line1[:w], line2[:w], line3[:w]]


def pad_to_width(s, w):
    """填充到指定宽度 (借助亚洲字符不算宽度, 这里简单用空格)"""
    return s.ljust(w)


# ---------------------------------------------------------------------------
# 显示
# ---------------------------------------------------------------------------

def show_linear(items, label):
    """单栏线性显示"""
    print(f"=== 日志查询结果 ({label}) ===")
    print(f"共 {len(items)} 条\n")

    for item in items:
        ts = ts_to_short(item.get("created_at"))
        use_time = item.get("use_time", 0)
        content = (item.get("content") or "")[:200]
        ch_id = item.get("channel") or item.get("channel_id", "")
        model = item.get("model_name", "?")
        other = parse_other(item.get("other"))

        print(f"[{ts}] [{ch_id}] {item.get('channel_name', '?')}  |  {model}")
        print(f"   ID={item.get('id')}  IP={item.get('ip', '?')}"
              f"  耗时={use_time}ms  quota={item.get('quota', 0)}")

        if other.get("error_code"):
            print(f"   HTTP {other['error_code']}  {other.get('request_path', '')}")
        if content:
            print(f"   {content}")
        uc = other.get("admin_info", {}).get("use_channel") if isinstance(other.get("admin_info"), dict) else None
        if uc and len(uc) > 1:
            print(f"   重试链: {uc}")
        print()


def show_split(items_l, label_l, items_r, label_r, n):
    """左右分栏: 各取 n 条"""
    # 列宽: 终端 80 列, 左右各 38, 中间 " │ " 占 3
    W = 38
    header = f"  {label_l:<{W}} │ {label_r}"
    sep = f"  {'─' * W}─┼─{'─' * W}"

    print(header)
    print(sep)

    # 各取最多 n 条
    left = items_l[:n]
    right = items_r[:n]

    # 格式化每条为 3 行
    left_rows = [fmt_consume(item, W) for item in left]
    right_rows = [fmt_error(item, W) for item in right]

    # 逐行输出
    max_entries = max(len(left_rows), len(right_rows))
    for i in range(max_entries):
        l_lines = left_rows[i] if i < len(left_rows) else ["", "", ""]
        r_lines = right_rows[i] if i < len(right_rows) else ["", "", ""]
        for j in range(3):
            l = pad_to_width(l_lines[j], W)
            r = pad_to_width(r_lines[j], W)
            print(f"  {l} │ {r}")
        # 条目间隔线
        if i < max_entries - 1:
            print(f"  {'─' * W}─┼─{'─' * W}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="查询 new-api 请求日志")
    parser.add_argument("--ip", help="按客户端 IP 过滤")
    parser.add_argument("--token", help="按令牌名称过滤")
    parser.add_argument("--error", help="按错误信息关键词过滤 (不区分大小写)")
    parser.add_argument("-n", "--num", type=int, default=5, help="查询条数 (默认 5, 最大 500)")
    parser.add_argument("--type", type=str, default="2,5",
                        help="日志类型: 2,5=消耗+错误分栏(默认), 5=仅错误, 2=仅消耗, 0=全部")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    type_vals = [int(t.strip()) for t in args.type.split(",") if t.strip().isdigit()]
    if not type_vals:
        print("错误: --type 格式无效，示例: 2,5  /  5  /  0")
        sys.exit(1)

    env = load_env()
    api_base = build_api_base(env.get("new_admin_url", ""))
    admin_key = env.get("new_admin_key", "")
    admin_user = env.get("New-Api-User", "1")

    if not api_base or not admin_key:
        print("错误: .env 中缺少 new_admin_url 或 new_admin_key")
        sys.exit(1)

    has_filter = bool(args.ip or args.token or args.error)
    fetch_size = min(args.num, 500)
    if has_filter and fetch_size < 100:
        fetch_size = 100

    # 每类单独拉取
    items_by_type = {}
    for t in type_vals:
        data = api_get(api_base, admin_key, admin_user, "/log/", {
            "size": str(fetch_size),
            "type": str(t),
        })
        if data.get("success"):
            items_by_type[t] = data["data"].get("items", [])
        else:
            items_by_type[t] = []

    # 客户端过滤
    def apply_filters(lst):
        if args.ip:
            lst = [i for i in lst if i.get("ip") == args.ip]
        if args.token:
            kw = args.token.lower()
            lst = [i for i in lst if kw in (i.get("token_name") or "").lower()]
        if args.error:
            kw = args.error.lower()
            lst = [i for i in lst if kw in (i.get("content") or "").lower()
                                   or kw in (i.get("model_name") or "").lower()
                                   or kw in (i.get("channel_name") or "").lower()]
        return lst

    for t in type_vals:
        items_by_type[t] = apply_filters(items_by_type[t])

    if args.json:
        all_items = []
        for items in items_by_type.values():
            all_items.extend(items)
        all_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        print(json.dumps(all_items, indent=2, ensure_ascii=False))
        return

    # ---- 显示 ----
    # 默认 2,5 -> 分栏; 但一边为空时自动退化为单栏
    if set(type_vals) == {2, 5}:
        left = items_by_type.get(2, [])
        right = items_by_type.get(5, [])
        if not left or not right:
            # 退化为单栏
            items = left + right
            items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            items = items[:args.num]
            label = "消耗" if not right else "错误"
            show_linear(items, label)
        else:
            show_split(left, "消耗 (type=2)", right, "错误 (type=5)", n=args.num)
    else:
        # 单栏: 合并排序
        all_items = []
        for items in items_by_type.values():
            all_items.extend(items)
        all_items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        all_items = all_items[:args.num]
        label = "+".join(TYPE_LABELS.get(t, str(t)) for t in type_vals)
        show_linear(all_items, label)


if __name__ == "__main__":
    main()
