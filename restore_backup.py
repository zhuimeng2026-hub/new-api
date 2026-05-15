#!/usr/bin/env python3
"""
Restore backup_newapi_data.json to aikey2.aixifs.com via the new-api API.

Usage: python3 restore_backup.py [--dry-run] [--skip-tokens] [--skip-channels]
"""

import json
import sys
import os
import requests
import argparse
from typing import Any

# Load config from .env
def load_env(path=".env"):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

env = load_env()
BASE_URL = "https://aikey2.aixifs.com"
ADMIN_KEY = env.get("backup_admin_key", "1g5nmQdaHIeC+r5KqkBg+23LiCIF")
USER_HEADER = env.get("New-Api-User", "1")

HEADERS = {
    "Authorization": f"Bearer {ADMIN_KEY}",
    "New-Api-User": USER_HEADER,
    "Content-Type": "application/json",
}

def api_get(path):
    r = requests.get(f"{BASE_URL}{path}", headers=HEADERS, timeout=30)
    return r.json()

def api_post(path, data):
    r = requests.post(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=30)
    try:
        return r.json(), r.status_code
    except:
        return {"success": False, "message": r.text[:200]}, r.status_code

def api_put(path, data):
    r = requests.put(f"{BASE_URL}{path}", headers=HEADERS, json=data, timeout=30)
    try:
        return r.json(), r.status_code
    except:
        return {"success": False, "message": r.text[:200]}, r.status_code

def api_delete(path):
    r = requests.delete(f"{BASE_URL}{path}", headers=HEADERS, timeout=30)
    return r.json(), r.status_code

