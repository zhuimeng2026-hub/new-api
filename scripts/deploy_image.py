#!/usr/bin/env python3
"""
deploy_image.py — Docker image loader & deployer for new-api

Usage:
    python3 deploy_image.py /path/to/new-api.tar.gz              # load & deploy (auto-detect compose)
    python3 deploy_image.py -c /opt/new-api image.tar.gz         # specify compose directory
    python3 deploy_image.py -c /opt/new-api/docker-compose.yml image.tar.gz  # specify compose file
    python3 deploy_image.py --no-backup image.tar.gz             # skip db backup
    python3 deploy_image.py --check                              # check current status
    python3 deploy_image.py -c /opt/new-api --check              # check with specific compose dir
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# --- configuration ---
SERVICE_NAME = "new-api"
HEALTH_URL = "http://localhost:3000/api/status"
HEALTH_TIMEOUT_DEFAULT = 60  # seconds
HEALTH_INTERVAL = 2  # seconds between retries

# These will be resolved after argument parsing
COMPOSE_DIR = None
COMPOSE_FILE = None

# --- path resolution ---
def resolve_compose_path(compose_arg: str | None) -> tuple[Path, Path]:
    """Resolve compose directory and file path from argument.

    Args:
        compose_arg: User-provided path (dir or file), or None for auto-detect

    Returns:
        Tuple of (compose_dir, compose_file)
    """
    if compose_arg:
        target = Path(compose_arg).resolve()
        if target.is_file() and target.name.endswith(('.yml', '.yaml')):
            # User provided a compose file path directly
            return target.parent, target
        elif target.is_dir():
            # User provided a directory
            compose_file = target / "docker-compose.yml"
            if compose_file.exists():
                return target, compose_file
            # Also check for docker-compose.yaml
            compose_file = target / "docker-compose.yaml"
            if compose_file.exists():
                return target, compose_file
            log_error(f"No docker-compose.yml found in {target}")
            sys.exit(1)
        else:
            log_error(f"Path does not exist: {target}")
            sys.exit(1)

    # Auto-detect: check current working directory first
    cwd = Path.cwd()
    for name in ["docker-compose.yml", "docker-compose.yaml"]:
        compose_file = cwd / name
        if compose_file.exists():
            log_info(f"Auto-detected compose file in current directory: {compose_file}")
            return cwd, compose_file

    # Fallback: check script's directory
    script_dir = Path(__file__).parent.resolve()
    for name in ["docker-compose.yml", "docker-compose.yaml"]:
        compose_file = script_dir / name
        if compose_file.exists():
            log_info(f"Auto-detected compose file in script directory: {compose_file}")
            return script_dir, compose_file

    log_error("Could not find docker-compose.yml!")
    log_error("Searched in:")
    log_error(f"  - Current directory: {cwd}")
    log_error(f"  - Script directory: {script_dir}")
    log_error("Use -c/--compose-dir to specify the compose file location.")
    sys.exit(1)

# --- logging ---
def log_info(msg: str):
    print(f"[INFO]  {msg}")

def log_warn(msg: str):
    print(f"[WARN]  {msg}", file=sys.stderr)

def log_error(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr)

def log_ok(msg: str):
    print(f"[OK]    {msg}")

# --- helpers ---
def run_cmd(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    """Run a command with error handling."""
    log_info(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=capture, text=True, check=False)
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        log_error(f"Command failed (exit {result.returncode}): {stderr}")
        sys.exit(1)
    return result

def container_running(name: str) -> bool:
    """Check if a container is running."""
    result = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=False,
    )
    return name in (result.stdout or "").strip().split("\n")

def get_image_tag(tar_path: Path) -> str | None:
    """Load image and return its tag."""
    result = run_cmd(["docker", "load", "-i", str(tar_path)], check=False, capture=True)
    if result.returncode != 0:
        log_error(f"Failed to load image: {result.stderr.strip()}")
        return None
    # Parse output like "Loaded image: new-api:local"
    for line in (result.stdout or "").strip().split("\n"):
        if "Loaded image:" in line:
            return line.split("Loaded image:")[-1].strip()
    log_warn("Could not parse loaded image tag, assuming 'new-api:local'")
    return "new-api:local"

def check_health() -> bool:
    """Check if the service is healthy via HTTP."""
    try:
        import urllib.request
        req = urllib.request.Request(HEALTH_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("success") is True
    except Exception:
        return False

def wait_for_health(timeout: int = HEALTH_TIMEOUT_DEFAULT) -> bool:
    """Wait for service to become healthy."""
    log_info(f"Waiting for service health (timeout={timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        if check_health():
            return True
        time.sleep(HEALTH_INTERVAL)
    return False

def check_db_has_data() -> bool:
    """Check if PostgreSQL database has actual data (not empty)."""
    result = subprocess.run(
        ["docker", "exec", "postgres", "psql", "-U", "root", "-d", "new-api",
         "-t", "-c", "SELECT COUNT(*) FROM users;"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return False
    try:
        count = int(result.stdout.strip())
        return count > 0
    except (ValueError, TypeError):
        return False

def check_pg_volume_exists() -> bool:
    """Check if PostgreSQL data volume exists."""
    result = subprocess.run(
        ["docker", "volume", "inspect", "new-api_pg_data"],
        capture_output=True, text=True, check=False,
    )
    return result.returncode == 0

# --- commands ---
def cmd_check():
    """Check current deployment status."""
    print("=" * 50)
    print("New-API Deployment Status")
    print("=" * 50)

    # Check containers
    for name in [SERVICE_NAME, "postgres", "redis"]:
        status = "running" if container_running(name) else "stopped"
        icon = "✓" if status == "running" else "✗"
        print(f"  {icon} {name}: {status}")

    # Check health
    if container_running(SERVICE_NAME):
        healthy = check_health()
        icon = "✓" if healthy else "✗"
        print(f"  {icon} health: {'ok' if healthy else 'failed'}")

    # Check PostgreSQL volume
    pg_vol = check_pg_volume_exists()
    icon = "✓" if pg_vol else "✗"
    print(f"  {icon} pg_volume: {'exists' if pg_vol else 'missing'}")

    # Check database has data
    if container_running("postgres"):
        has_data = check_db_has_data()
        icon = "✓" if has_data else "✗"
        print(f"  {icon} db_data: {'ok' if has_data else 'EMPTY!'}")

    # Check compose file
    exists = COMPOSE_FILE.exists()
    icon = "✓" if exists else "✗"
    print(f"  {icon} compose: {COMPOSE_FILE}")

    print("=" * 50)

def get_compose_image() -> str | None:
    """Extract the service image tag from docker-compose.yml."""
    try:
        content = COMPOSE_FILE.read_text()
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if stripped.startswith("image:") and "postgres" not in stripped and "redis" not in stripped and "mysql" not in stripped:
                return stripped.split("image:", 1)[1].strip()
    except Exception:
        pass
    return None

def check_sql_dsn() -> bool:
    """Verify SQL_DSN is configured for PostgreSQL in docker-compose.yml."""
    try:
        content = COMPOSE_FILE.read_text()
        # Check for active (not commented) SQL_DSN with postgresql
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "SQL_DSN" in stripped and "postgresql" in stripped:
                return True
        return False
    except Exception:
        return False

def cmd_deploy(tar_path: Path, backup: bool = True, timeout: int = HEALTH_TIMEOUT_DEFAULT):
    """Deploy new image."""
    # 1. Validate inputs
    if not tar_path.exists():
        log_error(f"File not found: {tar_path}")
        sys.exit(1)
    if not tar_path.is_file():
        log_error(f"Not a file: {tar_path}")
        sys.exit(1)
    if not COMPOSE_FILE.exists():
        log_error(f"Compose file not found: {COMPOSE_FILE}")
        sys.exit(1)

    # 1.1 Verify PostgreSQL is configured (not SQLite)
    if not check_sql_dsn():
        log_error("SQL_DSN with PostgreSQL not found in docker-compose.yml!")
        log_error("Aborting to prevent fallback to SQLite database.")
        sys.exit(1)
    log_ok("SQL_DSN configured for PostgreSQL")

    log_info(f"Deploying from: {tar_path}")
    log_info(f"Compose dir: {COMPOSE_DIR}")

    # 2. Backup database (optional)
    if backup:
        backup_script = COMPOSE_DIR / "newapi_backup.py"
        if backup_script.exists():
            log_info("Creating database backup...")
            run_cmd([sys.executable, str(backup_script), "backup"], check=False)
        else:
            log_warn("Backup script not found, skipping backup")

    # 3. Load Docker image
    log_info("Loading Docker image...")
    image_tag = get_image_tag(tar_path)
    if not image_tag:
        log_error("Failed to load image")
        sys.exit(1)
    log_ok(f"Image loaded: {image_tag}")

    # 3.1 Ensure loaded image tag matches what docker-compose expects
    expected_tag = get_compose_image()
    if expected_tag and image_tag != expected_tag:
        log_info(f"Tagging {image_tag} → {expected_tag} (to match docker-compose.yml)")
        run_cmd(["docker", "tag", image_tag, expected_tag])
        log_ok(f"Tagged: {expected_tag}")
    elif expected_tag:
        log_ok(f"Image tag matches compose: {expected_tag}")

    # 4. Stop current containers
    log_info("Stopping current containers...")
    run_cmd(["docker", "compose", "-f", str(COMPOSE_FILE), "down"], check=False)

    # 5. Start new containers
    log_info("Starting containers...")
    run_cmd(["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"])

    # 6. Wait for health
    if wait_for_health(timeout):
        log_ok("Service is healthy!")
    else:
        log_warn("Health check timed out, service may still be starting")

    # 7. Verify database has data
    log_info("Verifying database connection and data...")
    time.sleep(3)  # Wait for DB init
    if check_pg_volume_exists():
        log_ok("PostgreSQL volume exists")
    else:
        log_error("PostgreSQL volume not found!")
        sys.exit(1)

    if check_db_has_data():
        log_ok("Database has data")
    else:
        log_error("Database is empty! Possible volume mount issue.")
        log_error("Check: docker exec postgres psql -U root -d new-api -c 'SELECT COUNT(*) FROM users;'")
        sys.exit(1)

    # 8. Final status
    log_info("")
    cmd_check()

# --- main ---
def main():
    global COMPOSE_DIR, COMPOSE_FILE

    parser = argparse.ArgumentParser(
        description="Deploy new-api Docker image from tar.gz",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s image.tar.gz                    # Auto-detect compose location
  %(prog)s -c /opt/new-api image.tar.gz    # Specify compose directory
  %(prog)s -c /opt/new-api/docker-compose.yml image.tar.gz  # Specify compose file
  %(prog)s --check                         # Check current status
  %(prog)s -c /opt/new-api --check         # Check with specific compose dir
        """,
    )
    parser.add_argument("image", nargs="?", help="Path to tar.gz image file")
    parser.add_argument("-c", "--compose-dir", dest="compose_dir",
                        help="Path to docker-compose.yml or its directory (default: auto-detect)")
    parser.add_argument("--no-backup", action="store_true", help="Skip database backup")
    parser.add_argument("--check", action="store_true", help="Check current status only")
    parser.add_argument("--timeout", type=int, default=HEALTH_TIMEOUT_DEFAULT,
                        help="Health check timeout in seconds (default: %(default)s)")

    args = parser.parse_args()

    # Resolve compose path (must happen before any command)
    COMPOSE_DIR, COMPOSE_FILE = resolve_compose_path(args.compose_dir)

    if args.check:
        cmd_check()
        return

    if not args.image:
        parser.error("Image path is required (or use --check)")

    cmd_deploy(Path(args.image), backup=not args.no_backup, timeout=args.timeout)

if __name__ == "__main__":
    main()
