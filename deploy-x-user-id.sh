#!/bin/bash
# ============================================================
# deploy-x-user-id.sh
# 无人值守部署脚本：x-user-id (openid) 接入 new-api 账号体系
#
# 用法:
#   ./deploy-x-user-id.sh                     # 默认在 tmux 中运行（脱离终端）
#   tmux attach -t deploy-openid              # 重新连接查看实时输出
#
# 功能:
#   1. 修改 model/user.go  — 新增 GetOrCreateUserByOpenId
#   2. 修改 controller/token.go — AddToken 注入 x-user-id 逻辑
#   3. 数据库添加 wechat_id 唯一索引（防并发）
#   4. go build 编译验证
#   5. 失败自动回滚
# ============================================================
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="${LOG_FILE:-/opt/new-api/deploy_openid_${TIMESTAMP}.log}"
PROJECT_DIR="/opt/new-api"
TMUX_SESSION="deploy-openid"

# ============================================================
# 日志：同时输出到终端和日志文件
# ============================================================
log()     { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"; }
log_ok()  { log "✅ $*"; }
log_err() { log "❌ ERROR: $*"; }
log_hdr() {
    log ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "📌 $*"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# ============================================================
# 回滚：恢复所有代码改动
# ============================================================
rollback() {
    log_hdr "回滚代码改动"
    cd "$PROJECT_DIR"
    if git diff --quiet model/user.go controller/token.go; then
        log "  无需回滚，文件未改动"
    else
        git checkout model/user.go controller/token.go
        log "  已回滚 model/user.go controller/token.go"
    fi
}

# ============================================================
# 预检
# ============================================================
preflight() {
    log_hdr "预检环境"
    cd "$PROJECT_DIR"

    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        log_err "不是 git 仓库"; exit 1
    fi
    if ! git diff --quiet model/user.go controller/token.go; then
        log_err "model/user.go 或 controller/token.go 有未提交修改，请先提交或撤销"
        exit 1
    fi
    if ! command -v go &>/dev/null; then
        log_err "go 未安装"; exit 1
    fi
    log_ok "预检通过 — 工作区干净，go $(go version | awk '{print $3}')"
}

# ============================================================
# 1. 修改 model/user.go
# ============================================================
patch_user_model() {
    log_hdr "1/3 修改 model/user.go — 新增 GetOrCreateUserByOpenId"

    if grep -q "GetOrCreateUserByOpenId" model/user.go 2>/dev/null; then
        log "  已存在，跳过"
        return
    fi

    python3 << 'PYEOF'
import sys

with open('model/user.go', 'r') as f:
    content = f.read()

marker = '\nfunc IsEmailAlreadyTaken'
pos = content.find(marker)
if pos == -1:
    print('ERROR: cannot find IsEmailAlreadyTaken')
    sys.exit(1)

new_func = '''
// GetOrCreateUserByOpenId finds or creates a user by openid (stored in wechat_id).
// If affCode is provided and valid, the new user is created with inviter relationship.
func GetOrCreateUserByOpenId(openid string, affCode string) (*User, error) {
	if openid == "" {
		return nil, errors.New("openid 为空")
	}
	user := &User{WeChatId: openid}
	err := user.FillUserByWeChatId()
	if err == nil {
		return user, nil
	}
	if !errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, err
	}
	// Create new user
	usernameBase := "oversea_" + openid
	if len(usernameBase) > UserNameMaxLength {
		usernameBase = usernameBase[:UserNameMaxLength]
	}
	var inviterId int
	if affCode != "" {
		inviterId, _ = GetUserIdByAffCode(affCode)
	}
	maxQuota := int(1000000000 * common.QuotaPerUnit)
	// Retry with random suffix on username conflict
	var newUser *User
	for attempt := 0; attempt < 5; attempt++ {
		username := usernameBase
		if attempt > 0 {
			suffix := common.GetRandomString(4)
			maxPrefix := UserNameMaxLength - len(suffix)
			if len(usernameBase) > maxPrefix {
				username = usernameBase[:maxPrefix] + suffix
			} else {
				username = usernameBase + suffix
			}
		}
		candidate := &User{
			Username: username,
			WeChatId: openid,
			Role:     common.RoleCommonUser,
			Status:   common.UserStatusEnabled,
			Password: common.GetRandomString(16),
		}
		err = candidate.Insert(inviterId)
		if err == nil {
			newUser = candidate
			break
		}
		if !strings.Contains(err.Error(), "username") &&
		   !strings.Contains(err.Error(), "UNIQUE") &&
		   !strings.Contains(err.Error(), "unique") &&
		   !strings.Contains(err.Error(), "Duplicate") {
			return nil, err
		}
	}
	if newUser == nil {
		return nil, errors.New("创建用户失败：无法生成唯一用户名")
	}
	// Override QuotaForNewUser default — keygen users use token quota as the only limit
	if err := DB.Model(newUser).Update("quota", maxQuota).Error; err != nil {
		return nil, err
	}
	newUser.Quota = maxQuota
	return newUser, nil
}

'''

content = content[:pos] + new_func + content[pos:]

with open('model/user.go', 'w') as f:
    f.write(content)
print('OK')
PYEOF

    if [ $? -ne 0 ]; then
        log_err "model/user.go 修改失败"; return 1
    fi
    log_ok "model/user.go 已更新"
}

# ============================================================
# 2. 修改 controller/token.go
# ============================================================
patch_token_controller() {
    log_hdr "2/3 修改 controller/token.go — AddToken 注入 x-user-id 逻辑"

    if grep -q "x-user-id" controller/token.go 2>/dev/null; then
        log "  已存在，跳过"
        return
    fi

    python3 << 'PYEOF'
import sys

with open('controller/token.go', 'r') as f:
    content = f.read()

marker = '\t// 检查用户令牌数量是否已达上限'
pos = content.find(marker)
if pos == -1:
    print('ERROR: cannot find marker in controller/token.go')
    sys.exit(1)

new_block = '\t// x-user-id: auto-create/bind user by openid (from keygen oversea-key)\n\tif openid := c.GetHeader("x-user-id"); openid != "" {\n\t\taffCode := c.GetHeader("x-aff-code")\n\t\tuser, err := model.GetOrCreateUserByOpenId(openid, affCode)\n\t\tif err != nil {\n\t\t\tcommon.ApiError(c, err)\n\t\t\treturn\n\t\t}\n\t\tc.Set("id", user.Id)\n\t}\n'

content = content[:pos] + new_block + content[pos:]

with open('controller/token.go', 'w') as f:
    f.write(content)
print('OK')
PYEOF

    if [ $? -ne 0 ]; then
        log_err "controller/token.go 修改失败"; return 1
    fi
    log_ok "controller/token.go 已更新"
}

# ============================================================
# 3. 数据库迁移 — wechat_id 唯一索引
# ============================================================
apply_db_migration() {
    log_hdr "3/3 数据库迁移 — wechat_id 唯一索引"

    local SQL_DSN=""
    local SQLITE_PATH=""

    if [ -f .env ]; then
        SQL_DSN=$(grep -E '^SQL_DSN=' .env 2>/dev/null | head -1 | sed 's/.*=//' | xargs || true)
        SQLITE_PATH=$(grep -E '^SQLITE_PATH=' .env 2>/dev/null | head -1 | sed 's/.*=//' | xargs || true)
    fi

    local DB_TYPE="unknown"
    if echo "$SQL_DSN" | grep -qi "postgres"; then
        DB_TYPE="postgres"
    elif echo "$SQL_DSN" | grep -qi "mysql"; then
        DB_TYPE="mysql"
    elif [ -n "$SQLITE_PATH" ] || [ -z "$SQL_DSN" ]; then
        DB_TYPE="sqlite"
    fi

    log "  检测到数据库类型: $DB_TYPE"

    case "$DB_TYPE" in
        postgres)
            log "  执行 PostgreSQL 迁移..."
            local PG_HOST=$(echo "$SQL_DSN" | sed -n 's/.*host=\([^ ]*\).*/\1/p')
            local PG_PORT=$(echo "$SQL_DSN" | sed -n 's/.*port=\([^ ]*\).*/\1/p')
            local PG_USER=$(echo "$SQL_DSN" | sed -n 's/.*user=\([^ ]*\).*/\1/p')
            local PG_DB=$(echo "$SQL_DSN" | sed -n 's/.*dbname=\([^ ]*\).*/\1/p')
            local PGPASS=$(echo "$SQL_DSN" | sed -n 's/.*password=\([^ ]*\).*/\1/p')

            PGPASSWORD="$PGPASS" psql -h "${PG_HOST:-localhost}" \
                -p "${PG_PORT:-5432}" -U "${PG_USER:-postgres}" \
                -d "${PG_DB:-newapi}" -c "
                DO \$\$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_indexes WHERE indexname = 'idx_users_wechat_id'
                    ) THEN
                        CREATE UNIQUE INDEX idx_users_wechat_id ON users(wechat_id) WHERE wechat_id != '' AND deleted_at IS NULL;
                    END IF;
                END
                \$\$;
            " 2>&1 | tee -a "$LOG_FILE" || log "  ⚠ PostgreSQL 迁移失败，继续（非致命）"
            log_ok "PostgreSQL 迁移完成"
            ;;
        mysql)
            log "  执行 MySQL 迁移..."
            local MYSQL_HOST=$(echo "$SQL_DSN" | sed -n 's/.*@tcp(\([^:]*\).*/\1/p')
            local MYSQL_PORT=$(echo "$SQL_DSN" | sed -n 's/.*@tcp([^:]*:\([^)]*\).*/\1/p')
            local MYSQL_USER=$(echo "$SQL_DSN" | sed -n 's/\([^:]*\):.*@tcp.*/\1/p')
            local MYSQL_PASS=$(echo "$SQL_DSN" | sed -n 's/[^:]*:\([^@]*\)@tcp.*/\1/p')
            local MYSQL_DB=$(echo "$SQL_DSN" | sed -n 's/.*\/\([^?]*\).*/\1/p')

            mysql -h "${MYSQL_HOST:-localhost}" -P "${MYSQL_PORT:-3306}" \
                -u "${MYSQL_USER:-root}" -p"$MYSQL_PASS" \
                -D "${MYSQL_DB:-newapi}" -e "
                CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_id ON users(wechat_id);
            " 2>&1 | tee -a "$LOG_FILE" || log "  ⚠ MySQL 迁移失败（可能索引已存在），继续"
            log_ok "MySQL 迁移完成"
            ;;
        sqlite)
            log "  执行 SQLite 迁移..."
            local DB_FILE="${SQLITE_PATH:-new-api.db}"
            if [ -f "$DB_FILE" ]; then
                sqlite3 "$DB_FILE" "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wechat_id ON users(wechat_id);" 2>&1 | tee -a "$LOG_FILE" || log "  ⚠ SQLite 迁移失败（可能索引已存在），继续"
                log_ok "SQLite 迁移完成"
            else
                log "  ⚠ SQLite 文件 $DB_FILE 不存在，跳过（开发环境可能使用内存数据库）"
            fi
            ;;
        *)
            log "  ⚠ 无法确定数据库类型，跳过 DB 迁移"
            log "  手动执行（按需）:"
            log "    PostgreSQL: CREATE UNIQUE INDEX idx_users_wechat_id ON users(wechat_id) WHERE wechat_id != '' AND deleted_at IS NULL;"
            log "    MySQL:      CREATE UNIQUE INDEX idx_users_wechat_id ON users(wechat_id);"
            ;;
    esac
}

