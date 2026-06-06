#!/usr/bin/env python3
"""seedance 2.0 视频生成测试"""

import requests
import time
import os
import urllib3
urllib3.disable_warnings()

BASE_URL = "https://aikey.aixifs.com"
TOKEN = "8PVg6IMq4Zm5k0kX0GUMGP2yXbaUgVUQd8gvzMD5Yf3xl386"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

session = requests.Session()
session.verify = False

def api(method, path, **kwargs):
    for i in range(3):
        try:
            r = session.request(method, f"{BASE_URL}{path}", headers=HEADERS, timeout=30, **kwargs)
            return r.json()
        except Exception as e:
            print(f"  重试 {i+1}: {e}")
            time.sleep(2)
    return {}

# 提交任务
print("提交任务...")
data = api("POST", "/v1/videos", json={
    "model": "doubao-seedance-2.0",
    "prompt": "A golden retriever playing in autumn leaves in a park, cinematic lighting",
    "duration": 5,
    "ratio": "16:9",
    "resolution": "720p",
})
print(data)
task_id = data.get("id") or data.get("task_id", "")
if not task_id:
    print("创建失败")
    exit(1)
print(f"任务: {task_id}")

# 轮询状态
for i in range(30):
    time.sleep(10)
    r = api("GET", f"/v1/videos/{task_id}")
    status = r.get("status", "")
    print(f"  [{i+1}] {status}")
    if status in ("completed", "succeeded"):
        output = f"seedance_{int(time.time())}.mp4"
        vr = session.get(f"{BASE_URL}/v1/videos/{task_id}/content", headers=HEADERS, timeout=60)
        if vr.status_code == 200:
            with open(output, "wb") as f:
                f.write(vr.content)
            print(f"已保存: {output} ({os.path.getsize(output)/1024:.0f} KB)")
        print(f"tokens: {r.get('usage', {})}")
        break
    if status in ("failed", "error"):
        print(f"失败: {r.get('fail_reason', '')}")
        break
