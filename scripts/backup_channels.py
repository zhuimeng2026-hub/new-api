#!/usr/bin/env python3
"""
渠道完整备份脚本

功能：
  1. 通过管理 API 获取全部渠道配置（模型、分组、设置等）
  2. 通过数据库查询真实 Key（API 层会脱敏）
  3. 合并生成完整的渠道备份 JSON
  4. 检查 Key 是否为空并告警
  5. 输出可用于紧急还原的完整数据

用法：
  python3 scripts/backup_channels.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from urllib.request import Request, urlopen

# ── 配置 ──────────────────────────────────────────────
API_URL = os.getenv("NEW_API_URL", "http://localhost:3000")
ADMIN_KEY = os.getenv("NEW_ADMIN_KEY", "F139rjKJlV5QQ4wZ1y9NLLCKjifoucU=")
ADMIN_USER = os.getenv("NEW_API_USER", "1")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "channels")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── API 请求 ──────────────────────────────────────────
def api_get(path):
    req = Request(f"{API_URL}{path}", method="GET")
    req.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    req.add_header("New-Api-User", ADMIN_USER)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


# ── 数据库查询真实 Key ────────────────────────────────
def get_real_keys_from_db():
    """通过 docker exec 查询 PostgreSQL 获取所有渠道的真实 Key"""
    sql = "SELECT id, key FROM channels ORDER BY id;"
    result = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "root", "-d", "new-api",
         "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"  ❌ 数据库查询失败: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    keys = {}
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            ch_id = int(parts[0])
            keys[ch_id] = parts[1]
    return keys


# ── 主逻辑 ────────────────────────────────────────────
def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{'=' * 78}")
    print(f"  渠道完整备份  |  {now}")
    print(f"{'=' * 78}")

    # 1. 获取 API 渠道列表
    print("\n[1/4] 从 API 获取渠道列表...")
    resp = api_get("/api/channel/?p=0&size=100")
    api_channels = resp.get("data", {}).get("items", [])
    print(f"  获取到 {len(api_channels)} 个渠道")

    # 2. 从数据库获取真实 Key
    print("\n[2/4] 从数据库查询真实 Key...")
    db_keys = get_real_keys_from_db()
    print(f"  获取到 {len(db_keys)} 个渠道的 Key")

    # 3. 合并数据
    print("\n[3/4] 合并数据...")
    channels = []
    warnings = []

    # 渠道类型映射（常用）
    TYPE_NAMES = {
        1: "OpenAI", 2: "Claude(官方)", 3: "Claude(代理)", 4: "Google PaLM",
        5: "Azure", 8: "Custom", 10: "Moonshot", 11: "Zhipu",
        12: "Ali", 13: "Baidu", 14: "Anthropic", 15: "Tongyi",
        16: "MiniMax", 17: "Qwen", 18: "Hunyuan", 19: "Spark",
        20: "OpenRouter", 21: "Midjourney", 22: "Suno",
        25: "Xiaomi MiMo", 26: "Zhipu BigModel", 27: "ByteDance",
        30: "Hailuo", 31: "Kling", 32: "Jimeng", 33: "Vidu",
        35: "MiniMax", 36: "DeepSeek", 37: "StepFun", 38: "Yi",
        39: "Cloudflare", 40: "SiliconFlow", 41: "XAI",
        42: "Coze", 43: "DeepSeek", 44: "Volcengine(Doubao)",
        45: "Volcengine(Coding)", 46: "Volcengine(Agent)",
        50: "Gemini(代理)", 51: "AWS Bedrock", 52: "Cohere",
        54: "DoubaoVideo", 55: "HailuoVideo", 56: "KlingVideo",
        57: "Codex", 58: "Xiaomi MiMo", 59: "ModelScope",
    }

    for ch in api_channels:
        ch_id = ch["id"]
        api_key = ch.get("key", "")
        real_key = db_keys.get(ch_id, "")

        # 检查 Key 状态
        key_status = "ok"
        if not real_key:
            key_status = "empty_in_db"
            warnings.append(f"  ❌ ID={ch_id} {ch['name']} — 数据库中 Key 为空")
        elif not api_key and real_key:
            key_status = "masked_by_api"

        merged = {
            "id": ch_id,
            "name": ch.get("name", ""),
            "type": ch.get("type", 0),
            "type_name": TYPE_NAMES.get(ch.get("type", 0), f"Unknown({ch.get('type', 0)})"),
            "status": ch.get("status", 0),
            "key": real_key,  # 真实 Key
            "key_status": key_status,
            "base_url": ch.get("base_url", ""),
            "models": ch.get("models", ""),
            "group": ch.get("group", "default"),
            "weight": ch.get("weight", 0),
            "priority": ch.get("priority", 0),
            "auto_ban": ch.get("auto_ban", 1),
            "model_mapping": ch.get("model_mapping", ""),
            "status_code_mapping": ch.get("status_code_mapping", ""),
            "setting": ch.get("setting", ""),
            "param_override": ch.get("param_override", ""),
            "header_override": ch.get("header_override", ""),
            "remark": ch.get("remark", ""),
            "tag": ch.get("tag", ""),
            "other": ch.get("other", ""),
            "other_info": ch.get("other_info", ""),
            "channel_info": ch.get("channel_info", {}),
            "settings": ch.get("settings", ""),
        }
        channels.append(merged)

    # 4. 输出报告
    print(f"\n[4/4] 生成备份报告...\n")

    # 渠道总表
    print(f"{'─' * 78}")
    print(f"  渠道总表 ({len(channels)} 个)")
    print(f"{'─' * 78}")
    print(f"  {'ID':>4} {'名称':<30} {'类型':<15} {'状态':>4} {'Key':>6} {'分组':<10}")
    print(f"  {'─' * 4} {'─' * 30} {'─' * 15} {'─' * 4} {'─' * 6} {'─' * 10}")

    status_map = {0: "🔴禁用", 1: "🟢启用", 2: "🟡测试"}
    for ch in channels:
        st = status_map.get(ch["status"], f"?{ch['status']}")
        kl = len(ch["key"]) if ch["key"] else 0
        ks = f"{kl:>5}" if kl > 0 else "  ❌空"
        print(f"  {ch['id']:>4} {ch['name']:<30} {ch['type_name']:<15} {st:>4} {ks} {ch['group']:<10}")

    # Key 告警
    if warnings:
        print(f"\n{'─' * 78}")
        print(f"  ⚠  Key 告警")
        print(f"{'─' * 78}")
        for w in warnings:
            print(w)

    # 统计
    enabled = sum(1 for c in channels if c["status"] == 1)
    disabled = sum(1 for c in channels if c["status"] == 0)
    testing = sum(1 for c in channels if c["status"] == 2)
    empty_key = sum(1 for c in channels if not c["key"])

    print(f"\n{'─' * 78}")
    print(f"  统计")
    print(f"{'─' * 78}")
    print(f"  总计: {len(channels)} 个渠道")
    print(f"  🟢 启用: {enabled}  |  🟡 测试: {testing}  |  🔴 禁用: {disabled}")
    print(f"  Key 正常: {len(channels) - empty_key}  |  Key 为空: {empty_key}")

    # 5. 导出 JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = {
        "backup_time": now,
        "api_url": API_URL,
        "total_channels": len(channels),
        "channels": channels,
    }
    json_path = os.path.join(OUTPUT_DIR, f"channels_backup_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=2)

    print(f"\n{'─' * 78}")
    print(f"  备份已导出: {json_path}")
    print(f"{'─' * 78}")

    # 同时生成一个精简版（只含 ID/key/base_url/models，用于紧急还原）
    restore_data = []
    for ch in channels:
        if ch["key"]:  # 只备份有 key 的
            restore_data.append({
                "id": ch["id"],
                "name": ch["name"],
                "type": ch["type"],
                "key": ch["key"],
                "base_url": ch["base_url"],
                "models": ch["models"],
                "group": ch["group"],
                "status": ch["status"],
            })

    restore_path = os.path.join(OUTPUT_DIR, f"channels_restore_{timestamp}.json")
    with open(restore_path, "w", encoding="utf-8") as f:
        json.dump(restore_data, f, ensure_ascii=False, indent=2)
    print(f"  还原精简版: {restore_path} ({len(restore_data)} 个有效渠道)")

    print()


if __name__ == "__main__":
    main()
