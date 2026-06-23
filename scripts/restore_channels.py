#!/usr/bin/env python3
"""
渠道还原脚本

功能：
  从 channels_backup_*.json 完整备份文件还原渠道配置。
  - 已存在的渠道 → PUT 更新（按 ID 匹配）
  - 不存在的渠道 → POST 新建
  - 支持 --dry-run 模式预览变更

用法：
  python3 scripts/restore_channels.py <备份文件>              # 交互式还原
  python3 scripts/restore_channels.py <备份文件> --dry-run    # 仅预览，不写入
  python3 scripts/restore_channels.py <备份文件> --id 21      # 只还原指定渠道
"""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── 配置 ──────────────────────────────────────────────
API_URL = os.getenv("NEW_API_URL", "http://localhost:3000")
ADMIN_KEY = os.getenv("NEW_ADMIN_KEY", "F139rjKJlV5QQ4wZ1y9NLLCKjifoucU=")
ADMIN_USER = os.getenv("NEW_API_USER", "1")


# ── API 工具 ──────────────────────────────────────────
def api_request(method, path, data=None):
    url = f"{API_URL}{path}"
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    req.add_header("New-Api-User", ADMIN_USER)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        return {"success": False, "message": str(e)}


def get_existing_channels():
    """获取当前所有渠道的 ID 列表"""
    resp = api_request("GET", "/api/channel/?p=0&size=500")
    items = resp.get("data", {}).get("items", [])
    return {ch["id"]: ch for ch in items}


def build_update_payload(ch):
    """构建 PUT 更新请求体（保留完整字段）"""
    return {
        "id": ch["id"],
        "name": ch.get("name", ""),
        "type": ch.get("type", 0),
        "key": ch.get("key", ""),
        "base_url": ch.get("base_url", ""),
        "models": ch.get("models", ""),
        "group": ch.get("group", "default"),
        "status": ch.get("status", 1),
        "weight": ch.get("weight"),
        "priority": ch.get("priority"),
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


def build_create_payload(ch):
    """构建 POST 创建请求体（不含 ID，由系统分配）"""
    payload = build_update_payload(ch)
    payload.pop("id", None)
    return payload


# ── 主逻辑 ────────────────────────────────────────────
def main():
    # 解析参数
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    target_id = None
    if "--id" in args:
        idx = args.index("--id")
        if idx + 1 < len(args):
            target_id = int(args[idx + 1])
            args = args[:idx] + args[idx + 2:]

    backup_file = None
    for a in args:
        if not a.startswith("--"):
            backup_file = a
            break

    if not backup_file:
        print("用法: python3 restore_channels.py <备份文件> [--dry-run] [--id N]")
        print()
        print("  <备份文件>   channels_backup_*.json 完整备份文件")
        print("  --dry-run    仅预览变更，不实际写入")
        print("  --id N       只还原指定 ID 的渠道")
        sys.exit(1)

    if not os.path.exists(backup_file):
        print(f"错误: 文件不存在: {backup_file}")
        sys.exit(1)

    # 加载备份
    with open(backup_file, encoding="utf-8") as f:
        backup = json.load(f)

    channels = backup.get("channels", [])
    if not channels:
        print("错误: 备份文件中没有渠道数据")
        sys.exit(1)

    # 过滤指定 ID
    if target_id is not None:
        channels = [c for c in channels if c["id"] == target_id]
        if not channels:
            print(f"错误: 备份中没有 ID={target_id} 的渠道")
            sys.exit(1)

    mode = "🔍 预览模式 (dry-run)" if dry_run else "⚡ 执行模式"
    print(f"{'=' * 78}")
    print(f"  渠道还原  |  {mode}")
    print(f"  备份文件: {os.path.basename(backup_file)}")
    print(f"  备份时间: {backup.get('backup_time', '未知')}")
    print(f"  待还原: {len(channels)} 个渠道")
    print(f"{'=' * 78}")

    # 获取现有渠道
    print("\n查询现有渠道...")
    existing = get_existing_channels()
    print(f"  当前系统有 {len(existing)} 个渠道")

    # 分类：更新 vs 新建
    to_update = []
    to_create = []
    for ch in channels:
        if ch["id"] in existing:
            to_update.append(ch)
        else:
            to_create.append(ch)

    # 展示变更计划
    if to_update:
        print(f"\n{'─' * 78}")
        print(f"  将更新 {len(to_update)} 个已有渠道")
        print(f"{'─' * 78}")
        for ch in to_update:
            old = existing[ch["id"]]
            key_changed = (old.get("key", "") != ch.get("key", "") and ch.get("key", ""))
            name_changed = old.get("name", "") != ch.get("name", "")
            models_changed = old.get("models", "") != ch.get("models", "")
            marks = []
            if key_changed:
                marks.append("🔑Key")
            if name_changed:
                marks.append("📝名称")
            if models_changed:
                marks.append("🤖模型")
            tag = " " + ", ".join(marks) if marks else " (无实质变更)"
            print(f"  ID={ch['id']:>3} {ch['name']:<35}{tag}")

    if to_create:
        print(f"\n{'─' * 78}")
        print(f"  将新建 {len(to_create)} 个渠道（原 ID 不保留）")
        print(f"{'─' * 78}")
        for ch in to_create:
            print(f"  原ID={ch['id']:>3} {ch['name']:<35} type={ch.get('type', '?')}")

    # 确认
    if dry_run:
        print(f"\n  🔍 预览模式，不执行写入。")
        return

    if not to_update and not to_create:
        print(f"\n  无需变更。")
        return

    answer = input(f"\n  确认还原? (y/N): ").strip().lower()
    if answer != "y":
        print("  已取消。")
        return

    # 执行更新
    success = 0
    failed = 0
    if to_update:
        print(f"\n更新已有渠道...")
        for ch in to_update:
            payload = build_update_payload(ch)
            resp = api_request("PUT", "/api/channel/", payload)
            if resp.get("success"):
                print(f"  ✅ ID={ch['id']} {ch['name']}")
                success += 1
            else:
                print(f"  ❌ ID={ch['id']} {ch['name']} — {resp.get('message', '未知错误')}")
                failed += 1

    # 执行新建
    if to_create:
        print(f"\n新建渠道...")
        for ch in to_create:
            payload = build_create_payload(ch)
            resp = api_request("POST", "/api/channel/", payload)
            if resp.get("success"):
                new_id = resp.get("data", {}).get("id", "?")
                print(f"  ✅ {ch['name']} → 新ID={new_id}")
                success += 1
            else:
                print(f"  ❌ {ch['name']} — {resp.get('message', '未知错误')}")
                failed += 1

    # 汇总
    print(f"\n{'─' * 78}")
    print(f"  还原完成: 成功 {success}, 失败 {failed}")
    print(f"{'─' * 78}")


if __name__ == "__main__":
    main()
