"""
Windows 服务注册模块。

pywin32 标准方式：服务类继承 ServiceFramework，
通过 HandleCommandLine 处理 install/start/stop/remove。

用法（需管理员权限）：
    nightmend-agent service install   # 安装服务
    nightmend-agent service start     # 启动服务
    nightmend-agent service stop      # 停止服务
    nightmend-agent service restart   # 重启服务
    nightmend-agent service remove    # 卸载服务
    nightmend-agent service status    # 查看状态
"""
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_NAME = "NightMendAgent"
SERVICE_DISPLAY_NAME = "NightMend Monitoring Agent"
SERVICE_DESCRIPTION = "NightMend 轻量级监控代理，负责采集系统指标、服务健康检查和日志上报。"


def _require_pywin32() -> bool:
    try:
        import win32serviceutil  # noqa
        return True
    except ImportError:
        print("错误: 需要安装 pywin32。请运行: pip install pywin32")
        return False


# ---------------------------------------------------------------------------
# 服务类（运行时动态构建，避免非 Windows 环境 import 报错）
# ---------------------------------------------------------------------------
def _get_service_class():
    import win32serviceutil
    import win32service
    import win32event
    import servicemanager

    class NightMendAgentService(win32serviceutil.ServiceFramework):
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = SERVICE_DISPLAY_NAME
        _svc_description_ = SERVICE_DESCRIPTION

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._stop_event = win32event.CreateEvent(None, 0, 0, None)
            self._loop = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop_event)
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            try:
                self._run_agent()
            except Exception as e:
                servicemanager.LogErrorMsg(f"NightMend Agent service error: {e}")

        def _run_agent(self):
            import asyncio
            import socket
            import winreg
            from nightmend_agent.config import load_config
            from nightmend_agent.reporter import AgentReporter

            # 优先从注册表读取安装时记录的配置路径
            config_path = None
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r"SYSTEM\CurrentControlSet\Services\NightMendAgent\Parameters")
                config_path, _ = winreg.QueryValueEx(key, "ConfigPath")
                winreg.CloseKey(key)
            except Exception:
                pass

            # 回退：遍历常见路径
            if not config_path or not Path(config_path).exists():
                candidates = [
                    Path("C:/ProgramData/NightMend/config.yaml"),
                    Path("/etc/nightmend/config.yaml"),
                ]
                config_path = next((str(p) for p in candidates if p.exists()), None)

            if not config_path:
                raise FileNotFoundError(
                    "No config file found. Run 'nightmend-agent configure' first."
                )

            cfg = load_config(config_path)
            if not cfg.host.name:
                cfg.host.name = socket.gethostname()

            reporter = AgentReporter(cfg)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(reporter.start())

    return NightMendAgentService


# ---------------------------------------------------------------------------
# 公共操作函数
# ---------------------------------------------------------------------------

def install_service() -> bool:
    """安装 Windows 服务。使用 sc create 直接注册，更可靠。"""
    if not _require_pywin32():
        return False

    # 服务启动命令：python.exe <本模块路径> run_service
    python_exe = sys.executable
    module_path = str(Path(__file__).resolve())
    bin_path = f'"{python_exe}" "{module_path}" run_service'

    try:
        # 先删除旧服务（如果存在）
        subprocess.run(["sc", "stop", SERVICE_NAME], capture_output=True)
        subprocess.run(["sc", "delete", SERVICE_NAME], capture_output=True)

        # 创建服务
        result = subprocess.run([
            "sc", "create", SERVICE_NAME,
            "binPath=", bin_path,
            "DisplayName=", SERVICE_DISPLAY_NAME,
            "start=", "auto",
        ], capture_output=True, text=True)

        if result.returncode != 0:
            print(f"❌ 安装失败: {result.stderr or result.stdout}")
            return False

        # 设置描述
        subprocess.run([
            "sc", "description", SERVICE_NAME, SERVICE_DESCRIPTION
        ], capture_output=True)

        # 配置崩溃自动重启
        _configure_failure_recovery()

        # 把配置文件路径写入注册表，供服务启动时读取（服务以 SYSTEM 账户运行，无法访问用户目录）
        _save_config_path_to_registry()

        print(f"✅ 服务 '{SERVICE_DISPLAY_NAME}' 安装成功。")
        print(f"   运行 'nightmend-agent service start' 启动服务。")
        return True
    except Exception as e:
        print(f"❌ 安装失败: {e}")
        return False


