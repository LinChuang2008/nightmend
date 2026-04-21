"""Exporter 安装脚本生成器 + 分发端点测试。

覆盖点：
  服务层：
    - 4 种 exporter 默认元数据
    - 版本 / arch / port 非法 → ValueError
    - 版本 shell 注入防护
    - 脚本形状：set -euo pipefail / systemd unit / 0.0.0.0:port bind / sudo 提示
  路由层：
    - /exporters 列表（admin 可访问）
    - /install-script/{type} 返回 text/x-shellscript + Content-Disposition
    - 非法 exporter type → 4xx
    - viewer 访问 install-script → 403（operator-only）
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services import exporter_provisioning as ep


# ─── 服务层纯函数 ────────────────────────────────────────────────────


def test_list_supported_exporters_shape():
    items = ep.list_supported_exporters()
    types = {item["type"] for item in items}
    assert types == {"node_exporter", "mysqld_exporter", "redis_exporter", "blackbox_exporter"}
    for item in items:
        assert item["default_port"] > 0
        assert item["default_version"]
        assert item["description"]


def test_generate_install_script_node_exporter_default():
    script = ep.generate_install_script("node_exporter")
    assert script.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in script
    assert "node_exporter" in script
    assert "0.0.0.0:9100" in script
    assert "systemctl daemon-reload" in script
    assert "systemctl enable" in script
    assert "EUID -ne 0" in script  # 有 sudo 提示
    assert "github.com/prometheus/node_exporter/releases/download/v1.8.2" in script


def test_generate_install_script_custom_port_and_version():
    script = ep.generate_install_script("node_exporter", version="1.7.0", listen_port=19100)
    assert "1.7.0" in script
    assert "0.0.0.0:19100" in script
    assert "v1.7.0" in script


def test_generate_install_script_arm64():
    script = ep.generate_install_script("node_exporter", arch="arm64")
    assert "linux-arm64.tar.gz" in script


def test_generate_install_script_rejects_unsupported_arch():
    with pytest.raises(ValueError, match="Unsupported arch"):
        ep.generate_install_script("node_exporter", arch="sparc64")


def test_generate_install_script_rejects_invalid_port():
    with pytest.raises(ValueError, match="Invalid listen_port"):
        ep.generate_install_script("node_exporter", listen_port=80)
    with pytest.raises(ValueError, match="Invalid listen_port"):
        ep.generate_install_script("node_exporter", listen_port=70000)


def test_generate_install_script_rejects_shell_injection_version():
    """version 含非字母数字/点/连字符必须被拒，防脚本注入。"""
    for bad in ("1.8.2; rm -rf /", "1.8$(whoami)", "1.8`id`", "1.8 && curl evil"):
        with pytest.raises(ValueError, match="Invalid version"):
            ep.generate_install_script("node_exporter", version=bad)


def test_generate_install_script_rejects_unknown_exporter():
    with pytest.raises(ValueError, match="Unsupported exporter_type"):
        ep.generate_install_script("prometheus_itself")  # type: ignore[arg-type]


def test_all_four_exporters_produce_valid_scripts():
    for etype in ("node_exporter", "mysqld_exporter", "redis_exporter", "blackbox_exporter"):
        script = ep.generate_install_script(etype)
        assert "#!/usr/bin/env bash" in script
        assert etype in script
        assert "systemctl enable" in script


def test_mysqld_exporter_includes_my_cnf_flag():
    script = ep.generate_install_script("mysqld_exporter")
    assert "--config.my-cnf=/etc/.mysqld_exporter.cnf" in script


def test_build_one_liner_returns_script_and_size():
    result = ep.build_one_liner("node_exporter")
    assert "script" in result
    assert "size_bytes" in result
    assert int(result["size_bytes"]) == len(result["script"])
    assert result["exporter_type"] == "node_exporter"


# ─── 路由层 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_exporters_endpoint(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/prom/exporters", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    types = {item["type"] for item in data}
    assert "node_exporter" in types
    assert len(data) == 4


@pytest.mark.asyncio
async def test_install_script_returns_shellscript(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/prom/install-script/node_exporter",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/x-shellscript")
    assert "install-node_exporter.sh" in response.headers.get("content-disposition", "")
    assert response.headers["x-nightmend-exporter"] == "node_exporter"
    assert "set -euo pipefail" in response.text


@pytest.mark.asyncio
async def test_install_script_json_wrapper(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/prom/install-script/node_exporter/json",
        headers=auth_headers,
        params={"version": "1.7.0", "arch": "arm64"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["exporter_type"] == "node_exporter"
    assert "1.7.0" in body["script"]
    assert "linux-arm64.tar.gz" in body["script"]


@pytest.mark.asyncio
async def test_install_script_rejects_bad_version(client: AsyncClient, auth_headers):
    response = await client.get(
        "/api/v1/prom/install-script/node_exporter",
        headers=auth_headers,
        params={"version": "1.8; evil"},
    )
    assert response.status_code == 400
    assert "Invalid version" in response.text


@pytest.mark.asyncio
async def test_install_script_unknown_exporter_returns_4xx(client: AsyncClient, auth_headers):
    # FastAPI Literal 校验失败会返回 422
    response = await client.get(
        "/api/v1/prom/install-script/prometheus_itself",
        headers=auth_headers,
    )
    assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_install_script_requires_operator(client: AsyncClient, viewer_headers):
    """viewer 不能下载 install script（operator 权限）。"""
    response = await client.get(
        "/api/v1/prom/install-script/node_exporter",
        headers=viewer_headers,
    )
    assert response.status_code == 403
