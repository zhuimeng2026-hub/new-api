#!/usr/bin/env python3
"""
sync_modelscope_models.py — 同步魔搭社区可用模型到 new-api 渠道

功能:
  1. 调用魔搭推理 API (/v1/models) 获取当前可用模型列表
  2. 从 new-api API 获取渠道配置（models、model_mapping）
  3. 对比差异，新增/删除模型
  4. 通过 new-api API 更新渠道

用法:
  python3 sync_modelscope_models.py                   # 执行同步
  python3 sync_modelscope_models.py --dry-run         # 只预览，不执行
  python3 sync_modelscope_models.py --channel-id 9    # 指定渠道 ID（默认 9）
  python3 sync_modelscope_models.py --ignore Qwen/Qwen3-4B  # 忽略指定模型
"""

import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── ANSI colors ──────────────────────────────────────────────
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"


def load_env():
    """从 /opt/new-api/.env 读取配置"""
    env = {}
    try:
        with open("/opt/new-api/.env") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f"{RED}错误: 找不到 /opt/new-api/.env{RESET}", file=sys.stderr)
        sys.exit(1)
    return env


def api_request(url, token, method="GET", body=None, timeout=15):
    """通用 HTTP 请求"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req = Request(url, method=method, headers=headers, data=data)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        print(f"{RED}HTTP {e.code}: {e.reason}{RESET}", file=sys.stderr)
        if err_body:
            print(f"{DIM}{err_body[:500]}{RESET}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"{RED}连接失败: {e.reason}{RESET}", file=sys.stderr)
        sys.exit(1)


def get_channel(base_url, admin_key, admin_user, channel_id):
    """获取渠道配置"""
    url = f"{base_url}/channel/{channel_id}"
    headers = {
        "Authorization": f"Bearer {admin_key}",
        "New-Api-User": admin_user,
    }
    req = Request(url, headers=headers)
    with urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    if not result.get("success"):
        print(f"{RED}获取渠道失败: {result.get('message')}{RESET}", file=sys.stderr)
        sys.exit(1)
    return result["data"]


def update_channel(base_url, admin_key, admin_user, channel_id, models_str, mapping_str):
    """更新渠道模型列表和映射"""
    url = f"{base_url}/channel/"
    body = {
        "id": channel_id,
        "models": models_str,
        "model_mapping": mapping_str,
    }
    headers = {
        "Authorization": f"Bearer {admin_key}",
        "New-Api-User": admin_user,
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode()
    req = Request(url, method="PUT", headers=headers, data=data)
    with urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    if not result.get("success"):
        print(f"{RED}更新渠道失败: {result.get('message')}{RESET}", file=sys.stderr)
        sys.exit(1)
    return result


def get_upstream_models(base_url, modelscope_key):
    """从魔搭推理 API 获取可用模型列表"""
    url = f"{base_url}/v1/models"
    headers = {"Authorization": f"Bearer {modelscope_key}"}
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
    except (HTTPError, URLError) as e:
        print(f"{RED}获取魔搭模型列表失败: {e}{RESET}", file=sys.stderr)
        sys.exit(1)
    models = {m["id"] for m in result.get("data", [])}
    return models


def main():
    parser = argparse.ArgumentParser(description="同步魔搭社区可用模型到 new-api 渠道")
    parser.add_argument("--dry-run", action="store_true", help="只输出差异，不执行更新")
    parser.add_argument("--channel-id", type=int, default=9, help="渠道 ID（默认 9）")
    parser.add_argument("--ignore", action="append", default=[], help="不添加的模型（可多次使用）")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    # ── 加载配置 ──────────────────────────────────────────────
    env = load_env()

    raw_url = env.get("new_admin_url", "")
    if raw_url and not raw_url.startswith("http"):
        raw_url = "http://" + raw_url
    base_url = raw_url.rstrip("/")
    # .env 中可能是 https://host/api/channel/ 或 https://host/api
    # 统一处理为 https://host/api（去掉末尾的 /channel）
    if base_url.endswith("/channel"):
        base_url = base_url[:-8]
    if not base_url.endswith("/api"):
        base_url += "/api"

    admin_key = env.get("new_admin_key", "")
    admin_user = env.get("New-Api-User", "1")
    modelscope_key = env.get("modelscope_key", "")

    if not admin_key:
        print(f"{RED}错误: .env 中缺少 new_admin_key{RESET}", file=sys.stderr)
        sys.exit(1)
    if not modelscope_key:
        print(f"{RED}错误: .env 中缺少 modelscope_key{RESET}", file=sys.stderr)
        sys.exit(1)

    # ── 获取上游可用模型 ──────────────────────────────────────
    channel = get_channel(base_url, admin_key, admin_user, args.channel_id)
    upstream_url = channel.get("base_url", "https://api-inference.modelscope.cn")

    print(f"{BOLD}=== ModelScope 模型同步 ==={RESET}")
    print(f"渠道: {CYAN}{channel['name']}{RESET} (ID={channel['id']}, type={channel['type']})")
    print(f"上游: {DIM}{upstream_url}/v1/models{RESET}")
    print()

    upstream_models = get_upstream_models(upstream_url, modelscope_key)

    # ── 解析本地配置 ──────────────────────────────────────────
    local_models_str = channel.get("models", "")
    local_models = [m.strip() for m in local_models_str.split(",") if m.strip()]

    mapping_str = channel.get("model_mapping", "{}")
    try:
        mapping = json.loads(mapping_str) if mapping_str else {}
    except json.JSONDecodeError:
        mapping = {}

    # 别名集合：model_mapping 中的 key（用户自定义名称）
    alias_names = set(mapping.keys())
    # 别名目标集合：model_mapping 中的 value（实际发送给上游的模型 ID）
    alias_targets = set(mapping.values())

    # ── 分类 ──────────────────────────────────────────────────
    # 区分"上游模型名"和"自定义别名"
    upstream_set = set()      # 本地 models 中属于上游模型 ID 的
    custom_names = set()      # 本地 models 中的自定义别名

    for m in local_models:
        if m in upstream_models or m in alias_targets:
            upstream_set.add(m)
        elif m in alias_names:
            custom_names.add(m)
        else:
            # 可能是已下架的上游模型，也可能是自定义名
            # 如果它在 mapping 中作为 value 出现，视为别名目标
            if m in alias_targets:
                upstream_set.add(m)
            else:
                # 既不在上游、也不是别名 key、也不是别名 value → 视为可能已下架
                upstream_set.add(m)

    # ── 计算差异 ──────────────────────────────────────────────
    ignore_set = set(args.ignore)

    # 需要新增的：上游有、本地无
    to_add = sorted(upstream_models - set(local_models) - ignore_set)

    # 需要删除的：本地有、上游无，且不是别名 key/value，也不在 ignore 中
    to_remove = []
    to_keep_alias = []
    for m in local_models:
        if m in upstream_models:
            continue  # 上游还有，保留
        if m in alias_names:
            to_keep_alias.append(m)  # 是自定义别名，保留
            continue
        if m in alias_targets:
            # 是某个别名的目标，保留（但标记警告）
            to_keep_alias.append(m)
            continue
        if m in ignore_set:
            continue
        # 不在上游、不是别名 → 删除
        to_remove.append(m)

    # 同时清理 mapping：删除 value 指向已不在上游、且 key 不在新 models 列表中的映射
    new_model_set = set(local_models) | set(to_add) - set(to_remove)
    mapping_to_remove = []
    for k, v in list(mapping.items()):
        # 如果 value 指向的模型不在上游可用列表中，且不是自定义名
        if v not in upstream_models and v not in ignore_set:
            # 检查 value 是否已经在 to_remove 中
            if v in to_remove:
                mapping_to_remove.append((k, v))

    # ── 输出报告 ──────────────────────────────────────────────
    print(f"上游可用: {CYAN}{len(upstream_models)}{RESET}  |  "
          f"本地已有: {CYAN}{len(local_models)}{RESET}  |  "
          f"别名: {CYAN}{len(alias_names)}{RESET}")
    print()

    if to_add:
        print(f"{GREEN}[+] 新增 ({len(to_add)}):{RESET}")
        for m in to_add:
            print(f"    {GREEN}+ {m}{RESET}")
    else:
        print(f"{DIM}[+] 无新增{RESET}")

    print()

    if to_remove:
        print(f"{RED}[-] 删除 ({len(to_remove)}):{RESET}")
        for m in to_remove:
            print(f"    {RED}- {m}{RESET}")
    else:
        print(f"{DIM}[-] 无删除{RESET}")

    print()

    if to_keep_alias:
        print(f"{YELLOW}[=] 保留别名/映射目标 ({len(to_keep_alias)}):{RESET}")
        for m in sorted(to_keep_alias):
            label = "别名" if m in alias_names else "映射目标"
            print(f"    {YELLOW}~ {m} ({label}){RESET}")

    if mapping_to_remove:
        print(f"\n{RED}[~] 清理映射 ({len(mapping_to_remove)}):{RESET}")
        for k, v in mapping_to_remove:
            print(f"    {RED}~ {k} -> {v}{RESET}")

    # ── 执行更新 ──────────────────────────────────────────────
    if args.dry_run:
        print(f"\n{YELLOW}(--dry-run 模式，未执行更新){RESET}")
        return

    if not to_add and not to_remove and not mapping_to_remove:
        print(f"\n{GREEN}模型列表无变化，无需更新。{RESET}")
        return

    # 构建新的 models 列表
    final_models = []
    for m in local_models:
        if m not in to_remove:
            final_models.append(m)
    final_models.extend(to_add)
    final_models_str = ",".join(final_models)

    # 构建新的 mapping
    new_mapping = dict(mapping)
    for k, v in mapping_to_remove:
        del new_mapping[k]
    new_mapping_str = json.dumps(new_mapping, ensure_ascii=False)

    # 保留其他字段不变，只更新 models 和 model_mapping
    print(f"\n{BOLD}正在更新渠道...{RESET}")
    update_channel(base_url, admin_key, admin_user, args.channel_id,
                   final_models_str, new_mapping_str)
    print(f"{GREEN}✓ 更新成功！{RESET}")

    # 最终统计
    print(f"\n{BOLD}=== 最终状态 ==={RESET}")
    print(f"模型总数: {CYAN}{len(final_models)}{RESET}")
    if args.verbose:
        for m in sorted(final_models):
            tag = ""
            if m in alias_names:
                tag = f" {DIM}(别名){RESET}"
            elif m in to_add:
                tag = f" {GREEN}(新增){RESET}"
            print(f"  {m}{tag}")


if __name__ == "__main__":
    main()
