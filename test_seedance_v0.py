#!/usr/bin/env python3
"""seedance 2.0 视频生成测试"""

import requests
import time
import os

BASE_URL = "https://aikey.aixifs.com"
TOKEN = "8PVg6IMq4Zm5k0kX0GUMGP2yXbaUgVUQd8gvzMD5Yf3xl386"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# 提交任务
resp = requests.post(f"{BASE_URL}/v1/videos", headers=HEADERS, json={
    "model": "doubao-seedance-2-0",
    "prompt": "A golden retriever playing in autumn leaves in a park, cinematic lighting",
    "duration": 5,
    "ratio": "16:9",
    "resolution": "720p",
}, timeout=30)
data = resp.json()
task_id = data.get("id", "")
print(f"任务: {task_id}")

# 轮询状态
for _ in range(30):
    time.sleep(10)
    r = requests.get(f"{BASE_URL}/v1/videos/{task_id}", headers=HEADERS, timeout=15).json()
    status = r.get("status", "")
    print(f"  {status}")
    if status in ("completed", "succeeded"):
        # 下载视频
        output = f"seedance_{int(time.time())}.mp4"
        vr = requests.get(f"{BASE_URL}/v1/videos/{task_id}/content", headers=HEADERS, timeout=60)
        if vr.status_code == 200:
            with open(output, "wb") as f:
                f.write(vr.content)
            print(f"已保存: {output} ({os.path.getsize(output)/1024:.0f} KB)")
        print(f"tokens: {r.get('usage', {})}")
        break
    if status in ("failed", "error"):
        print(f"失败: {r.get('fail_reason', '')}")
        break
