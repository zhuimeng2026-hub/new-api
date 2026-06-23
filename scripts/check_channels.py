#!/usr/bin/env python3
"""直连 + 网关验证 mimo-v2.5-pro-ultraspeed 模型"""

import subprocess, json

MODEL = "mimo-v2.5-pro-ultraspeed"
CH_KEY = "sk-co9ij893u4a07nm3fc4f2aj4921djy1omk9p18d3cu38qokr"
GW_TOKEN = "t7npV6raGbd2f4HOMR4RRi0gsK2MbvPWk5TMs4i8Q9eJ80cG"
GW_URL = "https://aikey.aixifs.com/v1/chat/completions"
UPSTREAM_URL = "https://api.xiaomimimo.com/v1/chat/completions"

PAYLOAD = json.dumps({
    "model": MODEL,
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "用一句话介绍你自己"}],
})

def test(label, url, auth_value):
    print(f"=== {label} ===")
    r = subprocess.run(
        ["curl", "-s", "-w", "\n__HTTP__%{http_code}", "-X", "POST", url,
         "-H", f"Authorization: Bearer {auth_value}",
         "-H", "Content-Type: application/json",
         "-d", PAYLOAD],
        capture_output=True, text=True, timeout=30,
    )
    parts = r.stdout.rsplit("__HTTP__", 1)
    body, http_code = parts[0].strip(), parts[1].strip() if len(parts) > 1 else "?"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"  ❌ HTTP {http_code}  非JSON: {body[:200]}")
        return

    if http_code == "200" and "choices" in data:
        content = data["choices"][0].get("message", {}).get("content", "")
        speed = data.get("usage", {}).get("pd", {}).get("decode_tokens_per_second", "?")
        print(f"  ✅ HTTP {http_code}  speed={speed} t/s")
        print(f"  回复: {content}")
    else:
        err = data.get("error", {})
        print(f"  ❌ HTTP {http_code}  {err.get('message', body[:200])}")
    print()

test("直连上游", UPSTREAM_URL, CH_KEY)
test("通过网关", GW_URL, GW_TOKEN)