# ============================================================
# 构建验证
# ============================================================
build_verify() {
    log_hdr "编译验证"
    cd "$PROJECT_DIR"

    local BUILD_OUTPUT
    BUILD_OUTPUT=$(go build -o /dev/null . 2>&1) || {
        log_err "编译失败:"
        echo "$BUILD_OUTPUT" | tee -a "$LOG_FILE"
        rollback
        log_err "已自动回滚所有代码改动"
        exit 1
    }
    log_ok "编译通过"
}

# ============================================================
# 变更摘要
# ============================================================
show_summary() {
    log_hdr "变更摘要"
    cd "$PROJECT_DIR"
    git diff -- model/user.go controller/token.go | tee -a "$LOG_FILE"

    log ""
    log "╔══════════════════════════════════════════════════════════╗"
    log "║                    部署完成                              ║"
    log "╠══════════════════════════════════════════════════════════╣"
    log "║  日志: $LOG_FILE"
    log "║                                                          ║"
    log "║  后续步骤:                                               ║"
    log "║    1. 重启服务:  systemctl restart new-api               ║"
    log "║    2. 验证测试:  curl ... -H 'x-user-id: test_123' ...  ║"
    log "║    3. 提交代码:  git add -A && git commit -m '...'       ║"
    log "║    4. 回滚:      git checkout model/user.go controller/token.go ║"
    log "║                                                          ║"
    log "║  封号操作 (SQL):                                         ║"
    log "║    UPDATE users SET status = 2 WHERE wechat_id='<openid>'; ║"
    log "╚══════════════════════════════════════════════════════════╝"
}

