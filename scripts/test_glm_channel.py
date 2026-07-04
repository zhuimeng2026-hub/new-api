#!/usr/bin/env python3
"""直接测试 glm 渠道上游各模型可用性"""

import subprocess
import json

env = {}
for line in open('/opt/new-api/scripts/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

BASE_URL = env.get('base_url', '')
API_KEY = env.get('glm_key', '')
MODELS = ['glm-5', 'glm-5-turbo', 'glm-5.1', 'glm-5.2']


def curl_cmd_str(model):
    url = f'{BASE_URL}/v1/chat/completions'
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 5,
        'stream': False,
    })
    return (
        f"curl -s -X POST '{url}' \\\n"
        f"  -H 'Authorization: Bearer {API_KEY}' \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"  -d '{body}'"
    )


def test_model(model):
    url = f'{BASE_URL}/v1/chat/completions'
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi'}],
        'max_tokens': 5,
        'stream': False,
    })
    cmd = [
        'curl', '-s', '-w', '\n%{http_code}', '-X', 'POST', url,
        '-H', f'Authorization: Bearer {API_KEY}',
        '-H', 'Content-Type: application/json',
        '-d', body,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    lines = r.stdout.strip().rsplit('\n', 1)
    body_text = lines[0] if len(lines) > 1 else r.stdout
    status_code = lines[-1] if len(lines) > 1 else '0'

    try:
        data = json.loads(body_text)
    except Exception:
        return status_code, False, f'响应解析失败: {body_text[:200]}'

    if 'error' in data:
        err = data['error']
        return status_code, False, err.get('message', str(err))

    try:
        code_int = int(status_code)
    except Exception:
        code_int = 0
    if code_int >= 400:
        return status_code, False, f'HTTP {status_code}: {body_text[:200]}'

    try:
        reply = data['choices'][0]['message']['content'][:50]
        return status_code, True, reply
    except Exception:
        return status_code, True, '(响应格式正常)'


print(f'=== 测试 glm 渠道上游 {BASE_URL} ===')
print(f'Key: {API_KEY[:12]}...\n')

ok = 0
fail = 0
for m in MODELS:
    code, success, msg = test_model(m)
    if success:
        print(f'  ✅ {m:20s}  HTTP {code}  {msg}')
        ok += 1
    else:
        print(f'  ❌ {m:20s}  HTTP {code}  {msg}')
        print(f'     复现命令:')
        for line in curl_cmd_str(m).split('\n'):
            print(f'     {line}')
        print()
        fail += 1

print(f'\n结果: {ok} 成功, {fail} 失败, 共 {len(MODELS)} 个模型')
