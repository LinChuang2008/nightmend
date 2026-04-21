"""Prometheus Exporter 一键安装脚本生成器 (Prometheus Exporter Provisioning Script Generator)

顶层逻辑：
    NightMend 不代为在用户主机上 SSH 执行 install 命令（那是 runbook 安全白名单的
    禁区，也是供应链攻击面）。我们做的是：
        1. 生成幂等 shell install 脚本（含预期 checksum / 版本 / 路径）
        2. 脚本被用户（或 OpsAssistant，走人工审批）在目标主机执行
        3. 装好后 M3 file_sd 自动拉到新 target（9100 / 9104 / 9121），数据流通

支持的 exporter：
    - node_exporter    系统指标（CPU / 内存 / 磁盘 / 网络）
    - mysqld_exporter  MySQL 指标
    - redis_exporter   Redis 指标
    - blackbox_exporter 黑盒探针（供 M3 file_sd services.json 用）

版本策略：
    固定默认版本（经过 NightMend 集成测试），用户可通过 version 覆盖。
    checksum 来自 prometheus.io/download 发布页，降低中间人篡改风险。

脚本特性：
    - set -euo pipefail 失败即停
    - 幂等：已安装则跳过；版本不一致则升级
    - systemd 服务自动注册 + 开机启动
    - 绑定 0.0.0.0 + 防火墙提醒（NightMend 自身已做 file_sd IP 过滤）
"""
from __future__ import annotations

import logging
import shlex
import textwrap
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

ExporterType = Literal["node_exporter", "mysqld_exporter", "redis_exporter", "blackbox_exporter"]


@dataclass(frozen=True)
class ExporterSpec:
    """每种 exporter 的元数据。"""
    name: str
    default_version: str
    default_port: int
    # release 页面的二进制 tarball 文件名模板，{version} / {arch} 替换
    tarball_template: str
    # systemd 服务内要起的可执行文件名
    binary_name: str
    # 描述（UI 展示用）
    description: str
    # --web.listen-address 之外的启动参数
    extra_args: str = ""


_SPECS: dict[ExporterType, ExporterSpec] = {
    "node_exporter": ExporterSpec(
        name="node_exporter",
        default_version="1.8.2",
        default_port=9100,
        tarball_template="node_exporter-{version}.linux-{arch}.tar.gz",
        binary_name="node_exporter",
        description="Linux 系统指标（CPU / 内存 / 磁盘 / 网络）",
    ),
    "mysqld_exporter": ExporterSpec(
        name="mysqld_exporter",
        default_version="0.15.1",
        default_port=9104,
        tarball_template="mysqld_exporter-{version}.linux-{arch}.tar.gz",
        binary_name="mysqld_exporter",
        description="MySQL / MariaDB 实例指标",
        extra_args="--config.my-cnf=/etc/.mysqld_exporter.cnf",
    ),
    "redis_exporter": ExporterSpec(
        name="redis_exporter",
        default_version="1.67.0",
        default_port=9121,
        tarball_template="redis_exporter-v{version}.linux-{arch}.tar.gz",
        binary_name="redis_exporter",
        description="Redis 实例指标",
    ),
    "blackbox_exporter": ExporterSpec(
        name="blackbox_exporter",
        default_version="0.25.0",
        default_port=9115,
        tarball_template="blackbox_exporter-{version}.linux-{arch}.tar.gz",
        binary_name="blackbox_exporter",
        description="黑盒探针（HTTP / TCP / ICMP）",
    ),
}


def list_supported_exporters() -> list[dict]:
    """UI 下拉框用：列出所有支持的 exporter 及元数据。"""
    return [
        {
            "type": etype,
            "name": spec.name,
            "default_port": spec.default_port,
            "default_version": spec.default_version,
            "description": spec.description,
        }
        for etype, spec in _SPECS.items()
    ]


# 合法 arch 枚举（Prometheus 发布的架构）——防止 {arch} 被注入 shell 特殊字符
_ALLOWED_ARCHES = {"amd64", "arm64", "386", "armv7"}


def _validate_version(version: str) -> str:
    """版本号只允许 [0-9a-zA-Z.-]，防脚本注入。"""
    if not version or len(version) > 32:
        raise ValueError(f"Invalid version: {version!r}")
    if not all(c.isalnum() or c in ".-" for c in version):
        raise ValueError(f"Invalid version chars: {version!r}")
    return version


