#!/usr/bin/env python3
"""
令牌模型管理脚本 —— 通过 new-api API 管理令牌的 model_limits（可用模型）。

用法:
  # 查看令牌当前模型列表
  python3 token_models.py show --id 148

  # 给令牌添加模型（追加，去重）
  python3 token_models.py add --id 148 --models gpt-5.3-codex,mimo-v2.5-pro

  # 从令牌移除模型
  python3 token_models.py remove --id 148 --models gpt-5.3-codex

  # 覆盖设置（替换为指定列表）
  python3 token_models.py set --id 148 --models gpt-5.3-codex,mimo-v2.5-pro

  # 带 name 参数也可以（仅用于显示确认，不参与匹配）
  python3 token_models.py show --id 148 --name oversea-260607-2232

  # 查看 API 脱敏结果（模拟）
  python3 token_models.py mask bSgP7jxeURoTVfuXMacBb80V6W0tLEF0zmPFl6jeTqALxxhf
"""

import os, sys, json, argparse, subprocess

# ── 读取凭据 ──────────────────────────────────────────────
def load_env():
    env_path = '/opt/new-api/.env'
    env = {}
    try:
        for line in open(env_path):
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    except FileNotFoundError:
        print(f'错误: {env_path} 不存在'); sys.exit(1)

    raw_url = env.get('new_admin_url', '')
    admin_key = env.get('new_admin_key', '')
    admin_user = env.get('New-Api-User', '1')

    if not raw_url or not admin_key:
        print('错误: .env 中缺少 new_admin_url 或 new_admin_key'); sys.exit(1)

    base = raw_url.rstrip('/')
    if base.endswith('/channel'): base = base[:-8]
    if not base.endswith('/api'): base += '/api'

    return base, admin_key, admin_user

