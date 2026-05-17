#!/usr/bin/env python3
"""
newapi_backup.py — PostgreSQL backup & restore for new-api

Usage:
    python3 newapi_backup.py                  # create a new backup (default)
    python3 newapi_backup.py backup           # create a new backup
    python3 newapi_backup.py restore          # restore from latest backup (interactive)
    python3 newapi_backup.py restore FILE     # restore from specific backup file
    python3 newapi_backup.py list             # list all backups
    python3 newapi_backup.py channel          # backup channel config via API
    python3 newapi_backup.py clean FILE       # remove pg_dump log lines from existing backup
"""

import argparse
import glob
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# --- configuration (override via environment) ---
CONTAINER = os.environ.get("DB_CONTAINER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "new-api")
DB_USER = os.environ.get("DB_USER", "root")
DB_PASS = os.environ.get("DB_PASS", "123456")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", Path(__file__).parent))
BACKUP_PREFIX = "new-api-db-dump"
KEEP_COUNT = int(os.environ.get("KEEP_COUNT", "10"))

# --- logging ---
def log_info(msg: str):
    print(f"[INFO]  {msg}")

def log_warn(msg: str):
    print(f"[WARN]  {msg}", file=sys.stderr)

def log_error(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)

# --- helpers ---
def container_running() -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True, check=True,
        )
        return CONTAINER in result.stdout.strip().split("\n")
    except subprocess.CalledProcessError:
        return False

def check_container():
    if not container_running():
        log_error(f"Docker container '{CONTAINER}' is not running.")
        sys.exit(1)

def list_backup_files() -> list[Path]:
    files = sorted(
        BACKUP_DIR.glob(f"{BACKUP_PREFIX}-*.sql"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return files

def human_size(path: Path) -> str:
    size = path.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def remove_old_backups():
    files = list_backup_files()
    if len(files) > KEEP_COUNT:
        log_info(f"Removing old backups (keeping last {KEEP_COUNT})")
        for old in files[KEEP_COUNT:]:
            old.unlink()
            log_info(f"Removed: {old.name}")

# --- backup ---
def cmd_backup():
    check_container()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{BACKUP_PREFIX}-{timestamp}.sql"
    filepath = BACKUP_DIR / filename

    log_info(f"Starting backup -> {filename}")

    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER,
         "pg_dump", "-U", DB_USER, "-d", DB_NAME, "--verbose"],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        log_error(f"pg_dump failed:\n{result.stderr}")
        sys.exit(1)

    # pg_dump --verbose writes log lines to stderr, data to stdout
    filepath.write_text(result.stdout)

    log_info(f"Backup complete: {filename} ({human_size(filepath)})")
    remove_old_backups()

# --- clean ---
def cmd_clean(filepath: str):
    path = Path(filepath)
    if not path.exists():
        log_error(f"File not found: {filepath}")
        sys.exit(1)

    log_info(f"Cleaning pg_dump log lines from: {path.name}")

    lines = path.read_text().splitlines(keepends=True)
    import re
    pattern = re.compile(r"^(pg_dump:|creating|dropping|processing|dumping)")
    cleaned = [line for line in lines if not pattern.match(line)]

    path.write_text("".join(cleaned))
    log_info(f"Cleaned: {len(lines)} -> {len(cleaned)} lines ({len(lines) - len(cleaned)} removed)")

# --- restore ---
def cmd_restore(target_file: str | None = None):
    check_container()

    if target_file:
        path = Path(target_file)
        if not path.exists():
            path = BACKUP_DIR / target_file
        if not path.exists():
            log_error(f"Backup file not found: {target_file}")
            sys.exit(1)
    else:
        files = list_backup_files()
        if not files:
            log_error(f"No backup files found in {BACKUP_DIR}")
            sys.exit(1)

        print("Available backups:")
        for i, f in enumerate(files, 1):
            print(f"  [{i}] {f.name} ({human_size(f)})")

        try:
            choice = input("Select backup to restore [1]: ").strip() or "1"
            idx = int(choice) - 1
            if idx < 0 or idx >= len(files):
                raise ValueError
        except (ValueError, EOFError):
            log_error("Invalid selection.")
            sys.exit(1)

        path = files[idx]

    log_info(f"Target backup: {path.name}")

    confirm = input(f"WARNING: This will DROP and RECREATE database '{DB_NAME}'. Are you sure? [y/N] ")
    if confirm.lower() != "y":
        log_info("Restore cancelled.")
        return

    import re
    content = path.read_text()
    if re.search(r"^(pg_dump:|creating|dropping|processing|dumping)", content, re.MULTILINE):
        log_warn("Backup file contains pg_dump log lines. Cleaning before restore...")
        pattern = re.compile(r"^(pg_dump:|creating|dropping|processing|dumping).*\n?", re.MULTILINE)
        content = pattern.sub("", content)
        path.write_text(content)

    log_info(f"Terminating existing connections to '{DB_NAME}'...")
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", "postgres", "-c",
         f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{DB_NAME}' AND pid <> pg_backend_pid();"],
        capture_output=True,
    )

    log_info(f"Dropping database '{DB_NAME}'...")
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", "postgres", "-c",
         f'DROP DATABASE IF EXISTS "{DB_NAME}";'],
        capture_output=True, check=True,
    )

    log_info(f"Creating database '{DB_NAME}'...")
    subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", "postgres", "-c",
         f'CREATE DATABASE "{DB_NAME}";'],
        capture_output=True, check=True,
    )

    log_info("Restoring from backup...")
    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME],
        input=content, capture_output=True, text=True,
    )

    if result.returncode != 0:
        log_error(f"Restore failed:\n{result.stderr}")
        sys.exit(1)

    log_info("Restore complete.")

    log_info("Verifying key tables...")
    verify = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-c",
         "SELECT 'channels' as tbl, COUNT(*) as cnt FROM channels "
         "UNION ALL SELECT 'users', COUNT(*) FROM users "
         "UNION ALL SELECT 'logs', COUNT(*) FROM logs "
         "UNION ALL SELECT 'tokens', COUNT(*) FROM tokens;"],
        capture_output=True, text=True,
    )
    print(verify.stdout)

