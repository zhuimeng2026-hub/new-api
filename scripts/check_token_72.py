import subprocess, json, sys, time
from datetime import datetime, timezone, timedelta

TOKEN_INPUT = '72'

env = {}
for line in open('/opt/new-api/.env'):
    line = line.strip()
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k.strip()] = v.strip()

ADMIN_URL = env.get('new_admin_url', '').rstrip('/')
if ADMIN_URL.endswith('/channel'):
    ADMIN_URL = ADMIN_URL[:-8]
if not ADMIN_URL.endswith('/api'):
    ADMIN_URL = ADMIN_URL + '/api'
ADMIN_KEY = env.get('new_admin_key', '')
ADMIN_USER = env.get('New-Api-User', '1')

def api_get(path, params=None):
    url = f'{ADMIN_URL}{path}'
    if params:
        url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
    r = subprocess.run(
        ['curl', '-s', '-H', f'Authorization: Bearer {ADMIN_KEY}',
         '-H', f'New-Api-User: {ADMIN_USER}', url],
        capture_output=True, text=True, timeout=15
    )
    return json.loads(r.stdout)

now = int(time.time())
tz = timezone(timedelta(hours=8))
errors, warnings, info = [], []

def ts_to_str(ts):
    try: return datetime.fromtimestamp(ts, tz=tz).strftime('%Y-%m-%d %H:%M:%S')
    except: return str(ts)

token_id = int(TOKEN_INPUT)

# 获取详情
resp = api_get(f'/token/{token_id}')
if not resp.get('success') or not resp.get('data'):
    print('令牌不存在'); sys.exit(0)

t = resp['data']
t_id, t_name, t_key = t['id'], t.get('name',''), t.get('key','')
t_status, t_uid, t_group = t.get('status',0), t.get('user_id',0), t.get('group','')
t_exp, t_remain, t_used = t.get('expired_time',-1), t.get('remain_quota',0), t.get('used_quota',0)
t_unlimited = t.get('unlimited_quota', False)
t_deleted = t.get('DeletedAt')
t_mle, t_ml = t.get('model_limits_enabled',False), t.get('model_limits','')

info.append(f'ID={t_id}  名称={t_name or "(空)"}  用户ID={t_uid}')
info.append(f'Key={t_key}')

# 用户信息
try:
    ur = api_get(f'/user/{t_uid}')
    if ur.get('success') and ur.get('data'):
        u = ur['data']
        info[0] = f'ID={t_id}  名称={t_name or "(空)"}  用户={u.get("username","")} (ID={t_uid})'
        info.append(f'用户额度={u.get("quota",0):,}')
except: pass

# 渠道列表
channels = []
try:
    cr = api_get('/channel/', {'p':'0','size':'200'})
    if cr.get('success') and cr.get('data'):
        items = cr['data'].get('items',[]) if isinstance(cr['data'],dict) else cr['data']
        for ch in (items if isinstance(items,list) else []):
            if ch.get('status') == 1: channels.append(ch)
except: pass

# 诊断
if t_deleted: errors.append('已软删除')

status_map = {1:'启用',2:'禁用',3:'过期',4:'额度耗尽'}
sn = status_map.get(t_status, f'未知({t_status})')
if t_status != 1: errors.append(f'状态: {sn}')
else: info.append(f'状态: {sn}')

if t_exp == -1: info.append('过期: 永不过期')
elif t_exp == 0: errors.append('expired_time=0 (1970过期)')
elif t_exp < now: errors.append(f'已过期 {(now-t_exp)//86400} 天')
else:
    days = (t_exp - now) // 86400
    (warnings if days <= 7 else info).append(f'过期: {ts_to_str(t_exp)} (还有{days}天)')

if t_unlimited: info.append('额度: 无限')
elif t_remain <= 0: errors.append(f'额度耗尽 (remain={t_remain})')
else: info.append(f'额度: {t_remain:,} (${t_remain/500000:.2f})')

info.append(f'group="{t_group or "(空)"}"')

# 渠道匹配
token_group = t_group or ''
allowed = {m.strip() for m in t_ml.split(',') if m.strip()} if t_mle and t_ml else set()
if allowed:
    mc_map = {}
    matched_ch_ids = set()
    for m in allowed:
        mc_map[m] = [ch for ch in channels
                     if m in {x.strip() for x in ch.get('models','').split(',')}
                     and (not token_group or not ch.get('group') or ch['group']==token_group)]
        for ch in mc_map[m]: matched_ch_ids.add(ch['id'])
    no_ch = [m for m, cs in mc_map.items() if not cs]
    if no_ch:
        errors.append(f'无渠道模型: {", ".join(no_ch)}')
    else:
        info.append(f'{len(allowed)}个模型均有渠道')
        for m, cs in mc_map.items():
            best = max(cs, key=lambda c: c.get('priority', 0))
            info.append(f'  {m} -> [{best.get("priority",0)}] {best.get("name","")}')
        info.append('匹配渠道详情:')
        for cid in matched_ch_ids:
            ch = next((c for c in channels if c['id'] == cid), None)
            if ch:
                info.append(f'  [{ch["id"]}] {ch.get("name","")}  优先级={ch.get("priority",0)}  模型={ch.get("models","")}')
else:
    mc = [ch for ch in channels if not token_group or not ch.get('group') or ch['group']==token_group]
    if mc:
        info.append(f'group="{token_group}" 匹配 {len(mc)} 个渠道:')
        for ch in mc:
            info.append(f'  [{ch["id"]}] {ch.get("name","")}  优先级={ch.get("priority",0)}  模型={ch.get("models","")}')
    else:
        errors.append(f'group="{token_group}" 无匹配渠道')

# === 输出 ===
print('='*50)
print('  令牌诊断报告')
print('='*50)
for i in info: print(f'  {i}')
if errors:
    print(f'\n错误 ({len(errors)}):')
    for e in errors: print(f'  X {e}')
if warnings:
    print(f'\n警告:')
    for w in warnings: print(f'  ! {w}')
if not errors:
    print(f'\n全部通过')
else:
    print(f'\n修复建议:')
    if t_exp == 0 or (t_exp != -1 and t_exp < now):
        print(f'  PUT {ADMIN_URL}/token/ {{"id":{t_id},"expired_time":-1}}')
    if not t_unlimited and t_remain <= 0:
        print(f'  PUT {ADMIN_URL}/token/ {{"id":{t_id},"remain_quota":5000000}}')
