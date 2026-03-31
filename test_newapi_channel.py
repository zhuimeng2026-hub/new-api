#!/usr/bin/env python3
"""
通过 new-api 测试智谱渠道
"""

import requests
import json

# new-api 配置
NEW_API_BASE = "http://localhost:3000"

# 测试 1: 直接调用智谱 API (验证 key 有效)
def test_zhipu_direct():
    """直接调用智谱 API"""
    print("=" * 60)
    print("测试 1: 直接调用智谱 API")
    print("=" * 60)

    url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    api_key = "6219676c932e49afaaefab73c354d325.Jq9Roo03IrzbKyOt"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "glm-4-flash",
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 10
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"状态码: {resp.status_code}")
        if resp.status_code == 200:
            print("✅ 智谱 API 直接调用成功")
            print(f"响应: {resp.json()}")
            return True
        else:
            print(f"❌ 智谱 API 直接调用失败")
            print(f"错误: {resp.text}")
            return False
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False


# 测试 2: 通过 new-api 调用智谱
def test_via_newapi():
    """通过 new-api 调用"""
    print("\n" + "=" * 60)
    print("测试 2: 通过 new-api 调用智谱")
    print("=" * 60)

    # 首先获取一个可用的 token
    # 使用 root 用户登录获取 token
    login_url = f"{NEW_API_BASE}/api/user/login"

    # 尝试登录
    login_data = {
        "username": "root",
        "password": "123456"
    }

    session = requests.Session()

    try:
        # 登录
        login_resp = session.post(login_url, json=login_data)
        print(f"登录状态: {login_resp.status_code}")

        if login_resp.status_code != 200:
            print(f"登录失败: {login_resp.text}")
            return False

        login_result = login_resp.json()
        print(f"登录结果: {login_result}")

        # 获取渠道列表
        channels_url = f"{NEW_API_BASE}/api/channel/"
        channels_resp = session.get(channels_url)
        print(f"\n获取渠道列表状态: {channels_resp.status_code}")

        if channels_resp.status_code == 200:
            channels = channels_resp.json()
            print(f"渠道列表: {json.dumps(channels, ensure_ascii=False, indent=2)}")

        # 测试渠道
        test_url = f"{NEW_API_BASE}/api/channel/test/1"
        test_resp = session.get(test_url)
        print(f"\n测试渠道状态: {test_resp.status_code}")
        print(f"测试结果: {test_resp.text}")

        return True

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False


# 测试 3: 使用 API Key 调用 new-api
def test_with_api_key():
    """使用 API Key 调用 new-api"""
    print("\n" + "=" * 60)
    print("测试 3: 创建 Token 并调用 API")
    print("=" * 60)

    session = requests.Session()

    try:
        # 登录
        login_resp = session.post(
            f"{NEW_API_BASE}/api/user/login",
            json={"username": "root", "password": "123456"}
        )

        if login_resp.status_code != 200:
            print(f"登录失败")
            return False

        # 获取现有 tokens
        tokens_resp = session.get(f"{NEW_API_BASE}/api/token/")
        print(f"获取 Tokens: {tokens_resp.status_code}")

        if tokens_resp.status_code == 200:
            tokens_data = tokens_resp.json()
            print(f"Tokens: {json.dumps(tokens_data, ensure_ascii=False, indent=2)}")

            # 如果有 token，用它来调用 API
            if tokens_data.get("success") and tokens_data.get("data"):
                items = tokens_data["data"].get("items", [])
                if items:
                    token_key = items[0].get("key")
                    if token_key:
                        print(f"\n使用 Token: {token_key[:10]}...")

                        # 调用 chat API
                        chat_url = f"{NEW_API_BASE}/v1/chat/completions"
                        chat_headers = {
                            "Authorization": f"Bearer {token_key}",
                            "Content-Type": "application/json"
                        }
                        chat_data = {
                            "model": "glm-4-flash",
                            "messages": [{"role": "user", "content": "hi"}],
                            "max_tokens": 10
                        }

                        chat_resp = requests.post(chat_url, headers=chat_headers, json=chat_data, timeout=60)
                        print(f"\nChat API 状态: {chat_resp.status_code}")
                        print(f"Chat API 响应: {chat_resp.text[:500]}")

        return True

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False


if __name__ == "__main__":
    test_zhipu_direct()
    test_via_newapi()
    test_with_api_key()