def main():
    parser = argparse.ArgumentParser(description="Restore backup to new-api")
    parser.add_argument("--dry-run", action="store_true", help="Don't make changes")
    parser.add_argument("--skip-tokens", action="store_true", help="Skip token import")
    parser.add_argument("--skip-channels", action="store_true", help="Skip channel import")
    parser.add_argument("--skip-options", action="store_true", help="Skip options import")
    parser.add_argument("--skip-models", action="store_true", help="Skip models import")
    parser.add_argument("--skip-vendors", action="store_true", help="Skip vendors import")
    parser.add_argument("--skip-abilities", action="store_true", help="Skip abilities import")
    args = parser.parse_args()

    with open("backup_newapi_data.json") as f:
        backup = json.load(f)

    meta = backup.get("_meta", {})
    print(f"Backup exported at: {meta.get('exported_at')}")
    print(f"Source container: {meta.get('container')}")
    print(f"Target: {BASE_URL}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    results = {}

    # ============================================================
    # 1. USERS
    # ============================================================
    print("=" * 60)
    print("1. USERS")
    print("=" * 60)
    existing_users = api_get("/api/user/")
    existing_usernames = {u["username"] for u in existing_users.get("data", {}).get("items", existing_users.get("data", []))}
    # Also get by list
    existing_user_list = existing_users.get("data", {})
    if isinstance(existing_user_list, dict):
        existing_user_list = existing_user_list.get("items", [])
    print(f"  Existing users on target: {len(existing_user_list)} -> {[u['username'] for u in existing_user_list]}")

    created_users = []
    updated_users = []
    for user in backup.get("users", []):
        username = user["username"]
        # Username max 20 chars per model validation
        truncated_username = username[:20]
        if truncated_username != username:
            print(f"  [{username}] Username too long, truncating to '{truncated_username}'")

        if truncated_username in existing_usernames:
            # User exists, update quota/group via PUT
            print(f"  [{truncated_username}] Already exists, updating quota/group...")
            target_user = next((u for u in existing_user_list if u["username"] == truncated_username), None)
            if target_user:
                update_data = {
                    "id": target_user["id"],
                    "username": truncated_username,
                    "password": "12345678",  # placeholder (min=8)
                    "display_name": user.get("display_name", truncated_username)[:20],
                    "role": user.get("role", 1),
                    "status": user.get("status", 1),
                    "quota": user.get("quota", 0),
                    "group": user.get("group", "default"),
                    "aff_code": (user.get("aff_code", "") or "")[:20],
                    "remark": (user.get("remark", "") or "")[:100],
                }
                if not args.dry_run:
                    resp, code = api_put("/api/user/", update_data)
                    if resp.get("success"):
                        print(f"  [{truncated_username}] Updated successfully")
                        updated_users.append(truncated_username)
                    else:
                        print(f"  [{truncated_username}] Update failed: {resp.get('message')}")
        else:
            print(f"  [{truncated_username}] Creating new user (role={user.get('role')})...")
            create_data = {
                "username": truncated_username,
                "password": "12345678",  # default password (min=8)
                "display_name": user.get("display_name", truncated_username)[:20],
                "role": min(user.get("role", 1), 99),  # can't create root user
            }
            if not args.dry_run:
                resp, code = api_post("/api/user/", create_data)
                if resp.get("success"):
                    print(f"  [{truncated_username}] Created successfully")
                    created_users.append(truncated_username)
                    # Now update with quota/group
                    all_users = api_get("/api/user/")
                    all_items = all_users.get("data", {}).get("items", all_users.get("data", []))
                    new_user = next((u for u in all_items if u["username"] == truncated_username), None)
                    if new_user:
                        update_data = {
                            "id": new_user["id"],
                            "username": truncated_username,
                            "password": "12345678",
                            "display_name": user.get("display_name", truncated_username)[:20],
                            "role": min(user.get("role", 1), 99),
                            "status": user.get("status", 1),
                            "quota": user.get("quota", 0),
                            "group": user.get("group", "default"),
                            "aff_code": (user.get("aff_code", "") or "")[:20],
                            "remark": (user.get("remark", "") or "")[:100],
                        }
                        resp2, code2 = api_put("/api/user/", update_data)
                        if resp2.get("success"):
                            print(f"  [{truncated_username}] Quota/group updated")
                        else:
                            print(f"  [{truncated_username}] Quota update failed: {resp2.get('message')}")
                else:
                    print(f"  [{truncated_username}] Create failed: {resp.get('message')}")

    results["users"] = {"created": len(created_users), "updated": len(updated_users)}

    # ============================================================
    # 2. CHANNELS
    # ============================================================
    print()
    print("=" * 60)
    print("2. CHANNELS")
    print("=" * 60)
    if args.skip_channels:
        print("  SKIPPED")
    else:
        existing = api_get("/api/channel/")
        existing_channels = existing.get("data", {}).get("items", [])
        # Build lookup by (name, type) to detect duplicates
        existing_keys = {(c["name"], c["type"]) for c in existing_channels}
        print(f"  Existing channels on target: {len(existing_channels)}")

        created_channels = []
        skipped_channels = []
        for ch in backup.get("channels", []):
            key = (ch["name"], ch["type"])
            if key in existing_keys:
                print(f"  [{ch['name']}] Already exists (type={ch['type']}), skipping")
                skipped_channels.append(ch["name"])
                continue

            print(f"  [{ch['name']}] Creating (type={ch['type']}, priority={ch.get('priority')})...")
            # Build channel payload
            # API expects AddChannelRequest: { "channel": {...} }
            channel_data = {
                "type": ch["type"],
                "key": ch.get("key", ""),
                "open_ai_organization": ch.get("open_ai_organization"),
                "test_model": ch.get("test_model"),
                "status": ch.get("status", 1),
                "name": ch["name"],
                "weight": ch.get("weight", 0),
                "base_url": ch.get("base_url", ""),
                "other": ch.get("other", ""),
                "balance": ch.get("balance", 0),
                "models": ch.get("models", ""),
                "group": ch.get("group", "default"),
                "model_mapping": ch.get("model_mapping", ""),
                "status_code_mapping": ch.get("status_code_mapping", ""),
                "priority": ch.get("priority", 0),
                "auto_ban": ch.get("auto_ban", 1),
                "other_info": ch.get("other_info", ""),
                "tag": ch.get("tag"),
                "setting": ch.get("setting"),
                "param_override": ch.get("param_override"),
                "header_override": ch.get("header_override"),
                "remark": ch.get("remark"),
            }
            if not args.dry_run:
                resp, code = api_post("/api/channel/", {"mode": "single", "channel": channel_data})
                if resp.get("success"):
                    print(f"  [{ch['name']}] Created successfully")
                    created_channels.append(ch["name"])
                else:
                    print(f"  [{ch['name']}] Create failed ({code}): {resp.get('message')}")

        results["channels"] = {"created": len(created_channels), "skipped": len(skipped_channels)}

    # ============================================================
    # 3. OPTIONS
    # ============================================================
    print()
    print("=" * 60)
    print("3. OPTIONS")
    print("=" * 60)
    if args.skip_options:
        print("  SKIPPED")
    else:
        updated_options = []
        for opt in backup.get("options", []):
            key = opt["key"]
            value = opt.get("value", "")
            print(f"  [{key}] Setting value...")
            if not args.dry_run:
                resp, code = api_put("/api/option/", {"key": key, "value": value})
                if resp.get("success"):
                    print(f"  [{key}] Updated successfully")
                    updated_options.append(key)
                else:
                    print(f"  [{key}] Update failed: {resp.get('message')}")
        results["options"] = {"updated": len(updated_options)}

    # ============================================================
    # 4. MODELS
    # ============================================================
    print()
    print("=" * 60)
    print("4. MODELS")
    print("=" * 60)
    if args.skip_models:
        print("  SKIPPED")
    else:
        existing_models_resp = api_get("/api/models/")
        existing_models = existing_models_resp.get("data", {}).get("items", existing_models_resp.get("data", []))
        existing_model_names = {m.get("model_name") for m in existing_models}
        print(f"  Existing models on target: {len(existing_models)}")

        created_models = []
        skipped_models = []
        for m in backup.get("models", []):
            model_name = m.get("model_name", "")
            if model_name in existing_model_names:
                print(f"  [{model_name}] Already exists, skipping")
                skipped_models.append(model_name)
                continue
            print(f"  [{model_name}] Creating...")
            payload = {
                "model_name": model_name,
                "description": m.get("description", ""),
                "icon": m.get("icon", ""),
                "tags": m.get("tags", ""),
                "vendor_id": m.get("vendor_id", 0),
                "endpoints": m.get("endpoints", ""),
                "status": m.get("status", 1),
                "sync_official": m.get("sync_official", False),
                "name_rule": m.get("name_rule", ""),
            }
            if not args.dry_run:
                resp, code = api_post("/api/models/", payload)
                if resp.get("success"):
                    print(f"  [{model_name}] Created successfully")
                    created_models.append(model_name)
                else:
                    print(f"  [{model_name}] Create failed: {resp.get('message')}")
        results["models"] = {"created": len(created_models), "skipped": len(skipped_models)}

    # ============================================================
    # 5. VENDORS
    # ============================================================
    print()
    print("=" * 60)
    print("5. VENDORS")
    print("=" * 60)
    if args.skip_vendors:
        print("  SKIPPED")
    else:
        existing_vendors_resp = api_get("/api/vendors/")
        existing_vendors = existing_vendors_resp.get("data", {}).get("items", existing_vendors_resp.get("data", []))
        existing_vendor_names = {v.get("name") for v in existing_vendors}
        print(f"  Existing vendors on target: {len(existing_vendors)}")

        created_vendors = []
        skipped_vendors = []
        for v in backup.get("vendors", []):
            vendor_name = v.get("name", "")
            if vendor_name in existing_vendor_names:
                print(f"  [{vendor_name}] Already exists, skipping")
                skipped_vendors.append(vendor_name)
                continue
            print(f"  [{vendor_name}] Creating...")
            payload = {
                "name": vendor_name,
                "description": v.get("description", ""),
                "icon": v.get("icon", ""),
                "status": v.get("status", 1),
            }
            if not args.dry_run:
                resp, code = api_post("/api/vendors/", payload)
                if resp.get("success"):
                    print(f"  [{vendor_name}] Created successfully")
                    created_vendors.append(vendor_name)
                else:
                    print(f"  [{vendor_name}] Create failed: {resp.get('message')}")
        results["vendors"] = {"created": len(created_vendors), "skipped": len(skipped_vendors)}

    # ============================================================
    # 6. ABILITIES (channel-model mappings via channel update)
    # ============================================================
    print()
    print("=" * 60)
    print("6. ABILITIES (channel-model mappings)")
    print("=" * 60)
    if args.skip_abilities:
        print("  SKIPPED")
    else:
        # Abilities are managed by updating channels with their models
        # For each channel in backup, update the target channel's models
        bk_channels = {ch["name"]: ch for ch in backup.get("channels", [])}
        target_channels = api_get("/api/channel/").get("data", {}).get("items", [])
        updated_abilities = 0
        for tc in target_channels:
            bk_ch = bk_channels.get(tc["name"])
            if bk_ch and bk_ch.get("models") != tc.get("models"):
                print(f"  [{tc['name']}] Updating models: {bk_ch['models'][:80]}...")
                update_payload = {
                    "id": tc["id"],
                    "type": tc["type"],
                    "key": tc.get("key", ""),
                    "status": tc.get("status", 1),
                    "name": tc["name"],
                    "weight": tc.get("weight", 0),
                    "base_url": tc.get("base_url", ""),
                    "other": tc.get("other", ""),
                    "models": bk_ch.get("models", ""),
                    "group": tc.get("group", "default"),
                    "model_mapping": bk_ch.get("model_mapping", tc.get("model_mapping", "")),
                    "priority": tc.get("priority", 0),
                    "auto_ban": tc.get("auto_ban", 1),
                }
                if not args.dry_run:
                    resp, code = api_put("/api/channel/", update_payload)
                    if resp.get("success"):
                        print(f"  [{tc['name']}] Models updated")
                        updated_abilities += 1
                    else:
                        print(f"  [{tc['name']}] Update failed: {resp.get('message')}")
        results["abilities"] = {"channels_updated": updated_abilities}

    # ============================================================
    # 7. TOKENS
    # ============================================================
    print()
    print("=" * 60)
    print("7. TOKENS")
    print("=" * 60)
    if args.skip_tokens:
        print("  SKIPPED")
    else:
        created_tokens = 0
        failed_tokens = 0
        for token in backup.get("tokens", []):
            token_name = token.get("name", f"token-{token['id']}")
            print(f"  [{token_name}] Creating (quota={token.get('remain_quota')}, unlimited={token.get('unlimited_quota')})...")
            payload = {
                "name": token_name,
                "key": token.get("key", ""),
                "status": token.get("status", 1),
                "expired_time": token.get("expired_time", -1),
                "remain_quota": token.get("remain_quota", 0),
                "unlimited_quota": token.get("unlimited_quota", False),
                "model_limits_enabled": token.get("model_limits_enabled", False),
                "model_limits": token.get("model_limits", ""),
                "allow_ips": token.get("allow_ips", ""),
                "group": token.get("group", "default"),
                "cross_group_retry": token.get("cross_group_retry", False),
            }
            if not args.dry_run:
                resp, code = api_post("/api/token/", payload)
                if resp.get("success"):
                    created_tokens += 1
                    if created_tokens % 10 == 0:
                        print(f"    ... {created_tokens} tokens created so far")
                else:
                    failed_tokens += 1
                    print(f"  [{token_name}] Failed: {resp.get('message')}")
        print(f"  Tokens: {created_tokens} created, {failed_tokens} failed")
        results["tokens"] = {"created": created_tokens, "failed": failed_tokens}

    # ============================================================
    # SUMMARY
    # ============================================================
    print()
    print("=" * 60)
    print("RESTORATION SUMMARY")
    print("=" * 60)
    for table, counts in results.items():
        print(f"  {table}: {counts}")

    # Tables NOT restored via API
    print()
    print("Tables NOT restored (no direct API endpoint):")
    for t in ["setups", "two_fas", "two_fa_backup_codes", "tasks", "quota_data"]:
        count = len(backup.get(t, []))
        if count:
            print(f"  {t}: {count} records (requires direct DB access)")

if __name__ == "__main__":
    main()