# --- list ---
def cmd_list():
    files = list_backup_files()
    if not files:
        log_info(f"No backups found in {BACKUP_DIR}")
        return

    print(f"{'Backup File':<45} {'Size':>10} {'Modified':>20}")
    print(f"{'-'*45} {'-'*10} {'-'*20}")
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{f.name:<45} {human_size(f):>10} {mtime:>20}")

# --- channel backup via API ---
def cmd_channel():
    """Backup channel configuration via the admin API."""
    try:
        import json
        import urllib.request
    except ImportError:
        log_error("urllib not available")
        sys.exit(1)

    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        log_error(".env file not found")
        sys.exit(1)

    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    admin_url = env.get("new_admin_url", "")
    admin_key = env.get("new_admin_key", "")
    admin_user = env.get("New-Api-User", "")

    if not all([admin_url, admin_key, admin_user]):
        log_error("Missing new_admin_url / new_admin_key / New-Api-User in .env")
        sys.exit(1)

    base = admin_url.replace("/api/channel/", "")
    url = f"{admin_url}?page_size=100"

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {admin_key}",
        "New-Api-User": admin_user,
    })

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        log_error(f"API request failed: {e}")
        sys.exit(1)

    if not data.get("success"):
        log_error(f"API error: {data.get('message')}")
        sys.exit(1)

    channels = data["data"]["items"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"channel_backup_{timestamp}.json"
    filepath = BACKUP_DIR / filename

    # Mask keys for safety
    for ch in channels:
        if ch.get("key"):
            ch["key"] = ch["key"][:8] + "***"

    filepath.write_text(json.dumps(channels, indent=2, ensure_ascii=False))
    log_info(f"Channel backup saved: {filename} ({len(channels)} channels)")

# --- main ---
def main():
    parser = argparse.ArgumentParser(description="newapi database backup & restore")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("backup", help="Create a new PostgreSQL backup")
    sub.add_parser("list", help="List all available backups")
    sub.add_parser("channel", help="Backup channel config via API")

    restore_p = sub.add_parser("restore", help="Restore database from backup")
    restore_p.add_argument("file", nargs="?", help="Backup file to restore from")

    clean_p = sub.add_parser("clean", help="Remove pg_dump log lines from backup file")
    clean_p.add_argument("file", help="Backup file to clean")

    args = parser.parse_args()

    # Default: backup when no arguments given
    if args.command is None:
        cmd_backup()
    elif args.command == "backup":
        cmd_backup()
    elif args.command == "restore":
        cmd_restore(args.file)
    elif args.command == "list":
        cmd_list()
    elif args.command == "channel":
        cmd_channel()
    elif args.command == "clean":
        cmd_clean(args.file)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
