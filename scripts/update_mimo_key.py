#!/usr/bin/env python3
"""
小米 MiMo 渠道 Key 更新脚本

用法:
  python3 scripts/update_mimo_key.py <新key>
  python3 scripts/update_mimo_key.py tp-c69dep29d5vmq7dai1d82c5enz1ub3bl9ixgyc7ijy3hihpx

功能:
  1. 更新 channels 表中 MiMo-Token-Plan (ID=21) 的 key
  2. 通过管理 API 触发内存缓存刷新（无需重启容器）
"""

import subprocess
import json
import sys

# === 配置 ===
CHANNEL_ID = 21
CHANNEL_NAME = "小米MiMo-Token-Plan"

# 从 .env 读取管理 API 配置
env = {}
for line in open("/opt/new-api/.env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

ADMIN_URL = env.get("new_admin_url", "").rstrip("/")
if ADMIN_URL.endswith("/channel"):
    ADMIN_URL = ADMIN_URL[:-8]
if not ADMIN_URL.endswith("/api"):
    ADMIN_URL = ADMIN_URL + "/api"
ADMIN_KEY = env.get("new_admin_key", "")
ADMIN_USER = env.get("New-Api-User", "1")


def run_sql(sql):
    """执行 PostgreSQL 语句"""
    r = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "root", "-d", "new-api", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip(), r.returncode


def trigger_cache_refresh():
    """通过 PUT 接口触发内存缓存刷新"""
    r = subprocess.run(
        [
            "curl", "-s", "-X", "PUT",
            "-H", f"Authorization: Bearer {ADMIN_KEY}",
            "-H", f"New-Api-User: {ADMIN_USER}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps({"id": CHANNEL_ID}),
            f"{ADMIN_URL}/channel/",
        ],
        capture_output=True, text=True, timeout=15,
    )
    return json.loads(r.stdout)


def main():
    if len(sys.argv) < 2:
        print(f"用法: python3 {sys.argv[0]} <新key>")
        sys.exit(1)

    new_key = sys.argv[1].strip()
    if not new_key:
        print("错误: key 不能为空")
        sys.exit(1)

    # 1. 查询当前 key（只显示前10位）
    out, _ = run_sql(f"SELECT id, name, substr(key,1,10) as key_preview FROM channels WHERE id = {CHANNEL_ID};")
    print(f"当前渠道:\n{out}\n")

    # 2. 更新 key
    sql = f"UPDATE channels SET key = '{new_key}' WHERE id = {CHANNEL_ID} RETURNING id, name, length(key);"
    out, code = run_sql(sql)
    if code != 0:
        print(f"数据库更新失败:\n{out}")
        sys.exit(1)
    print(f"数据库已更新:\n{out}\n")

    # 3. 触发缓存刷新
    print("触发内存缓存刷新...")
    result = trigger_cache_refresh()
    if result.get("success"):
        print("缓存刷新成功")
    else:
        print(f"缓存刷新失败: {result.get('message', '未知错误')}")
        print("提示: 可手动执行 docker restart new-api")
        sys.exit(1)

    print(f"\n完成! {CHANNEL_NAME} (ID={CHANNEL_ID}) 的 key 已更新。")


if __name__ == "__main__":
    main()
