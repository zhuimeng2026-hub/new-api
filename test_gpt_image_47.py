#!/usr/bin/env python3
"""Test gpt-image-2 for User 47 via new-api gateway."""
import os, sys, json, base64, time
import urllib.request, urllib.error

TOKEN = "sk-KApgyBMY1NY9ERxhiNkvpjRAF7KuSqkQOnpslYFQ7sYnWE63"
MODEL = "gpt-image-2"
BASE = os.environ.get("NEW_API_BASE", "https://aikey.aixifs.com")
PROMPT = "a cute cat sitting on a wooden table, warm sunlight, photorealistic"

body = json.dumps({
    "model": MODEL,
    "prompt": PROMPT,
    "n": 1,
    "size": "1024x1024"
}).encode("utf-8")

url = f"{BASE}/v1/images/generations"
print(f"URL: {url}")
print(f"Model: {MODEL}")
print(f"Token: {TOKEN[:20]}...{TOKEN[-8:]}")
print(f"Prompt: {PROMPT}")
print()

req = urllib.request.Request(url, data=body, headers={
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
})

try:
    start = time.time()
    resp = urllib.request.urlopen(req, timeout=120)
    elapsed = time.time() - start
    data = json.loads(resp.read().decode("utf-8"))
    print(f"Status: {resp.status} ({elapsed:.1f}s)")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])

    for i, img in enumerate(data.get("data", [])):
        b64 = img.get("b64_json") or img.get("url")
        if b64:
            if b64.startswith("http"):
                print(f"\nImage URL: {b64}")
            else:
                fname = f"gpt_image_test_{i+1}.png"
                with open(fname, "wb") as f:
                    f.write(base64.b64decode(b64))
                print(f"\nSaved: {fname}")

except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8")[:2000]
    print(f"HTTP {e.code}: {body}")
except Exception as e:
    print(f"Error: {e}")
