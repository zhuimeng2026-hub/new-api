#!/usr/bin/env python3
"""
备份 new-api options 表，重点展示四个模型的计费倍率配置。
同时导出全部 options 数据为 JSON 文件。
"""

import json
import sys
import os
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── 配置 ──────────────────────────────────────────────
API_URL = os.getenv("NEW_API_URL", "http://localhost:3000")
ADMIN_KEY = os.getenv("NEW_ADMIN_KEY", "F139rjKJlV5QQ4wZ1y9NLLCKjifoucU=")
ADMIN_USER = os.getenv("NEW_API_USER", "1")

# 要重点展示的模型
TARGET_MODELS = [
    "claude-opus-4-8",
    "gpt-5.5",
    "gpt-image-2",
    "seedance-2.0",
]

# 四个计费倍率的 option key
RATIO_KEYS = [
    "ModelRatio",
    "CompletionRatio",
    "CacheRatio",
    "CreateCacheRatio",
]

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── API 请求 ──────────────────────────────────────────
def fetch_options():
    """调用 GET /api/option/ 获取全部 options"""
    url = f"{API_URL}/api/option/"
    req = Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {ADMIN_KEY}")
    req.add_header("New-Api-User", ADMIN_USER)
    try:
        with urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            if not body.get("success"):
                print(f"API 返回失败: {body.get('message')}", file=sys.stderr)
                sys.exit(1)
            return body["data"]
    except URLError as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(1)


# ── 主逻辑 ────────────────────────────────────────────
def main():
    options = fetch_options()

    # 构建 key -> value 映射
    opt_map = {item["key"]: item["value"] for item in options}

    # 解析四个倍率 JSON
    ratios = {}
    for key in RATIO_KEYS:
        raw = opt_map.get(key, "{}")
        try:
            ratios[key] = json.loads(raw)
        except json.JSONDecodeError:
            ratios[key] = {}

    # ── 打印头部 ──────────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{'=' * 78}")
    print(f"  new-api Options 备份报告  |  {now}")
    print(f"{'=' * 78}")
    print(f"  共 {len(options)} 条配置项\n")

    # ── 四个模型的倍率详情 ──────────────────────────────
    print(f"{'─' * 78}")
    print(f"  重点模型计费倍率")
    print(f"{'─' * 78}")

    # 表头
    header = f"  {'模型':<28} {'ModelRatio':>12} {'Completion':>12} {'CacheRatio':>12} {'CreateCache':>12}"
    print(header)
    print(f"  {'─' * 28} {'─' * 12} {'─' * 12} {'─' * 12} {'─' * 12}")

    # 默认回退值
    DEFAULTS = {
        "ModelRatio": 37.5,
        "CompletionRatio": 1.0,       # getHardcodedCompletionModelRatio 可能覆盖
        "CacheRatio": 1.0,
        "CreateCacheRatio": 1.25,
    }

    for model in TARGET_MODELS:
        vals = []
        details = []
        for key in RATIO_KEYS:
            ratio_map = ratios[key]
            # 精确匹配
            if model in ratio_map:
                v = ratio_map[model]
                vals.append(f"{v:>12.4f}")
            else:
                # 尝试通配符匹配
                matched = False
                for pattern, v in sorted(ratio_map.items(), key=lambda x: -len(x[0])):
                    import fnmatch
                    if fnmatch.fnmatch(model, pattern):
                        vals.append(f"{v:>12.4f} (wildcard: {pattern})")
                        matched = True
                        break
                if not matched:
                    default = DEFAULTS.get(key, "?")
                    vals.append(f"{'N/A':>12}")
                    details.append(f"    ⚠  {key} 未配置，回退默认值 = {default}")

        print(f"  {model:<28} {''.join(vals)}")
        for d in details:
            print(d)

    # ── 四个倍率的完整 JSON 摘要 ──────────────────────
    print(f"\n{'─' * 78}")
    print(f"  四个倍率配置的模型数量")
    print(f"{'─' * 78}")
    for key in RATIO_KEYS:
        count = len(ratios[key])
        print(f"  {key:<24} : {count} 个模型")

    # 检查目标模型是否缺失配置
    print(f"\n{'─' * 78}")
    print(f"  缺失配置检查")
    print(f"{'─' * 78}")
    all_ok = True
    for model in TARGET_MODELS:
        missing = []
        for key in RATIO_KEYS:
            ratio_map = ratios[key]
            if model not in ratio_map:
                # 检查通配符
                has_wildcard = False
                import fnmatch
                for pattern in ratio_map:
                    if fnmatch.fnmatch(model, pattern):
                        has_wildcard = True
                        break
                if not has_wildcard:
                    missing.append(key)
        if missing:
            all_ok = False
            print(f"  ❌ {model}  缺失: {', '.join(missing)}")
        else:
            print(f"  ✅ {model}  四项完整")

    if all_ok:
        print(f"\n  所有目标模型配置完整，无缺失。")
    else:
        print(f"\n  ⚠  存在缺失配置，需补充后才不会回退到默认值。")

    # ── 导出全部 JSON ──────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(OUTPUT_DIR, f"options_backup_{timestamp}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(options, f, ensure_ascii=False, indent=2)
    print(f"\n{'─' * 78}")
    print(f"  全量 JSON 已导出: {json_path}")
    print(f"{'─' * 78}")

    # 同时导出四个倍率的单独文件
    for key in RATIO_KEYS:
        ratio_path = os.path.join(OUTPUT_DIR, f"{key}_{timestamp}.json")
        with open(ratio_path, "w", encoding="utf-8") as f:
            json.dump(ratios[key], f, ensure_ascii=False, indent=2)
        print(f"  {key} -> {ratio_path}")

    print()


if __name__ == "__main__":
    main()