def api_get(base, key, user, path, params=None):
    url = f'{base}{path}'
    if params:
        url += '?' + '&'.join(f'{k}={v}' for k, v in params.items())
    r = subprocess.run(
        ['curl', '-s', '-H', f'Authorization: Bearer {key}',
         '-H', f'New-Api-User: {user}', url],
        capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

def api_put(base, key, user, path, data):
    url = f'{base}{path}'
    r = subprocess.run(
        ['curl', '-s', '-X', 'PUT',
         '-H', 'Content-Type: application/json',
         '-H', f'Authorization: Bearer {key}',
         '-H', f'New-Api-User: {user}',
         '-d', json.dumps(data), url],
        capture_output=True, text=True, timeout=15)
    return json.loads(r.stdout)

# ── 脱敏规则（与后端一致） ──────────────────────────────
def mask_token_key(key: str) -> str:
    """模拟 model/token.go MaskTokenKey"""
    if not key:
        return ''
    if len(key) <= 4:
        return '*' * len(key)
    if len(key) <= 8:
        return key[:2] + '****' + key[-2:]
    return key[:4] + '**********' + key[-4:]

# ── 令牌操作 ──────────────────────────────────────────────
def get_token(base, key, user, token_id):
    """通过 API 获取单个令牌详情"""
    return api_get(base, key, user, f'/token/{token_id}')

def update_token_models(base, key, user, token_id, models_str, enabled=True):
    """通过 API 更新令牌的 model_limits"""
    data = {
        'id': token_id,
        'model_limits': models_str,
        'model_limits_enabled': enabled,
    }
    return api_put(base, key, user, '/token/', data)

# ── CLI ─────────────────────────────────────────────────────
def cmd_show(args):
    base, akey, auser = load_env()
    print(f'查询令牌 ID={args.id} ...')
    res = get_token(base, akey, auser, args.id)
    if not res.get('success'):
        print('失败:', res.get('message', '未知错误'))
        sys.exit(1)
    t = res['data']
    print()
    print(f'  ID:       {t["id"]}')
    print(f'  Name:     {t.get("name", "(空)")}')
    print(f'  Key:      {t.get("key", "(无)")}')
    print(f'  Status:   {"启用" if t.get("status") == 1 else "禁用/过期"}')
    print(f'  模型限制: {t.get("model_limits", "(无)") or "(无)"}')
    print(f'  限制启用: {"是" if t.get("model_limits_enabled") else "否"}')
    print(f'  分组:     {t.get("group", "default")}')
    print(f'  剩余额度: {t.get("remain_quota", "?")}')
    print(f'  无限额度: {"是" if t.get("unlimited_quota") else "否"}')
    print(f'  过期时间: {t.get("expired_time", -1)}')

def cmd_add(args):
    base, akey, auser = load_env()
    # 先获取当前模型
    res = get_token(base, akey, auser, args.id)
    if not res.get('success'):
        print('获取令牌失败:', res.get('message', '')); sys.exit(1)
    current = res['data'].get('model_limits', '') or ''
    current_set = set(m.strip() for m in current.split(',') if m.strip())

    new_models = [m.strip() for m in args.models.split(',') if m.strip()]
    before = len(current_set)
    current_set.update(new_models)
    added = [m for m in new_models if m not in current_set or (m in current_set and m not in current.split(','))]

    if len(current_set) == before and not added:
        print(f'令牌 ID={args.id} 已有全部指定模型，无需变更')
        return

    models_str = ','.join(sorted(current_set, key=lambda x: (current_set != x, x)))
    print(f'令牌 ID={args.id}  名称={res["data"].get("name","?")}')
    print(f'  添加: {", ".join(new_models)}')
    print(f'  当前模型列表: {models_str}')
    if args.yes:
        confirm = 'y'
    else:
        confirm = input('确认更新? [Y/n] ') or 'y'
    if confirm.lower() != 'y':
        print('已取消'); return

    result = update_token_models(base, akey, auser, args.id, models_str)
    if result.get('success'):
        print(f'✅ 已更新，共 {len(current_set)} 个模型')
    else:
        print('❌ 失败:', result.get('message', ''))

def cmd_remove(args):
    base, akey, auser = load_env()
    res = get_token(base, akey, auser, args.id)
    if not res.get('success'):
        print('获取令牌失败:', res.get('message', '')); sys.exit(1)
    current = res['data'].get('model_limits', '') or ''
    current_list = [m.strip() for m in current.split(',') if m.strip()]

    remove_set = set(m.strip() for m in args.models.split(',') if m.strip())
    new_list = [m for m in current_list if m not in remove_set]
    removed = [m for m in current_list if m in remove_set]

    if not removed:
        print(f'令牌 ID={args.id} 中没有这些模型: {", ".join(remove_set)}')
        return

    models_str = ','.join(new_list)
    print(f'令牌 ID={args.id}  名称={res["data"].get("name","?")}')
    print(f'  移除: {", ".join(removed)}')
    print(f'  剩余模型: {models_str or "(空)"}')
    if args.yes:
        confirm = 'y'
    else:
        confirm = input('确认更新? [Y/n] ') or 'y'
    if confirm.lower() != 'y':
        print('已取消'); return

    result = update_token_models(base, akey, auser, args.id, models_str)
    if result.get('success'):
        print(f'✅ 已更新，剩余 {len(new_list)} 个模型')
    else:
        print('❌ 失败:', result.get('message', ''))

def cmd_set(args):
    base, akey, auser = load_env()
    models_list = [m.strip() for m in args.models.split(',') if m.strip()]
    models_str = ','.join(models_list)

    print(f'令牌 ID={args.id}')
    print(f'  设置模型: {models_str or "(空——清除所有限制)"}')
    if args.yes:
        confirm = 'y'
    else:
        confirm = input('确认覆盖? [Y/n] ') or 'y'
    if confirm.lower() != 'y':
        print('已取消'); return

    result = update_token_models(base, akey, auser, args.id, models_str,
                                  enabled=args.enabled if models_str else False)
    if result.get('success'):
        print(f'✅ 已覆盖，共 {len(models_list)} 个模型')
    else:
        print('❌ 失败:', result.get('message', ''))

def cmd_mask(args):
    print(f'原始: {args.key}')
    print(f'脱敏: {mask_token_key(args.key)}')

# ── 入口 ──────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='令牌模型管理 —— 通过 new-api API 管理令牌的 model_limits')
    sub = parser.add_subparsers(dest='cmd', required=True)

    # show
    p_show = sub.add_parser('show', help='查看令牌信息')
    p_show.add_argument('--id', type=int, required=True, help='令牌 ID')

    # add
    p_add = sub.add_parser('add', help='追加模型（去重）')
    p_add.add_argument('--id', type=int, required=True, help='令牌 ID')
    p_add.add_argument('--models', type=str, required=True, help='模型名，逗号分隔')
    p_add.add_argument('--yes', '-y', action='store_true', help='跳过确认')

    # remove
    p_rem = sub.add_parser('remove', help='移除模型')
    p_rem.add_argument('--id', type=int, required=True, help='令牌 ID')
    p_rem.add_argument('--models', type=str, required=True, help='模型名，逗号分隔')
    p_rem.add_argument('--yes', '-y', action='store_true', help='跳过确认')

    # set
    p_set = sub.add_parser('set', help='覆盖设置模型列表')
    p_set.add_argument('--id', type=int, required=True, help='令牌 ID')
    p_set.add_argument('--models', type=str, required=True, help='模型名，逗号分隔')
    p_set.add_argument('--yes', '-y', action='store_true', help='跳过确认')
    p_set.add_argument('--enabled', action='store_true', default=True,
                       help='启用模型限制（默认开启）')

    # mask
    p_mask = sub.add_parser('mask', help='模拟令牌 key 脱敏，查看匹配效果')
    p_mask.add_argument('key', type=str, help='完整令牌 key')

    args = parser.parse_args()
    cmds = {'show': cmd_show, 'add': cmd_add, 'remove': cmd_remove,
            'set': cmd_set, 'mask': cmd_mask}
    cmds[args.cmd](args)

if __name__ == '__main__':
    main()
