#!/bin/sh
# Alertmanager entrypoint：用 envsubst 渲染 template → 真实配置，再 exec 官方 binary。
#
# 环境变量：
#   NIGHTMEND_WEBHOOK_URL         例如 http://backend:8000/api/v1/webhooks/alertmanager
#   ALERTMANAGER_WEBHOOK_TOKEN    与 NightMend settings.alertmanager_webhook_token 一致
set -eu

TEMPLATE_PATH="${ALERTMANAGER_TEMPLATE:-/etc/alertmanager/alertmanager.yml.template}"
OUTPUT_PATH="${ALERTMANAGER_CONFIG:-/etc/alertmanager/alertmanager.yml}"

: "${NIGHTMEND_WEBHOOK_URL:?NIGHTMEND_WEBHOOK_URL is required}"
: "${ALERTMANAGER_WEBHOOK_TOKEN:?ALERTMANAGER_WEBHOOK_TOKEN is required (must match NightMend settings)}"

# 只渲染已知变量，防止意外展开 $foo
export NIGHTMEND_WEBHOOK_URL ALERTMANAGER_WEBHOOK_TOKEN
envsubst '${NIGHTMEND_WEBHOOK_URL} ${ALERTMANAGER_WEBHOOK_TOKEN}' \
    < "$TEMPLATE_PATH" > "$OUTPUT_PATH"

# 启动 Alertmanager，其他参数透传
exec /bin/alertmanager \
    --config.file="$OUTPUT_PATH" \
    --storage.path=/alertmanager \
    --web.listen-address=:9093 \
    "$@"