def _configure_failure_recovery():
    try:
        subprocess.run([
            "sc", "failure", SERVICE_NAME,
            "reset=", "86400",
            "actions=", "restart/5000/restart/10000/restart/30000",
        ], capture_output=True, check=False)
    except Exception:
        pass


def _save_config_path_to_registry():
    """将当前用户的配置文件路径写入注册表，供服务（SYSTEM账户）启动时读取。"""
    try:
        import winreg
        config_path = str(Path.home() / ".nightmend" / "config.yaml")
        key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SYSTEM\CurrentControlSet\Services\NightMendAgent\Parameters")
        winreg.SetValueEx(key, "ConfigPath", 0, winreg.REG_SZ, config_path)
        winreg.CloseKey(key)
        print(f"   配置路径已记录: {config_path}")
    except Exception as e:
        print(f"   警告: 无法写入注册表: {e}")


def start_service() -> bool:
    if not _require_pywin32():
        return False
    import win32serviceutil
    try:
        win32serviceutil.StartService(SERVICE_NAME)
        print(f"✅ 服务 '{SERVICE_NAME}' 已启动。")
        return True
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        return False


def stop_service() -> bool:
    if not _require_pywin32():
        return False
    import win32serviceutil
    try:
        win32serviceutil.StopService(SERVICE_NAME)
        print(f"✅ 服务 '{SERVICE_NAME}' 已停止。")
        return True
    except Exception as e:
        print(f"❌ 停止失败: {e}")
        return False


def restart_service() -> bool:
    if not _require_pywin32():
        return False
    import win32serviceutil
    try:
        win32serviceutil.RestartService(SERVICE_NAME)
        print(f"✅ 服务 '{SERVICE_NAME}' 已重启。")
        return True
    except Exception as e:
        print(f"❌ 重启失败: {e}")
        return False


def remove_service() -> bool:
    if not _require_pywin32():
        return False
    try:
        subprocess.run(["sc", "stop", SERVICE_NAME], capture_output=True)
        result = subprocess.run(
            ["sc", "delete", SERVICE_NAME], capture_output=True, text=True
        )
        if result.returncode == 0:
            print(f"✅ 服务 '{SERVICE_NAME}' 已卸载。")
            return True
        else:
            print(f"❌ 卸载失败: {result.stderr or result.stdout}")
            return False
    except Exception as e:
        print(f"❌ 卸载失败: {e}")
        return False


def query_service_status() -> str:
    if not _require_pywin32():
        return "unknown"
    import win32serviceutil
    import win32service
    STATUS_MAP = {
        win32service.SERVICE_STOPPED: "stopped",
        win32service.SERVICE_START_PENDING: "starting",
        win32service.SERVICE_STOP_PENDING: "stopping",
        win32service.SERVICE_RUNNING: "running",
        win32service.SERVICE_PAUSED: "paused",
    }
    try:
        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
        return STATUS_MAP.get(status[1], "unknown")
    except Exception as e:
        return f"unknown ({e})"


# ---------------------------------------------------------------------------
# 服务入口：SCM 启动时直接执行本模块
# ---------------------------------------------------------------------------
def run_as_service():
    """由 SCM 调用，启动服务主循环。"""
    if not _require_pywin32():
        sys.exit(1)
    import servicemanager
    import win32serviceutil

    ServiceClass = _get_service_class()
    if len(sys.argv) == 1:
        # 被 SCM 直接调用
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(ServiceClass)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(ServiceClass)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run_service":
        # 移除 run_service 参数，让 HandleCommandLine 正常工作
        sys.argv.pop(1)
    run_as_service()
