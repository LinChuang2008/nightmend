#Requires -RunAsAdministrator
<#
.SYNOPSIS
    One-click installer for NightMend Agent on Windows.
    NightMend Agent Windows 一键安装脚本。

.DESCRIPTION
    This script performs a complete installation of NightMend Agent on Windows:
    本脚本在 Windows 上执行 NightMend Agent 的完整安装：

    1. Check Python 3.9+ availability / 检查 Python 3.9+ 是否可用
    2. Create virtual environment / 创建虚拟环境
    3. Install nightmend-agent package / 安装 nightmend-agent 包
    4. Create default config directory and template / 创建默认配置目录和模板
    5. Optionally install as Windows service / 可选安装为 Windows 服务

.PARAMETER InstallDir
    Installation directory. Default: C:\nightmend
    安装目录。默认：C:\nightmend

.PARAMETER ServerUrl
    NightMend server URL. Default: http://localhost:8001
    NightMend 服务端地址。默认：http://localhost:8001

.PARAMETER Token
    Agent authentication token.
    Agent 认证令牌。

.PARAMETER InstallService
    If set, install as Windows service after package installation.
    如果设置，在安装包后自动注册为 Windows 服务。

.PARAMETER UseNSSM
    If set along with -InstallService, use NSSM for service registration.
    如果与 -InstallService 一起设置，使用 NSSM 注册服务。

.EXAMPLE
    .\install-windows-agent.ps1 -Token "your-token-here" -ServerUrl "https://nightmend.example.com" -InstallService
#>

param(
    [string]$InstallDir = "C:\nightmend",
    [string]$ServerUrl = "http://localhost:8001",
    [string]$Token = "",
    [switch]$InstallService,
    [switch]$UseNSSM
)

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "NightMend Agent - Windows One-Click Installer" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ---- Step 1: Check Python / 检查 Python ----
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
$python = $null
foreach ($cmd in @("python", "python3", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        $ver = & $found.Source --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 9) {
                $python = $found.Source
                Write-Host "  Found: $ver at $python" -ForegroundColor Green
                break
            }
        }
    }
}
if (-not $python) {
    Write-Error "Python 3.9+ is required but not found. Please install from https://www.python.org/downloads/"
    exit 1
}

# ---- Step 2: Create install directory and venv / 创建安装目录和虚拟环境 ----
Write-Host "[2/5] Setting up virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}

$venvDir = Join-Path $InstallDir "venv"
if (-not (Test-Path $venvDir)) {
    Write-Host "  Creating virtual environment at $venvDir..."
    & $python -m venv $venvDir
}

$pipExe = Join-Path $venvDir "Scripts\pip.exe"
$agentExe = Join-Path $venvDir "Scripts\nightmend-agent.exe"

if (-not (Test-Path $pipExe)) {
    Write-Error "pip not found in virtual environment. Installation may be corrupted."
    exit 1
}

Write-Host "  Virtual environment ready." -ForegroundColor Green

# ---- Step 3: Install package / 安装 Agent 包 ----
Write-Host "[3/5] Installing nightmend-agent..." -ForegroundColor Yellow
& $pipExe install --upgrade pip 2>&1 | Out-Null
& $pipExe install nightmend-agent
if ($LASTEXITCODE -ne 0) {
    Write-Warning "PyPI install failed. Trying local install from source..."
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $projectDir = Split-Path -Parent $scriptDir
    if (Test-Path (Join-Path $projectDir "pyproject.toml")) {
        & $pipExe install $projectDir
    } else {
        Write-Error "Failed to install nightmend-agent. Check network or provide the package."
        exit 1
    }
}
Write-Host "  Package installed." -ForegroundColor Green

# ---- Step 4: Create config / 创建配置文件 ----
Write-Host "[4/5] Setting up configuration..." -ForegroundColor Yellow
$configDir = Join-Path $env:PROGRAMDATA "nightmend"
$configFile = Join-Path $configDir "agent.yaml"

if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

# Create logs directory / 创建日志目录
$logDir = Join-Path $configDir "logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if (-not (Test-Path $configFile)) {
    # Generate default config / 生成默认配置
    $configContent = @"
# NightMend Agent Configuration / NightMend Agent 配置文件
# Generated on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

server:
  url: "$ServerUrl"
  token: "$Token"

host:
  name: ""          # Leave empty to auto-detect / 留空自动检测
  display_name: ""
  tags: []

metrics:
  interval: 15      # Seconds / 秒

discovery:
  docker: true
  host_services: true
  interval: 30

services: []

log_sources: []

databases: []
"@
    Set-Content -Path $configFile -Value $configContent -Encoding UTF8
    Write-Host "  Config created: $configFile" -ForegroundColor Green
    if (-not $Token) {
        Write-Warning "  No token specified. Edit $configFile and set server.token before starting."
    }
} else {
    Write-Host "  Config already exists: $configFile (skipped)" -ForegroundColor Green
}

# ---- Step 5: Optionally install service / 可选安装服务 ----
if ($InstallService) {
    Write-Host "[5/5] Installing Windows service..." -ForegroundColor Yellow
    $serviceScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "install-windows-service.ps1"
    if (Test-Path $serviceScript) {
        $svcParams = @{
            ServiceName  = "NightMendAgent"
            AgentExePath = $agentExe
            ConfigPath   = $configFile
        }
        if ($UseNSSM) {
            $svcParams["UseNSSM"] = $true
        }
        & $serviceScript @svcParams
    } else {
        Write-Warning "Service install script not found: $serviceScript"
        Write-Host "  You can install the service manually later." -ForegroundColor Yellow
    }
} else {
    Write-Host "[5/5] Skipping service installation (use -InstallService to enable)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Quick start:" -ForegroundColor Cyan
Write-Host "  1. Edit config: $configFile"
Write-Host "  2. Run agent:   $agentExe run -c `"$configFile`""
Write-Host ""
Write-Host "Or install as service:" -ForegroundColor Cyan
Write-Host "  .\install-windows-service.ps1 -AgentExePath `"$agentExe`" -ConfigPath `"$configFile`""
