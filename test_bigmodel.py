#!/usr/bin/env python3
"""Test BigModel (Zhipu AI) API availability using BIG_MODEL_KEY from .env file."""

import json
import os
import sys
import time
import jwt
import requests

API_BASE = "https://open.bigmodel.cn/api/paas/v4"
MODEL = "glm-4-flash"  # Free model for testing


def load_key_from_env():
    """Load BIG_MODEL_KEY from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    key = os.environ.get("BIG_MODEL_KEY")
    if not key and os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("BIG_MODEL_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    break
    if not key:
        print("ERROR: BIG_MODEL_KEY not found in .env or environment")
        sys.exit(1)
    return key


def generate_token(api_key: str) -> str:
    """Generate JWT token from Zhipu API key (id.secret format)."""
    parts = api_key.split(".")
    if len(parts) != 2:
        print(f"ERROR: Invalid key format, expected 'id.secret', got: {api_key[:10]}...")
        sys.exit(1)

    api_id, secret = parts
    now_ms = int(time.time() * 1000)
    exp_ms = now_ms + 3600 * 1000  # 1 hour

    payload = {
        "api_key": api_id,
        "exp": exp_ms,
        "timestamp": now_ms,
    }
    headers = {
        "alg": "HS256",
        "sign_type": "SIGN",
    }
    token = jwt.encode(payload, secret, algorithm="HS256", headers=headers)
    return token


def test_chat(token: str):
    """Test chat completion API."""
    url = f"{API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": "Say 'hello' in one word."},
        ],
        "max_tokens": 16,
    }

    print(f"Testing: POST {url}")
    print(f"  Model: {MODEL}")
    resp = requests.post(url, headers=headers, json=payload, timeout=30)

    print(f"  Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"  Response: {resp.text}")
        return False

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    usage = data.get("usage", {})
    print(f"  Reply: {content.strip()}")
    print(f"  Usage: prompt_tokens={usage.get('prompt_tokens')}, completion_tokens={usage.get('completion_tokens')}")
    return True


def test_models(token: str):
    """Test models list API."""
    url = f"{API_BASE}/models"
    headers = {"Authorization": f"Bearer {token}"}

    print(f"\nTesting: GET {url}")
    resp = requests.get(url, headers=headers, timeout=15)
    print(f"  Status: {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        models = data.get("data", [])
        model_ids = [m.get("id", "") for m in models]
        print(f"  Available models ({len(model_ids)}): {', '.join(model_ids[:10])}{'...' if len(model_ids) > 10 else ''}")
        return True
    else:
        print(f"  Response: {resp.text}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("BigModel (Zhipu AI) API Test")
    print("=" * 50)

    api_key = load_key_from_env()
    print(f"Key: {api_key[:8]}...{api_key[-4:]}")

    token = generate_token(api_key)
    print(f"JWT Token: {token[:20]}...{token[-8:]}")

    results = []
    print()
    results.append(("Models List", test_models(token)))
    print()
    results.append(("Chat Completion", test_chat(token)))

    print("\n" + "=" * 50)
    print("Results:")
    for name, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
    print("=" * 50)
