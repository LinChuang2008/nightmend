#!/usr/bin/env bash
# NightMend PostgreSQL 恢复脚本
# 用法: bash scripts/restore.sh <备份文件>
set -euo pipefail

ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5433}"
DB_NAME="${POSTGRES_DB:-nightmend}"
DB_USER="${POSTGRES_USER:-nightmend}"

if [ $# -lt 1 ] || [ "$1" = "--help" ]; then
    cat <<EOF
NightMend PostgreSQL 恢复工具

用法: $0 <备份文件.sql.gz>

⚠️ 警告: 恢复操作会覆盖当前数据库中的数据！

示例:
  $0 backups/nightmend_20260225_020000.sql.gz
EOF
    exit 0
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "错误: 备份文件不存在: $BACKUP_FILE" >&2
    exit 1
fi

echo "========================================"
echo "⚠️  即将恢复数据库: $DB_NAME"
echo "   备份文件: $BACKUP_FILE"
echo "   目标: ${DB_HOST}:${DB_PORT}"
echo "========================================"
echo ""
read -p "确认恢复？此操作会覆盖现有数据 (y/N): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "已取消恢复"
    exit 0
fi

echo "[$(date)] 开始恢复 ..."

if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q postgres; then
    CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | head -1)
    gunzip -c "$BACKUP_FILE" | docker exec -i "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"
elif command -v psql &>/dev/null; then
    PGPASSWORD="${POSTGRES_PASSWORD:-}" gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"
else
    echo "错误: 未找到 psql 或 Docker，无法执行恢复" >&2
    exit 1
fi

echo "[$(date)] 恢复完成!"
