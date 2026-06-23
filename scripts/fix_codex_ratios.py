#!/usr/bin/env python3
"""
修复 codex 模型的计费倍率配置。
根据 OpenAI 官方定价计算正确的 ModelRatio / CacheRatio / CreateCacheRatio，
通过 PUT /api/option/ 写入 options 表。

CompletionRatio 全部为 8（与硬编码一致），无需覆盖。
"""

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── 配置 ──────────────────────────────────────────────
API_URL = "http://localhost:3000"
ADMIN_KEY = "F139rjKJlV5QQ4wZ1y9NLLCKjifoucU="
ADMIN_USER = "1"

# 参照系: gpt-5 input=$1/M -> ModelRatio=0.625
MR_FACTOR = 0.625

# codex 模型官方定价 ($/M tokens)
CODEX_PRICING = {
    "gpt-5-codex":         {"input": 1.25, "output": 10.0, "cache_read": 0.12},
    "gpt-5.1-codex":       {"input": 1.25, "output": 10.0, "cache_read": 0.12},
    "gpt-5.1-codex-mini":  {"input": 0.25, "output": 2.0,  "cache_read": 0.02},
    "gpt-5.1-codex-max":   {"input": 1.25, "output": 10.0, "cache_read": 0.12},
    "gpt-5.2-codex":       {"input": 1.75, "output": 14.0, "cache_read": 0.17},
    "gpt-5.3-codex":       {"input": 1.75, "output": 14.0, "cache_read": 0.17},
}

# ── API 工具 ──────────────────────────────────────────
def api_get(path):
    req = Request(f"{API_URL}{path}", method="GET")
    req.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    req.add_header("New-Api-User", ADMIN_USER)
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def api_put(path, data):
    body = json.dumps(data).encode()
    req = Request(f"{API_URL}{path}", data=body, method="PUT")
    req.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    req.add_header("New-Api-User", ADMIN_USER)
    req.add_header("Content-Type", "application/json")
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


# ── 获取当前 options ──────────────────────────────────
def get_option_value(key):
    resp = api_get("/api/option/")
    for item in resp["data"]:
        if item["key"] == key:
            return json.loads(item["value"])
    return {}


def update_option(key, value_map):
    return api_put("/api/option/", {"key": key, "value": json.dumps(value_map)})


# ── 主逻辑 ────────────────────────────────────────────
def main():
    # 1. 读取当前三个 ratio map
    print("读取当前配置...")
    mr_map = get_option_value("ModelRatio")
    cr_map = get_option_value("CacheRatio")
    ccr_map = get_option_value("CreateCacheRatio")

    # 2. 计算并展示变更
    print(f"\n{'─' * 78}")
    print(f"  即将写入的 codex 模型倍率")
    print(f"{'─' * 78}")
    print(f"  {'模型':<25} {'ModelRatio':>12} {'CacheRatio':>12} {'CreateCache':>12}")
    print(f"  {'─' * 25} {'─' * 12} {'─' * 12} {'─' * 12}")

    changes = []
    for model, p in CODEX_PRICING.items():
        new_mr = round(p["input"] * MR_FACTOR, 4)
        new_cr = round(p["cache_read"] / p["input"], 4)
        new_ccr = 1.25

        old_mr = mr_map.get(model, "N/A")
        old_cr = cr_map.get(model, "N/A")
        old_ccr = ccr_map.get(model, "N/A")

        mr_mark = " " if old_mr == new_mr else "*"
        cr_mark = " " if old_cr == new_cr else "*"
        ccr_mark = " " if old_ccr == new_ccr else "*"

        print(f"  {model:<25} {new_mr:>11.4f}{mr_mark} {new_cr:>11.4f}{cr_mark} {new_ccr:>11.2f}{ccr_mark}")

        mr_map[model] = new_mr
        cr_map[model] = new_cr
        ccr_map[model] = new_ccr
        changes.append(model)

    print(f"\n  (* 表示有变更)")

    # 3. 确认
    print(f"\n  将更新 {len(changes)} 个模型的 ModelRatio / CacheRatio / CreateCacheRatio")
    print(f"  CompletionRatio 无需更新（硬编码=8，与实际定价一致）")

    answer = input("\n  确认写入? (y/N): ").strip().lower()
    if answer != "y":
        print("  已取消。")
        return

    # 4. 写入
    print("\n写入中...")
    for key, value_map in [("ModelRatio", mr_map), ("CacheRatio", cr_map), ("CreateCacheRatio", ccr_map)]:
        try:
            result = update_option(key, value_map)
            if result.get("success"):
                print(f"  ✅ {key} 更新成功 ({len(value_map)} 个模型)")
            else:
                print(f"  ❌ {key} 更新失败: {result.get('message')}")
        except Exception as e:
            print(f"  ❌ {key} 请求异常: {e}")

    # 5. 验证
    print("\n验证写入结果...")
    mr_verify = get_option_value("ModelRatio")
    cr_verify = get_option_value("CacheRatio")
    ccr_verify = get_option_value("CreateCacheRatio")

    all_ok = True
    for model in changes:
        for key, verify_map in [("ModelRatio", mr_verify), ("CacheRatio", cr_verify), ("CreateCacheRatio", ccr_verify)]:
            if model not in verify_map:
                print(f"  ❌ {model} 的 {key} 未写入")
                all_ok = False

    if all_ok:
        print(f"  ✅ 全部 {len(changes)} 个模型的三个倍率均已写入并验证通过")

    print()


if __name__ == "__main__":
    main()
