#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Install NightMend Agent as a Windows Service using NSSM or sc.exe.
    使用 NSSM 或 sc.exe 将 NightMend Agent 注册为 Windows 服务。

.DESCRIPTION
    This script registers the NightMend Agent as a Windows service so it starts
    automatically on boot and runs in the background.
    本脚本将 NightMend Agent 注册为 Windows 服务，使其开机自启并在后台运行。

    Preferred method: NSSM (Non-Sucking Service Manager) — handles stdout/stderr
    logging, graceful restart, and process monitoring.
    推荐方式：NSSM — 支持标准输出日志、优雅重启和进程监控。

    Fallback method: sc.exe — built-in but requires the agent to implement
    Windows Service API (win32serviceutil).
    备选方式：sc.exe — 系统内置，但要求 agent 实现 Windows 服务 API。

.PARAMETER ServiceName
    The Windows service name. Default: NightMendAgent
    Windows 服务名。默认：NightMendAgent

.PARAMETER AgentExePath
    Path to the nightmend-agent executable (or python.exe).
    nightmend-agent 可执行文件（或 python.exe）路径。

.PARAMETER ConfigPath
    Path to agent.yaml config file.
    agent.yaml 配置文件路径。

.PARAMETER UseNSSM
    If set, use NSSM to install the service. NSSM must be in PATH.
    如果设置，使用 NSSM 安装服务。NSSM 必须在 PATH 中。

.EXAMPLE
    .\install-windows-service.ps1 -AgentExePath "C:\nightmend\venv\Scripts\nightmend-agent.exe" -ConfigPath "C:\ProgramData\nightmend\agent.yaml" -UseNSSM
#>

param(
    [string]$ServiceName = "NightMendAgent",
    [string]$AgentExePath = "",
    [string]$ConfigPath = "",
    [switch]$UseNSSM
)

$ErrorActionPreference = "Stop"

# -- Resolve default paths / 解析默认路径 --
if (-not $AgentExePath) {
    # Try to find nightmend-agent in PATH
    $found = Get-Command "nightmend-agent" -ErrorAction SilentlyContinue
    if ($found) {
        $AgentExePath = $found.Source
    } else {
        Write-Error "Cannot find nightmend-agent in PATH. Please specify -AgentExePath."
        exit 1
    }
}

if (-not $ConfigPath) {
    $ConfigPath = Join-Path $env:PROGRAMDATA "nightmend\agent.yaml"
}

# Verify paths / 验证路径
if (-not (Test-Path $AgentExePath)) {
    Write-Error "Agent executable not found: $AgentExePath"
    exit 1
}
if (-not (Test-Path $ConfigPath)) {
    Write-Warning "Config file not found: $ConfigPath (service will fail to start without it)"
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "NightMend Agent Windows Service Installer" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Service Name : $ServiceName"
Write-Host "Agent Exe    : $AgentExePath"
Write-Host "Config File  : $ConfigPath"
Write-Host ""

# -- Check if service already exists / 检查服务是否已存在 --
$existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existingService) {
    Write-Warning "Service '$ServiceName' already exists (Status: $($existingService.Status))."
    $confirm = Read-Host "Remove and reinstall? (y/N)"
    if ($confirm -ne "y") {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
    # Stop and remove existing service / 停止并移除已有服务
    if ($existingService.Status -eq "Running") {
        Write-Host "Stopping existing service..."
        Stop-Service -Name $ServiceName -Force
    }
    if ($UseNSSM) {
        & nssm remove $ServiceName confirm
    } else {
        sc.exe delete $ServiceName | Out-Null
    }
    Start-Sleep -Seconds 2
    Write-Host "Existing service removed." -ForegroundColor Green
}

# -- Install / 安装服务 --
if ($UseNSSM) {
    # Check NSSM availability / 检查 NSSM 是否可用
    if (-not (Get-Command "nssm" -ErrorAction SilentlyContinue)) {
        Write-Error "NSSM not found in PATH. Install from https://nssm.cc/ or use without -UseNSSM flag."
        exit 1
    }

    Write-Host "Installing via NSSM..." -ForegroundColor Green
    & nssm install $ServiceName "$AgentExePath" "run -c `"$ConfigPath`""
    & nssm set $ServiceName DisplayName "NightMend Monitoring Agent"
    & nssm set $ServiceName Description "NightMend lightweight monitoring agent for system metrics, service checks, and log collection."
    & nssm set $ServiceName Start SERVICE_AUTO_START
    & nssm set $ServiceName AppStopMethodSkip 0
    & nssm set $ServiceName AppStopMethodConsole 5000
    & nssm set $ServiceName AppStopMethodWindow 5000
    & nssm set $ServiceName AppStopMethodThreads 5000

    # Configure log output / 配置日志输出
    $logDir = Join-Path $env:PROGRAMDATA "nightmend\logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    & nssm set $ServiceName AppStdout (Join-Path $logDir "agent-stdout.log")
    & nssm set $ServiceName AppStderr (Join-Path $logDir "agent-stderr.log")
    & nssm set $ServiceName AppRotateFiles 1
    & nssm set $ServiceName AppRotateBytes 10485760  # 10 MB

    Write-Host "Service installed via NSSM." -ForegroundColor Green
} else {
    # Use sc.exe (built-in) / 使用 sc.exe（系统内置）
    Write-Host "Installing via sc.exe..." -ForegroundColor Green
    $binPath = "`"$AgentExePath`" run -c `"$ConfigPath`""
    sc.exe create $ServiceName `
        binPath= $binPath `
        start= auto `
        DisplayName= "NightMend Monitoring Agent"

    sc.exe description $ServiceName "NightMend lightweight monitoring agent for system metrics, service checks, and log collection."
    # Configure failure recovery: restart after 60s / 配置故障恢复：60秒后重启
    sc.exe failure $ServiceName reset= 86400 actions= restart/60000/restart/60000/restart/60000

    Write-Host "Service installed via sc.exe." -ForegroundColor Green
    Write-Host ""
    Write-Host "NOTE: sc.exe method works best when the agent supports Windows Service API." -ForegroundColor Yellow
    Write-Host "If the service fails to start, consider using NSSM (-UseNSSM flag)." -ForegroundColor Yellow
}

# -- Start service / 启动服务 --
Write-Host ""
$startNow = Read-Host "Start service now? (Y/n)"
if ($startNow -ne "n") {
    Write-Host "Starting service..."
    Start-Service -Name $ServiceName
    Start-Sleep -Seconds 2
    $svc = Get-Service -Name $ServiceName
    if ($svc.Status -eq "Running") {
        Write-Host "Service '$ServiceName' is running." -ForegroundColor Green
    } else {
        Write-Warning "Service status: $($svc.Status). Check logs for errors."
    }
}

Write-Host ""
Write-Host "Done. Manage with:" -ForegroundColor Cyan
Write-Host "  Start-Service $ServiceName"
Write-Host "  Stop-Service $ServiceName"
Write-Host "  Restart-Service $ServiceName"
Write-Host "  Get-Service $ServiceName"
