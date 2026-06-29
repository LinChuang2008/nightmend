# NightMend-flavored Alertmanager：官方镜像 + envsubst + 启动脚本
# 只改 entrypoint，Alertmanager 本身版本由 FROM 锁定。
FROM prom/alertmanager:v0.27.0

USER root
# busybox 自带 sh，但无 envsubst；装 gettext 提供 envsubst
RUN apk add --no-cache gettext

COPY alertmanager.yml.template /etc/alertmanager/alertmanager.yml.template
COPY entrypoint.sh /usr/local/bin/nightmend-entrypoint.sh
RUN chmod +x /usr/local/bin/nightmend-entrypoint.sh

USER nobody
EXPOSE 9093
ENTRYPOINT ["/usr/local/bin/nightmend-entrypoint.sh"]
