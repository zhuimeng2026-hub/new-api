#!/usr/bin/env bash
#
# newapi-db.sh — PostgreSQL backup & restore for new-api
#
# Usage:
#   ./newapi-db.sh backup              # create a new backup
#   ./newapi-db.sh restore             # restore from latest backup (interactive)
#   ./newapi-db.sh restore FILE        # restore from specific backup file
#   ./newapi-db.sh list                # list all backups
#   ./newapi-db.sh clean FILE          # remove pg_dump log lines from existing backup
#

set -euo pipefail

# --- configuration ---
CONTAINER="postgres"
DB_NAME="new-api"
DB_USER="root"
DB_PASS="123456"
BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_PREFIX="new-api-db-dump"
KEEP_COUNT=10

# --- helpers ---
log_info()  { echo "[INFO]  $*"; }
log_warn()  { echo "[WARN]  $*" >&2; }
log_error() { echo "[ERROR] $*" >&2; }

container_running() {
    docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"
}

db_exists() {
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d postgres -tc \
        "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME';" 2>/dev/null | grep -q 1
}

check_container() {
    if ! container_running; then
        log_error "PostgreSQL container '$CONTAINER' is not running."
        exit 1
    fi
}

# --- backup ---
cmd_backup() {
    check_container

    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local filename="${BACKUP_PREFIX}-${timestamp}.sql"
    local filepath="${BACKUP_DIR}/${filename}"

    log_info "Starting backup → $filename"

    # Use pg_dump from inside container to avoid version mismatch
    docker exec -i "$CONTAINER" pg_dump -U "$DB_USER" -d "$DB_NAME" --verbose > "$filepath"

    local size
    size=$(du -h "$filepath" | cut -f1)
    log_info "Backup complete: $filename ($size)"

    # Remove old backups (keep last KEEP_COUNT)
    local count
    count=$(ls -1t "${BACKUP_DIR}/${BACKUP_PREFIX}"-*.sql 2>/dev/null | wc -l)
    if (( count > KEEP_COUNT )); then
        log_info "Removing old backups (keeping last $KEEP_COUNT)"
        ls -1t "${BACKUP_DIR}/${BACKUP_PREFIX}"-*.sql | tail -n +$((KEEP_COUNT + 1)) | while read -r oldfile; do
            rm -f "$oldfile"
            log_info "Removed: $(basename "$oldfile")"
        done
    fi
}

# --- clean (strip pg_dump log lines) ---
cmd_clean() {
    local input="$1"
    if [[ ! -f "$input" ]]; then
        log_error "File not found: $input"
        exit 1
    fi

    local tmpfile
    tmpfile=$(mktemp)
    log_info "Cleaning pg_dump log lines from: $(basename "$input")"

    # Strip pg_dump verbose output lines that leak into the dump file
    sed -E '/^(pg_dump:|creating|dropping|processing|dumping)/d' "$input" > "$tmpfile"

    local before after
    before=$(wc -l < "$input" | tr -d ' ')
    after=$(wc -l < "$tmpfile" | tr -d ' ')

    mv "$tmpfile" "$input"
    log_info "Cleaned: $before → $after lines ($(($before - $after)) removed)"
}

