#!/usr/bin/env python3
"""Test gpt-image-2 via new-api gateway. Token 77 (开朋-临时)."""
import os, sys, re, json, base64, time
import urllib.request, urllib.error

# Read credentials from .env
env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
creds = {}
with open(env_file) as f:
    for line in f:
        m = re.match(r'^(new_admin_url|New-Api-User)=(.+)', line.strip())
        if m:
            creds[m.group(1)] = m.group(2)

if "new_admin_url" not in creds:
    print("ERROR: new_admin_url not found in .env")
    sys.exit(1)

# Derive gateway base from admin URL
admin_url = creds["new_admin_url"]
base = re.sub(r'/api/channel/?$', '', admin_url)

TOKEN = "owUTGjjCWbcHYNmAJMh2nVDM6f9qeImLOYcsItHSCgcnaRqq"
MODEL = "gpt-image-2"
PROMPT = "a cute cat sitting on a wooden table, warm sunlight, photorealistic"

body = json.dumps({
    "model": MODEL,
    "prompt": PROMPT,
    "n": 1,
    "size": "1024x1024"
}).encode("utf-8")

url = f"{base}/v1/images/generations"
print(f"URL: {url}")
print(f"Model: {MODEL}")
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

    # If image data returned, save it
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
    print(f"HTTP {e.code}: {e.read().decode('utf-8')[:1000]}")
except Exception as e:
    print(f"Error: {e}")
