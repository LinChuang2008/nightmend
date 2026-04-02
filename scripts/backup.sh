#!/usr/bin/env bash
# NightMend PostgreSQL 备份脚本
# 用法: bash scripts/backup.sh [--backup-dir DIR] [--keep-days N]
set -euo pipefail

# 默认参数
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"

# 从 .env 读取数据库配置（如果存在）
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    set -a; source "$ENV_FILE"; set +a
fi

DB_HOST="${POSTGRES_HOST:-localhost}"
DB_PORT="${POSTGRES_PORT:-5433}"
DB_NAME="${POSTGRES_DB:-nightmend}"
DB_USER="${POSTGRES_USER:-nightmend}"

usage() {
    cat <<EOF
NightMend PostgreSQL 备份工具

用法: $0 [OPTIONS]

选项:
  --backup-dir DIR   备份目录 (默认: ./backups)
  --keep-days N      保留天数 (默认: 7)
  --help             显示帮助

环境变量:
  POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
  或通过 .env 文件设置

示例:
  $0                                    # 使用默认配置备份
  $0 --backup-dir /data/backups         # 指定备份目录
  $0 --keep-days 14                     # 保留 14 天

设置 cron 自动备份 (每天凌晨 2 点):
  0 2 * * * cd /path/to/nightmend && bash scripts/backup.sh >> logs/backup.log 2>&1
EOF
    exit 0
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir) BACKUP_DIR="$2"; shift 2 ;;
        --keep-days)  KEEP_DAYS="$2"; shift 2 ;;
        --help)       usage ;;
        *) echo "未知参数: $1"; usage ;;
    esac
done

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="nightmend_${TIMESTAMP}.sql.gz"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

echo "[$(date)] 开始备份 ${DB_NAME}@${DB_HOST}:${DB_PORT} ..."

# 使用 docker exec 或本地 pg_dump
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q postgres; then
    # Docker 环境：通过容器内 pg_dump
    CONTAINER=$(docker ps --format '{{.Names}}' | grep postgres | head -1)
    docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILEPATH"
elif command -v pg_dump &>/dev/null; then
    # 本地 pg_dump
    PGPASSWORD="${POSTGRES_PASSWORD:-}" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME" | gzip > "$FILEPATH"
else
    echo "错误: 未找到 pg_dump 或 Docker，无法执行备份" >&2
    exit 1
fi

SIZE=$(du -h "$FILEPATH" | cut -f1)
echo "[$(date)] 备份完成: $FILEPATH ($SIZE)"

# 自动轮转：删除超过 KEEP_DAYS 天的备份
DELETED=$(find "$BACKUP_DIR" -name "nightmend_*.sql.gz" -mtime +"$KEEP_DAYS" -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] 已清理 ${DELETED} 个过期备份 (>${KEEP_DAYS} 天)"
fi

echo "[$(date)] 当前备份文件:"
ls -lh "$BACKUP_DIR"/nightmend_*.sql.gz 2>/dev/null || echo "  (无)"
