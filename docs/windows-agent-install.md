# Windows 客户端安装指南

## 前置条件

- Windows 10 / Windows Server 2016 及以上
- Python 3.9+（推荐使用 conda 或官方安装包）
- 管理员权限（注册系统服务时需要）
- 已从 NightMend 管理后台获取 Agent Token

---

## 一、安装 Python 环境

推荐使用 conda 创建独立虚拟环境，避免依赖冲突：

```powershell
conda create -n nightmend python=3.9 -y
conda activate nightmend
```

也可以使用系统 Python 或其他虚拟环境工具（venv、pyenv 等）。

---

## 二、安装 Agent

有两种方式，选其一即可。

### 方式 A：使用 wheel 包安装（推荐）

从 NightMend 管理后台由管理员通过"构建安装包"功能生成后下载：

```powershell
pip install nightmend_agent-<version>-py3-none-any.whl
```

### 方式 B：直接使用源码目录安装

如果管理员直接提供了 `agent` 文件夹，进入该目录后安装依赖并以开发模式安装：

```powershell
cd agent

# 安装核心依赖
pip install -r requirements.txt

# Windows 服务支持（注册系统服务必须安装）
pip install pywin32

# 以可编辑模式安装（使 nightmend-agent 命令可用）
pip install -e .
```

> **注意：** `netifaces` 是一个需要 C 编译器的包，在 Windows 上 `pip install` 可能失败。
> 推荐使用 conda 预先安装编译好的版本：
>
> ```powershell
> conda install -c conda-forge netifaces -y
> ```
>
> 安装完成后再执行上方的 `pip install` 步骤。

安装完成后验证：

```powershell
nightmend-agent --version
```

---

## 三、首次配置

首次运行时需要输入服务端地址和 Token，配置会保存到 `~/.nightmend/config.yaml`：

```powershell
nightmend-agent configure
```

按提示输入：
- 服务端地址，例如 `http://10.0.49.9:8001`
- Agent Token（从管理后台 → 设置 → Agent Token 获取）
- 主机显示名称（可选，留空则使用主机名）

---

## 四、注册为 Windows 系统服务

以管理员身份打开命令行（右键 → 以管理员身份运行），执行：

```powershell
# 安装服务（开机自启）
nightmend-agent service install

# 启动服务
nightmend-agent service start

# 查看状态
nightmend-agent service status
```

安装成功后服务会在后台静默运行，开机自动启动，无需手动干预。

### 其他服务管理命令

```powershell
nightmend-agent service stop      # 停止服务
nightmend-agent service restart   # 重启服务
nightmend-agent service remove    # 卸载服务
```

---

## 五、验证运行

在 NightMend 管理后台 → 主机列表，确认主机状态显示为"在线"，指标数据正常上报即为安装成功。

也可以通过 Windows 事件查看器查看服务日志：

```powershell
eventvwr
# 应用程序和服务日志 → 应用程序 → 来源 NightMendAgent
```

或命令行查看最近日志：

```powershell
Get-EventLog -LogName Application -Source "NightMendAgent" -Newest 20 | Format-List
```

---

## 六、自动更新

服务运行期间会通过 WebSocket 监听服务端推送的更新通知。管理员在后台触发更新后，客户端会自动：

1. 下载新版 wheel 包
2. 执行 `pip install --upgrade`
3. 重启服务

整个过程无需人工介入。

---

## 常见问题

**服务启动后立刻停止**

通常是配置文件未找到。确保在安装服务前已执行 `nightmend-agent configure` 完成配置，然后重新执行 `service install`。

**启动失败 1053：服务没有及时响应**

检查 Python 环境是否正确，确认 `nightmend-agent` 命令可以正常执行：

```powershell
nightmend-agent run
```

前台运行无报错后，再注册为服务。

**`nightmend-agent` 不是内部或外部命令**

确认虚拟环境已激活，或将 Python Scripts 目录加入系统 PATH：

```powershell
conda activate nightmend
```
