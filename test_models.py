#!/usr/bin/env python3
"""Test gpt-5.5 and claude-opus-4-7 via new-api gateway."""
import json, time
import urllib.request, urllib.error

BASE_URL = "https://aikey.aixifs.com"
API_KEY = "sk-KApgyBMY1NY9ERxhiNkvpjRAF7KuSqkQOnpslYFQ7sYnWE63"
MODELS = ["gpt-5.5", "claude-opus-4-7"]
MESSAGES = [{"role": "user", "content": "Say hello in exactly 3 words."}]


def test_model(model):
    body = json.dumps({
        "model": model,
        "messages": MESSAGES,
        "max_tokens": 50
    }).encode("utf-8")

    url = f"{BASE_URL}/v1/chat/completions"
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    })

    try:
        start = time.time()
        resp = urllib.request.urlopen(req, timeout=120)
        elapsed = time.time() - start
        data = json.loads(resp.read().decode("utf-8"))
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return True, elapsed, content.strip(), data
    except urllib.error.HTTPError as e:
        return False, 0, f"HTTP {e.code}: {e.read().decode('utf-8')[:500]}", None
    except Exception as e:
        return False, 0, str(e), None


def main():
    print(f"Gateway: {BASE_URL}")
    print(f"API Key: {API_KEY[:20]}...{API_KEY[-10:]}")
    print()

    for model in MODELS:
        print(f"--- Testing {model} ---")
        ok, elapsed, content, raw = test_model(model)
        status = "OK" if ok else "FAIL"
        print(f"  Status: {status} ({elapsed:.1f}s)")
        print(f"  Response: {content}")
        if ok and raw:
            usage = raw.get("usage", {})
            if usage:
                print(f"  Usage: prompt={usage.get('prompt_tokens')}, completion={usage.get('completion_tokens')}, total={usage.get('total_tokens')}")
        print()


if __name__ == "__main__":
    main()
