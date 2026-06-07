#!/usr/bin/env python3
"""测试小米MiMo专用令牌 - 验证模型限制是否生效"""

import requests
import json

BASE_URL = "https://aikey.aixifs.com"
TOKEN = "sk-ddbcff964a3258506cea62a6c40ae68d379b9c0490986fb5"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

# 应该通过的模型（小米MiMo-Token-Plan渠道支持）
PASS_MODELS = [
    "mimo-v2.5-pro",
    "MiMo-V2.5-Pro",
    "mimo-v2.5",
    "MiMo-V2.5",
    "mimo-v2-pro",
    "mimo-v2-omni",
    "mimo-v2-flash",
    "mengxa-pay",
]

# 应该被拒绝的模型（不属于小米渠道）
FAIL_MODELS = [
    "gpt-4o",
    "claude-sonnet-4-5",
    "deepseek-chat",
    "qwen-max",
    "glm-4-plus",
]


def test_model(model: str, expect_pass: bool) -> bool:
    """测试单个模型，返回是否符合预期"""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/v1/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=30,
        )
        data = resp.json()
        success = data.get("choices") is not None
        error_msg = data.get("error", {}).get("message", "") if not success else ""

        passed = (success == expect_pass)
        status = "✅" if passed else "❌"
        detail = f"HTTP {resp.status_code}"
        if not success and error_msg:
            detail += f" | {error_msg[:80]}"

        print(f"  {status} {model:<30} {'通过' if success else '拒绝':<6}  {detail}")
        return passed

    except Exception as e:
        print(f"  ❌ {model:<30} 异常: {e}")
        return False


def main():
    print("=" * 70)
    print("小米MiMo专用令牌 模型限制测试")
    print(f"令牌: {TOKEN[:12]}...{TOKEN[-4:]}")
    print("=" * 70)

    results = []

    print("\n📌 应该通过的模型（小米渠道支持）:")
    for model in PASS_MODELS:
        results.append(test_model(model, expect_pass=True))

    print("\n📌 应该被拒绝的模型（不属于小米渠道）:")
    for model in FAIL_MODELS:
        results.append(test_model(model, expect_pass=False))

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 70)
    print(f"结果: {passed}/{total} 符合预期")
    if passed == total:
        print("🎉 全部通过！模型限制生效。")
    else:
        print("⚠️  存在不符合预期的项，请检查。")
    print("=" * 70)


if __name__ == "__main__":
    main()