# --- restore ---
cmd_restore() {
    check_container

    local target_file=""

    if [[ -n "${1:-}" ]]; then
        target_file="$1"
        if [[ ! -f "$target_file" ]]; then
            # try under BACKUP_DIR
            target_file="${BACKUP_DIR}/$1"
            if [[ ! -f "$target_file" ]]; then
                log_error "Backup file not found: $1"
                exit 1
            fi
        fi
    else
        # interactive: pick latest or let user choose
        local backups
        backups=$(ls -1t "${BACKUP_DIR}/${BACKUP_PREFIX}"-*.sql 2>/dev/null || true)

        if [[ -z "$backups" ]]; then
            log_error "No backup files found in $BACKUP_DIR"
            exit 1
        fi

        echo "Available backups:"
        local i=1
        local files=()
        while IFS= read -r f; do
            files+=("$f")
            local sz
            sz=$(du -h "$f" | cut -f1)
            printf "  [%d] %s (%s)\n" "$i" "$(basename "$f")" "$sz"
            ((i++))
        done <<< "$backups"

        read -rp "Select backup to restore [1]: " choice
        choice=${choice:-1}

        if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#files[@]} )); then
            log_error "Invalid selection."
            exit 1
        fi

        target_file="${files[$((choice - 1))]}"
    fi

    log_info "Target backup: $(basename "$target_file")"

    # Confirm
    read -rp "⚠️  This will DROP and RECREATE database '$DB_NAME'. Are you sure? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        log_info "Restore cancelled."
        exit 0
    fi

    # Check if file contains pg_dump log pollution
    if grep -qE "^(pg_dump:|creating|dropping|processing|dumping)" "$target_file"; then
        log_warn "Backup file contains pg_dump log lines. Cleaning before restore..."
        cmd_clean "$target_file"
    fi

    # Terminate existing connections
    log_info "Terminating existing connections to '$DB_NAME'..."
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d postgres -c \
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" >/dev/null 2>&1 || true

    # Drop and recreate
    log_info "Dropping database '$DB_NAME'..."
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" >/dev/null

    log_info "Creating database '$DB_NAME'..."
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"$DB_NAME\";" >/dev/null

    # Restore
    log_info "Restoring from backup..."
    if docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" < "$target_file"; then
        log_info "Restore complete."
    else
        log_error "Restore failed. Check output above."
        exit 1
    fi

    # Verify key tables
    log_info "Verifying key tables..."
    docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
        "SELECT 'channels' as tbl, COUNT(*) as cnt FROM channels
         UNION ALL SELECT 'users', COUNT(*) FROM users
         UNION ALL SELECT 'logs', COUNT(*) FROM logs
         UNION ALL SELECT 'tokens', COUNT(*) FROM tokens
         UNION ALL SELECT 'models', COUNT(*) FROM models;"
}

# --- list ---
cmd_list() {
    local files
    files=$(ls -1t "${BACKUP_DIR}/${BACKUP_PREFIX}"-*.sql 2>/dev/null || true)

    if [[ -z "$files" ]]; then
        log_info "No backups found in $BACKUP_DIR"
        return
    fi

    printf "%-40s %10s %20s\n" "Backup File" "Size" "Modified"
    printf "%-40s %10s %20s\n" "----------------------------------------" "----------" "--------------------"
    while IFS= read -r f; do
        local sz mtime
        sz=$(du -h "$f" | cut -f1)
        mtime=$(stat -c '%y' "$f" 2>/dev/null | cut -d'.' -f1 || stat -f '%Sm' -t '%Y-%m-%d %H:%M:%S' "$f" 2>/dev/null)
        printf "%-40s %10s %20s\n" "$(basename "$f")" "$sz" "$mtime"
    done <<< "$files"
}

# --- help ---
cmd_help() {
    cat <<-'EOF'
Usage: ./newapi-db.sh <command> [args]

Commands:
  backup              Create a new PostgreSQL backup
  restore [FILE]      Restore database from backup (interactive if no file given)
  list                List all available backups
  clean FILE          Remove pg_dump log pollution from an existing backup file
  help                Show this help message

Environment:
  CONTAINER=postgres   Docker container name
  DB_NAME=new-api      Database name
  DB_USER=root         PostgreSQL user
  DB_PASS=123456       PostgreSQL password
  KEEP_COUNT=10        Number of backups to retain
EOF
}

# --- main ---
main() {
    local cmd="${1:-help}"
    shift || true

    case "$cmd" in
        backup)
            cmd_backup
            ;;
        restore)
            cmd_restore "$@"
            ;;
        list)
            cmd_list
            ;;
        clean)
            if [[ $# -eq 0 ]]; then
                log_error "Usage: ./newapi-db.sh clean FILE"
                exit 1
            fi
            cmd_clean "$1"
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            log_error "Unknown command: $cmd"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