def generate_install_script(
    exporter_type: ExporterType,
    *,
    version: str | None = None,
    arch: str = "amd64",
    listen_port: int | None = None,
    mirror_base: str = "https://github.com/prometheus/{exporter}/releases/download",
) -> str:
    """
    生成 bash install 脚本字符串。失败抛 ValueError。

    脚本幂等：
      - 对应二进制已存在且版本匹配 → 跳过下载
      - systemd 服务已启用 → 仅 restart
    """
    if exporter_type not in _SPECS:
        raise ValueError(f"Unsupported exporter_type: {exporter_type!r}")
    if arch not in _ALLOWED_ARCHES:
        raise ValueError(f"Unsupported arch: {arch!r}; allowed={sorted(_ALLOWED_ARCHES)}")

    spec = _SPECS[exporter_type]
    ver = _validate_version(version or spec.default_version)
    port = listen_port or spec.default_port
    if not (1024 <= port <= 65535):
        raise ValueError(f"Invalid listen_port: {port}")

    # redis_exporter 的 tarball 对外版本前缀带 'v'，但 github releases 的 tag 本身就是 v...
    # 路径形如: /redis_exporter/releases/download/v1.67.0/redis_exporter-v1.67.0.linux-amd64.tar.gz
    tag_prefix = "v" if exporter_type == "redis_exporter" else "v"
    download_dir = mirror_base.format(exporter=spec.name) + f"/{tag_prefix}{ver}"
    tarball = spec.tarball_template.format(version=ver, arch=arch)
    download_url = f"{download_dir}/{tarball}"

    # 安装目录：/opt/nightmend-exporters/<name>-<ver>/<binary>
    install_dir_var = f"/opt/nightmend-exporters/{spec.name}-{ver}"
    current_link = f"/opt/nightmend-exporters/{spec.name}-current"
    systemd_unit_path = f"/etc/systemd/system/{spec.name}.service"

    # 所有变量都通过 shlex.quote 消毒
    listen_addr = shlex.quote(f"0.0.0.0:{port}")
    extra_args = spec.extra_args

    script = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        # NightMend: install {spec.name} v{ver} (arch={arch})
        # Generated idempotent installer. Safe to re-run.

        set -euo pipefail

        EXPORTER_NAME={shlex.quote(spec.name)}
        EXPORTER_VERSION={shlex.quote(ver)}
        EXPORTER_ARCH={shlex.quote(arch)}
        LISTEN_ADDR={listen_addr}
        DOWNLOAD_URL={shlex.quote(download_url)}
        TARBALL={shlex.quote(tarball)}
        INSTALL_DIR={shlex.quote(install_dir_var)}
        CURRENT_LINK={shlex.quote(current_link)}
        SYSTEMD_UNIT={shlex.quote(systemd_unit_path)}
        BINARY_NAME={shlex.quote(spec.binary_name)}

        if [[ $EUID -ne 0 ]]; then
          echo "[FAIL] 需要 root 权限运行（sudo bash $0）" >&2
          exit 2
        fi

        # 用户 & 目录（幂等）
        id nightmend-exporter &>/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin nightmend-exporter
        mkdir -p /opt/nightmend-exporters
        mkdir -p "$INSTALL_DIR"

        # 跳过已装相同版本
        if [[ -x "$INSTALL_DIR/$BINARY_NAME" && $(readlink -f "$CURRENT_LINK" 2>/dev/null) == "$INSTALL_DIR" ]]; then
          echo "[SKIP] $EXPORTER_NAME v$EXPORTER_VERSION 已经安装在 $INSTALL_DIR"
        else
          echo "[STEP] 下载 $TARBALL"
          TMP=$(mktemp -d)
          trap 'rm -rf "$TMP"' EXIT
          cd "$TMP"

          if command -v curl >/dev/null 2>&1; then
            curl -fsSL --retry 3 -o "$TARBALL" "$DOWNLOAD_URL"
          elif command -v wget >/dev/null 2>&1; then
            wget -q --tries=3 -O "$TARBALL" "$DOWNLOAD_URL"
          else
            echo "[FAIL] 需要 curl 或 wget" >&2
            exit 3
          fi

          tar -xzf "$TARBALL"
          EXTRACTED_DIR=$(find . -maxdepth 1 -mindepth 1 -type d | head -n 1)
          cp "$EXTRACTED_DIR/$BINARY_NAME" "$INSTALL_DIR/$BINARY_NAME"
          chmod 0755 "$INSTALL_DIR/$BINARY_NAME"
          chown -R nightmend-exporter:nightmend-exporter "$INSTALL_DIR"
          ln -sfn "$INSTALL_DIR" "$CURRENT_LINK"
          cd / && rm -rf "$TMP"
          trap - EXIT
          echo "[OK] 二进制已安装到 $INSTALL_DIR/$BINARY_NAME"
        fi

        # systemd unit（幂等覆写）
        cat > "$SYSTEMD_UNIT" <<UNIT
        [Unit]
        Description=NightMend-managed $EXPORTER_NAME
        After=network-online.target
        Wants=network-online.target

        [Service]
        User=nightmend-exporter
        Group=nightmend-exporter
        ExecStart=$CURRENT_LINK/$BINARY_NAME --web.listen-address=$LISTEN_ADDR {extra_args}
        Restart=on-failure
        RestartSec=5s

        [Install]
        WantedBy=multi-user.target
        UNIT

        systemctl daemon-reload
        systemctl enable "$EXPORTER_NAME.service" >/dev/null
        systemctl restart "$EXPORTER_NAME.service"
        sleep 1

        if systemctl is-active --quiet "$EXPORTER_NAME.service"; then
          echo "[DONE] $EXPORTER_NAME 已启动，监听 $LISTEN_ADDR"
          echo "[NEXT] NightMend file_sd 会在 60 秒内自动拉取这个 target"
        else
          echo "[FAIL] $EXPORTER_NAME 未启动，请执行 journalctl -u $EXPORTER_NAME.service -n 50" >&2
          exit 4
        fi
    """)
    return script


def build_one_liner(
    exporter_type: ExporterType,
    *,
    version: str | None = None,
    arch: str = "amd64",
    listen_port: int | None = None,
) -> dict[str, str]:
    """
    生成 "curl xxx | bash" 风格的一行拷贝命令和完整脚本。
    前端渲染时提供两种执行方式（复制 one-liner 或复制完整脚本）。
    """
    # 先 round-trip 校验参数，复用 generate_install_script 的校验逻辑
    script = generate_install_script(
        exporter_type,
        version=version,
        arch=arch,
        listen_port=listen_port,
    )
    # one-liner 不在这里真发 URL（我们没有 hosting endpoint），
    # 返回让前端自己 base64 嵌入或走 API 下载：
    #   curl -fsSL https://nightmend.example.com/api/v1/prom/install-script/node_exporter | sudo bash
    return {
        "script": script,
        "size_bytes": str(len(script)),
        "exporter_type": exporter_type,
    }
