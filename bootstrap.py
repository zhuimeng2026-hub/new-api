#!/usr/bin/env python3
"""
One-click new-api bootstrap: login, create channels, rebuild routing, test, refresh balances.

Two modes:
  Bootstrap  (--channels channels.json) : login → create channels → fix → test → balance
  Reprocess  (no --channels)            : login → fix → test → balance  (existing channels)

Usage:
  python3 bootstrap.py --channels channels.json    # full bootstrap
  python3 bootstrap.py                             # reprocess only (no channel changes)
  python3 bootstrap.py --skip-test                 # skip channel testing
  python3 bootstrap.py --dry-run                   # validate config only

No dependencies beyond Python 3.9+ stdlib.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def api_req(url: str, method: str = "GET", headers: dict | None = None,
            body: dict | None = None, timeout: int = 120) -> dict:
    h = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=h, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else ""
        return {"success": False, "message": f"HTTP {e.code}: {raw}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def load_env(env_path: str) -> dict:
    if not os.path.exists(env_path):
        return {}
    env = {}
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main():
    parser = argparse.ArgumentParser(description="new-api one-click bootstrap / reprocess")
    parser.add_argument("--channels", default=None,
                        help="Path to channel config JSON (omit for reprocess-only mode)")
    parser.add_argument("--env", default=None,
                        help="Path to .env file (default: <script_dir>/.env)")
    parser.add_argument("--base-url", default=None,
                        help="new-api base URL, e.g. https://aikey.aixifs.com")
    parser.add_argument("--admin-key", default=None,
                        help="Admin API key (overrides .env; auto-login if absent)")
    parser.add_argument("--admin-user", default="1",
                        help="New-Api-User header value (default: 1)")
    parser.add_argument("--login-user", default="root",
                        help="Admin username (default: root)")
    parser.add_argument("--login-pass", default="123456",
                        help="Admin password (default: 123456)")
    parser.add_argument("--skip-test", action="store_true",
                        help="Skip channel testing")
    parser.add_argument("--skip-balance", action="store_true",
                        help="Skip balance refresh")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config, show what would be done, then exit")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Resolve base URL ─────────────────────────────────────────────
    env = load_env(args.env or os.path.join(script_dir, ".env"))
    base = args.base_url
    if not base:
        admin_url = env.get("new_admin_url", "")
        base = admin_url.rstrip("/")
        if base.endswith("/api/channel"):
            base = base[: -len("/api/channel")]
        elif base.endswith("/api"):
            base = base[: -len("/api")]
    if not base:
        print("[ERROR] Cannot determine base URL. Set --base-url or new_admin_url in .env")
        sys.exit(1)

    # ── Resolve admin key (auto-login if needed) ─────────────────────
    admin_key = args.admin_key or env.get("new_admin_key", "")
    if not admin_key:
        login_url = f"{base}/api/user/login"
        print(f"[LOGIN] No admin key, auto-login {args.login_user}/{args.login_pass} -> {login_url}")
        if args.dry_run:
            print("[LOGIN] [DRY-RUN] Would login here")
            admin_key = "dry-run-fake-token"
        else:
            resp = api_req(login_url, method="POST",
                           body={"username": args.login_user, "password": args.login_pass},
                           timeout=15)
            if resp.get("success"):
                admin_key = resp["data"]
                print(f"[LOGIN] Token: {admin_key[:16]}...")
            else:
                print(f"[ERROR] Login failed: {resp.get('message', resp)}")
                sys.exit(1)

    headers = {
        "Authorization": f"Bearer {admin_key}",
        "New-Api-User": str(args.admin_user),
        "Content-Type": "application/json",
    }

    # ── Load channel config (optional) ───────────────────────────────
    channels = []
    do_create = args.channels is not None
    if do_create:
        channels_path = args.channels
        if not os.path.exists(channels_path):
            print(f"[ERROR] Channel config not found: {channels_path}")
            sys.exit(1)
        with open(channels_path) as f:
            cfg = json.load(f)
        channels = cfg.get("channels", [])
        if not channels:
            print("[ERROR] Channel config has empty 'channels' array")
            sys.exit(1)
        for i, ch in enumerate(channels):
            missing = [k for k in ("type", "name", "key", "models") if k not in ch]
            if missing:
                print(f"[ERROR] Channel #{i} '{ch.get('name','?')}' missing: {missing}")
                sys.exit(1)

    # ── Header ───────────────────────────────────────────────────────
    mode = "Bootstrap" if do_create else "Reprocess"
    print("=" * 60)
    print(f"  new-api {mode}")
    print(f"  Base URL  : {base}")
    if do_create:
        print(f"  Channels  : {len(channels)} to create")
    print(f"  Dry run   : {args.dry_run}")
    print("=" * 60)

    # ════════════════════════════════════════════════════════════════
    # Step 1: Create channels (bootstrap only)
    # ════════════════════════════════════════════════════════════════
    created, failed = 0, 0
    if do_create:
        url = f"{base}/api/channel/"
        print(f"\n── Creating {len(channels)} channels ──")
        for i, ch in enumerate(channels):
            payload = {
                "mode": "single",
                "channel": {
                    "type": ch["type"],
                    "name": ch["name"],
                    "key": ch["key"],
                    "models": ch["models"],
                    "group": ch.get("group", "default"),
                    "base_url": ch.get("base_url", ""),
                    "priority": ch.get("priority", 0),
                    "weight": ch.get("weight", 0),
                    "status": ch.get("status", 1),
                    "model_mapping": json.dumps(ch.get("model_mapping", {}), ensure_ascii=False) if ch.get("model_mapping") else "",
                },
            }
            label = f"{i+1}/{len(channels)} {ch['name']}"
            if args.dry_run:
                print(f"  [DRY-RUN] {label} (type={ch['type']})")
                created += 1
                continue
            start = time.time()
            resp = api_req(url, method="POST", headers=headers, body=payload, timeout=30)
            elapsed = time.time() - start
            if resp.get("success"):
                created += 1
                print(f"  OK  {label} ({elapsed:.1f}s)")
            else:
                failed += 1
                print(f"  FAIL {label} — {str(resp.get('message', resp))[:120]}")
        print(f"\n  Created: {created}  Failed: {failed}")

    # ════════════════════════════════════════════════════════════════
    # Step 2: Fix abilities
    # ════════════════════════════════════════════════════════════════
    print(f"\n── Rebuild abilities table (POST /api/channel/fix) ──")
    if args.dry_run:
        print("  [DRY-RUN] Would call fix")
    else:
        start = time.time()
        resp = api_req(f"{base}/api/channel/fix", method="POST", headers=headers, timeout=120)
        elapsed = time.time() - start
        ok = "OK" if resp.get("success") else "FAIL"
        print(f"  {ok} ({elapsed:.1f}s) — {resp.get('message', 'done')}")

    # ════════════════════════════════════════════════════════════════
    # Step 3: Test channels
    # ════════════════════════════════════════════════════════════════
    if args.skip_test:
        print(f"\n── Channel testing: skipped (--skip-test) ──")
    else:
        print(f"\n── Test all channels (GET /api/channel/test) ──")
        print("  (this may take several minutes)")
        if args.dry_run:
            print("  [DRY-RUN] Would call test")
        else:
            start = time.time()
            resp = api_req(f"{base}/api/channel/test", headers=headers, timeout=600)
            elapsed = time.time() - start
            ok = "OK" if resp.get("success") else "FAIL"
            print(f"  {ok} ({elapsed:.1f}s) — {resp.get('message', 'done')}")

    # ════════════════════════════════════════════════════════════════
    # Step 4: Update balances
    # ════════════════════════════════════════════════════════════════
    if args.skip_balance:
        print(f"\n── Balance refresh: skipped (--skip-balance) ──")
    else:
        print(f"\n── Refresh balances (GET /api/channel/update_balance) ──")
        if args.dry_run:
            print("  [DRY-RUN] Would call update_balance")
        else:
            start = time.time()
            resp = api_req(f"{base}/api/channel/update_balance", headers=headers, timeout=300)
            elapsed = time.time() - start
            ok = "OK" if resp.get("success") else "FAIL"
            print(f"  {ok} ({elapsed:.1f}s) — {resp.get('message', 'done')}")

    print("\n" + "=" * 60)
    if do_create:
        print(f"  Done. Channels created: {created}/{len(channels)}")
    else:
        print(f"  Done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