# ============================================================
# 主入口
# ============================================================
main() {
    cd "$PROJECT_DIR"

    log "╔══════════════════════════════════════════════════════════╗"
    log "║  x-user-id (openid) → new-api 账号体系 部署脚本         ║"
    log "║  启动: $(date '+%Y-%m-%d %H:%M:%S')                               ║"
    log "╚══════════════════════════════════════════════════════════╝"

    preflight

    if ! patch_user_model; then
        log_err "model/user.go 修改失败"; rollback; exit 1
    fi

    if ! patch_token_controller; then
        log_err "controller/token.go 修改失败"; rollback; exit 1
    fi

    apply_db_migration
    build_verify
    show_summary

    log "🏁 脚本执行完毕 ($(date '+%H:%M:%S'))"
}

# ============================================================
# 入口：始终通过 tmux 运行（允许脱离终端）
# $TMUX 由 tmux 自动设置，检测它防止递归
# ============================================================
if [ -z "${TMUX:-}" ]; then
    # 外层：启动 tmux 会话
    if ! command -v tmux &>/dev/null; then
        echo "[$(date '+%H:%M:%S')] ❌ ERROR: 需要 tmux，请先安装: apt install tmux"
        exit 1
    fi
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "[$(date '+%H:%M:%S')] tmux 会话 '$TMUX_SESSION' 已存在"
        echo "  查看: tmux attach -t $TMUX_SESSION"
        echo "  关闭: tmux kill-session -t $TMUX_SESSION"
        exit 1
    fi
    export LOG_FILE
    tmux new-session -d -s "$TMUX_SESSION" "bash $0 2>&1"
    echo "[$(date '+%H:%M:%S')] 已在 tmux 会话 '$TMUX_SESSION' 中启动"
    echo "  查看实时输出: tmux attach -t $TMUX_SESSION"
    echo "  脱离:          Ctrl+B, D"
    echo "  日志文件:      $LOG_FILE"
    sleep 2
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
        echo "  状态:          运行中 ✓"
    else
        echo "  状态:          已退出（检查日志排查原因）"
        tail -20 "$LOG_FILE"
    fi
else
    # 内层：在 tmux 中执行 main
    main
fi
