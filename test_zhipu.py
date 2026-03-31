#!/usr/bin/env python3
"""
智谱 BigModel API 测试脚本
测试渠道配置是否正确
"""

import requests
import json

# ==================== 配置参数 (从数据库读取) ====================
API_KEY = "6219676c932e49afaaefab73c354d325.Jq9Roo03IrzbKyOt"
BASE_URL = "https://open.bigmodel.cn"

# 智谱支持的模型列表
MODELS_TO_TEST = [
    "glm-4-flash",      # 快速版
    "glm-4",            # 标准版
    "glm-4-plus",       # 增强版
    "glm-4-air",        # 空气版
    "glm-4-airx",       # 空气X版
    "glm-4-long",       # 长文本版
    "glm-4v",           # 视觉版
    "glm-4v-plus",      # 视觉增强版
]

# ==================== API 端点 ====================
# OpenAI 兼容接口 (推荐)
OPENAI_COMPAT_URL = f"{BASE_URL}/api/paas/v4/chat/completions"

# 智谱原生接口
NATIVE_URL_TEMPLATE = f"{BASE_URL}/api/paas/v3/model-api/{{model}}/invoke"

# ==================== 测试函数 ====================

def test_openai_compatible(model="glm-4-flash"):
    """测试 OpenAI 兼容接口"""
    print(f"\n{'='*60}")
    print(f"测试 OpenAI 兼容接口: {model}")
    print(f"URL: {OPENAI_COMPAT_URL}")
    print(f"{'='*60}")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "你好，请用一句话介绍自己"}
        ],
        "max_tokens": 100,
        "temperature": 0.7
    }

    try:
        response = requests.post(
            OPENAI_COMPAT_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")

        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ 成功!")
            print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return True
        else:
            print(f"\n❌ 失败!")
            print(f"错误响应: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ 请求异常: {str(e)}")
        return False


def test_native_api(model="glm-4-flash"):
    """测试智谱原生接口"""
    url = NATIVE_URL_TEMPLATE.format(model=model)
    print(f"\n{'='*60}")
    print(f"测试智谱原生接口: {model}")
    print(f"URL: {url}")
    print(f"{'='*60}")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "你好"}
        ],
        "max_tokens": 50
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"\n✅ 成功!")
            print(f"响应: {json.dumps(result, ensure_ascii=False, indent=2)}")
            return True
        else:
            print(f"\n❌ 失败!")
            print(f"错误响应: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ 请求异常: {str(e)}")
        return False


def test_api_key_validity():
    """测试 API Key 有效性"""
    print(f"\n{'='*60}")
    print("测试 API Key 有效性")
    print(f"{'='*60}")
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:]}")
    print(f"API Key 长度: {len(API_KEY)}")

    # 检查 API Key 格式
    if "." in API_KEY:
        parts = API_KEY.split(".")
        print(f"API Key 格式: id.signature")
        print(f"  - ID 部分: {parts[0]}")
        print(f"  - Signature 部分: {parts[1][:5]}...")
    else:
        print(f"API Key 格式: 单一 token")


def main():
    print("=" * 60)
    print("智谱 BigModel API 测试脚本")
    print("=" * 60)

    # 显示配置
    print(f"\n配置信息:")
    print(f"  BASE_URL: {BASE_URL}")
    print(f"  API_KEY: {API_KEY[:10]}...{API_KEY[-10:]}")

    # 测试 API Key 格式
    test_api_key_validity()

    # 测试 OpenAI 兼容接口 (使用最常用的模型)
    print("\n" + "=" * 60)
    print("开始测试 API 调用...")
    print("=" * 60)

    # 测试几个常用模型
    test_models = ["glm-4-flash", "glm-4", "glm-4-plus"]

    for model in test_models:
        success = test_openai_compatible(model)
        if success:
            print(f"\n✅ 模型 {model} 测试通过!")
            break  # 只要有一个成功就停止
        else:
            print(f"\n❌ 模型 {model} 测试失败，尝试下一个...")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
