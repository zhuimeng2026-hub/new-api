#!/usr/bin/env python3
"""new-api 频道配置备份/还原工具 — 使用说明

用法:
  python3 channel_backup.py export [文件路径]           导出所有频道配置到 JSON 文件
  python3 channel_backup.py import <文件路径> [--dry-run]  从 JSON 文件还原频道配置
  python3 channel_backup.py show <文件路径>              预览备份文件中的频道配置

导出:
  python3 channel_backup.py export                          # 自动命名: channel_backup_YYYYMMDD_HHMMSS.json
  python3 channel_backup.py export my_channels.json         # 指定文件名
  python3 channel_backup.py export --keep-keys my.json      # 保留 API Key (默认脱敏为 "")

导入:
  python3 channel_backup.py import my_channels.json --dry-run  # 预览将要导入的内容，不做实际变更
  python3 channel_backup.py import my_channels.json             # 正式导入 (PUT /api/channel/)

预览:
  python3 channel_backup.py show my_channels.json           # 按优先级展示频道列表和模型配置

凭据:
  自动从 {项目根}/.env 读取 new_admin_url, new_admin_key, New-Api-User。
  .env 不存在或字段缺失时会报错退出。

依赖:
  仅 Python 标准库 (json, urllib, os, sys, datetime)，无需 pip install。
"""

import json
import os
import sys
import urllib.request
from datetime import datetime

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")
ENV_FILE = os.path.abspath(ENV_FILE)


def load_env():
    env = {}
    keys = ("new_admin_url", "new_admin_key", "New-Api-User")
    if not os.path.exists(ENV_FILE):
        die(f".env not found: {ENV_FILE}")
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            for k in keys:
                if line.startswith(f"{k}="):
                    env[k] = line.split("=", 1)[1]
    missing = [k for k in keys if k not in env]
    if missing:
        die(f"Missing .env fields: {', '.join(missing)}")
    return env


def die(msg):
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def api_get(env, path, params=None):
    url = env["new_admin_url"].replace("/api/channel/", "") + path
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += "?" + qs
    req = urllib.request.Request(url)
    req.add_header("Authorization", f'Bearer {env["new_admin_key"]}')
    req.add_header("New-Api-User", env["New-Api-User"])
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def api_put(env, path, body):
    url = env["new_admin_url"].replace("/api/channel/", "") + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f'Bearer {env["new_admin_key"]}')
    req.add_header("New-Api-User", env["New-Api-User"])
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


# --- export ---

def cmd_export(env, path):
    data = api_get(env, "/api/channel/", {"page_size": 200})
    if not data.get("success"):
        die(f"查询频道失败: {data.get('message', '')}")
    items = data["data"]["items"]

    # Redact keys unless --keep-keys is passed
    if "--keep-keys" not in sys.argv:
        for ch in items:
            ch["key"] = ""

    with open(path, "w") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    enabled = sum(1 for c in items if c["status"] == 1)
    print(f"✅ 已导出 {len(items)} 个频道 (启用: {enabled}) → {path}")


# --- import ---

def cmd_import(env, path, dry_run=False):
    with open(path) as f:
        items = json.load(f)

    if not isinstance(items, list):
        die("备份文件格式错误: 应为 JSON 数组")

    total = len(items)
    ok = fail = 0
    for i, ch in enumerate(items):
        chid = ch.get("id")
        name = ch.get("name", "?")
        label = f"[{i+1}/{total}] ID={chid} {name}"

        if dry_run:
            print(f"  {label} (dry-run, skipped)")
            continue

        # Fields the API expects on PUT
        payload = {k: ch[k] for k in ch if k in (
            "id", "type", "key", "status", "name", "weight", "base_url",
            "models", "group", "model_mapping", "priority", "auto_ban",
            "balance", "other", "test_model", "remark", "tag",
            "setting", "param_override", "header_override", "other_info",
        )}
        # Ensure non-null fields
        for f in ("model_mapping", "status_code_mapping"):
            if f in payload and payload[f] is None:
                payload[f] = "{}"

        try:
            res = api_put(env, "/api/channel/", payload)
            if res.get("success"):
                ok += 1
                print(f"  {label} ✅")
            else:
                fail += 1
                print(f"  {label} ❌ {res.get('message', '')}")
        except Exception as e:
            fail += 1
            print(f"  {label} ❌ {e}")

    print(f"\n导入完成: {ok} 成功, {fail} 失败 (共 {total})")


# --- show ---

def cmd_show(path):
    with open(path) as f:
        items = json.load(f)

    enabled = [c for c in items if c["status"] == 1]
    disabled = [c for c in items if c["status"] != 1]
    enabled.sort(key=lambda x: (-x.get("priority", 0), -x["id"]))

    print(f"共 {len(items)} 个频道 (启用: {len(enabled)}, 禁用: {len(disabled)})\n")
    print("=== 启用频道 ===\n")
    for ch in enabled:
        models = [m.strip() for m in ch["models"].split(",") if m.strip()]
        print(f'  [{ch["priority"]:>5}] {ch["name"]:<22s} {len(models)} models')
        if len(models) <= 5:
            print(f'          {", ".join(models)}')
        else:
            print(f'          {", ".join(models[:3])} ... +{len(models)-3}')
        mapping = ch.get("model_mapping")
        if mapping and mapping not in ("{}", "null", None):
            print(f"          ↳ {mapping}")
        print()

    if disabled:
        print("=== 禁用频道 ===\n")
        for ch in disabled:
            print(f'  ID={ch["id"]:<4d} {ch["name"]}')


# --- main ---

def main():
    env = load_env()
    args = sys.argv[1:]

    if len(args) < 1:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    if cmd == "export":
        rest = [a for a in args[1:] if not a.startswith("--")]
        path = rest[0] if rest else f"channel_backup_{datetime.now():%Y%m%d_%H%M%S}.json"
        cmd_export(env, path)

    elif cmd == "import":
        if len(args) < 2:
            die("缺少备份文件路径\n用法: python3 channel_backup.py import backup.json [--dry-run]")
        dry = "--dry-run" in args
        cmd_import(env, args[1], dry_run=dry)

    elif cmd == "show":
        if len(args) < 2:
            die("缺少备份文件路径\n用法: python3 channel_backup.py show backup.json")
        cmd_show(args[1])

    else:
        die(f"未知命令: {cmd}\n支持: export, import, show")


if __name__ == "__main__":
    main()
