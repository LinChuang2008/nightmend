"""
VigilOps Agent 命令行入口模块。

提供 CLI 命令：run（前台运行 Agent）和 check（验证配置文件）。

首次运行时若无配置文件，交互式引导用户输入服务端 URL 和 Token，
并保存到 ~/.vigilops/config.yaml，后续自动读取。
"""
import asyncio
import logging
import signal
import socket
import sys
from pathlib import Path

import click

from vigilops_agent import __version__
from vigilops_agent.config import load_config

# 用户级配置目录和文件路径
USER_CONFIG_DIR = Path.home() / ".vigilops"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.yaml"

# 项目级默认配置路径（Linux 系统服务场景）
SYSTEM_CONFIG_FILE = Path("/etc/vigilops/agent.yaml")


def _get_default_config_path() -> str:
    """按优先级返回配置文件路径：用户目录 > 系统目录。"""
    if USER_CONFIG_FILE.exists():
        return str(USER_CONFIG_FILE)
    if SYSTEM_CONFIG_FILE.exists():
        return str(SYSTEM_CONFIG_FILE)
    # 都不存在时返回用户目录路径（首次运行会在此创建）
    return str(USER_CONFIG_FILE)


def _prompt_and_save_config() -> str:
    """首次运行时交互式引导用户输入配置，保存到 ~/.vigilops/config.yaml。"""
    click.echo("=" * 50)
    click.echo("VigilOps Agent - 首次运行配置")
    click.echo("=" * 50)
    click.echo(f"配置将保存到: {USER_CONFIG_FILE}")
    click.echo()

    server_url = click.prompt("服务端地址 (例: http://192.168.1.100:8000)", type=str).strip().rstrip("/")
    token = click.prompt("Agent Token", type=str).strip()
    display_name = click.prompt("主机显示名称 (可选，直接回车跳过)", default="", show_default=False).strip()

    config_content = f"""server:
  url: {server_url}
  token: "{token}"

host:
  name: ""  # 留空则自动使用主机名
  display_name: "{display_name}"
  tags: []

metrics:
  interval: 15s

discovery:
  docker: true
  host_services: true
  interval: 30s
"""

    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG_FILE.write_text(config_content, encoding="utf-8")
    click.echo(f"\n配置已保存到 {USER_CONFIG_FILE}")
    return str(USER_CONFIG_FILE)


@click.group(invoke_without_command=True)
@click.option("--config", "-c", default=None, help="Config file path (default: ~/.vigilops/config.yaml)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.version_option(version=__version__)
@click.pass_context
def cli(ctx, config, verbose):
    """VigilOps Agent - 轻量级监控代理。"""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config  # None 表示自动选择
    ctx.obj["verbose"] = verbose

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if ctx.invoked_subcommand is None:
        click.echo(f"VigilOps Agent v{__version__}")
        click.echo(f"Config: {config or _get_default_config_path()}")
        click.echo("Use --help for available commands")


@cli.command()
@click.pass_context
def run(ctx):
    """以前台模式运行 Agent。"""
    logger = logging.getLogger("vigilops-agent")
    config_path = ctx.obj.get("config_path")

    # 未指定配置文件时自动选择
    if not config_path:
        config_path = _get_default_config_path()

    # 配置文件不存在时引导首次配置
    if not Path(config_path).exists():
        click.echo(f"未找到配置文件: {config_path}")
        config_path = _prompt_and_save_config()

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not cfg.server.token:
        click.echo("Error: No agent token configured. Set server.token in config or VIGILOPS_TOKEN env.", err=True)
        sys.exit(1)

    if not cfg.host.name:
        cfg.host.name = socket.gethostname()

    logger.info(f"Starting VigilOps Agent v{__version__}")
    logger.info(f"Server: {cfg.server.url}")
    logger.info(f"Host: {cfg.host.name}")
    logger.info(f"Config: {config_path}")

    from vigilops_agent.reporter import AgentReporter

    reporter = AgentReporter(cfg)
    loop = asyncio.new_event_loop()

    def _shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        loop.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        loop.run_until_complete(reporter.start())
    except Exception:
        logger.exception("Agent crashed")
        sys.exit(1)


@cli.command()
@click.pass_context
def check(ctx):
    """验证配置文件是否正确。"""
    config_path = ctx.obj.get("config_path") or _get_default_config_path()
    try:
        cfg = load_config(config_path)
        click.echo(f"✅ Config OK: {config_path}")
        click.echo(f"   Server: {cfg.server.url}")
        click.echo(f"   Host: {cfg.host.name or '(auto-detect)'}")
        click.echo(f"   Metrics interval: {cfg.metrics.interval}s")
        click.echo(f"   Services: {len(cfg.services)}")
        click.echo(f"   Log sources: {len(cfg.log_sources)}")
    except Exception as e:
        click.echo(f"❌ Config error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.pass_context
def configure(ctx):
    """重新配置服务端地址和 Token。"""
    _prompt_and_save_config()
    click.echo("配置完成，运行 'vigilops-agent run' 启动 Agent。")


@cli.group()
def service():
    """Windows 服务管理（需管理员权限）。"""
    if sys.platform != "win32":
        click.echo("错误: service 命令仅支持 Windows。", err=True)
        sys.exit(1)


@service.command("install")
def service_install():
    """安装并注册为 Windows 系统服务（开机自启）。"""
    # 首先确保配置文件存在
    if not USER_CONFIG_FILE.exists() and not Path("/etc/vigilops/agent.yaml").exists():
        click.echo("未找到配置文件，请先完成配置：")
        _prompt_and_save_config()

    from vigilops_agent.service.windows import install_service
    install_service()


@service.command("start")
def service_start():
    """启动 Windows 服务。"""
    from vigilops_agent.service.windows import start_service
    start_service()


@service.command("stop")
def service_stop():
    """停止 Windows 服务。"""
    from vigilops_agent.service.windows import stop_service
    stop_service()


@service.command("restart")
def service_restart():
    """重启 Windows 服务。"""
    from vigilops_agent.service.windows import restart_service
    restart_service()


@service.command("remove")
def service_remove():
    """卸载 Windows 服务。"""
    from vigilops_agent.service.windows import remove_service
    remove_service()


@service.command("status")
def service_status():
    """查看 Windows 服务运行状态。"""
    from vigilops_agent.service.windows import query_service_status
    status = query_service_status()
    click.echo(f"服务状态: {status}")


def main():
    """CLI 入口函数。"""
    cli()


if __name__ == "__main__":
    main()
