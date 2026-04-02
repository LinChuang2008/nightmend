# NightMend 外部认证集成指南

NightMend 支持多种外部认证方式，包括 OAuth 2.0 和 LDAP/Active Directory 集成。

## 支持的认证提供商

### OAuth 2.0 提供商
- **Google** - Google Workspace / Gmail 账户
- **GitHub** - GitHub 个人或企业账户
- **GitLab** - GitLab.com 或私有 GitLab 实例
- **Microsoft** - Azure AD / Microsoft 365 账户

### 目录服务
- **LDAP** - 标准 LDAP 服务器
- **Active Directory** - Microsoft Active Directory

## OAuth 2.0 配置

### 1. Google OAuth

#### 创建 Google OAuth 应用
1. 访问 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建新项目或选择现有项目
3. 启用 Google+ API
4. 创建 OAuth 2.0 客户端 ID
5. 设置授权重定向 URI：`http://your-domain/api/v1/auth/oauth/google/callback`

#### 环境变量配置
```bash
# .env
GOOGLE_CLIENT_ID="your-google-client-id"
GOOGLE_CLIENT_SECRET="your-google-client-secret"
```

### 2. GitHub OAuth

#### 创建 GitHub OAuth App
1. 访问 GitHub Settings > Developer settings > OAuth Apps
2. 点击 "New OAuth App"
3. 设置应用信息：
   - Authorization callback URL: `http://your-domain/api/v1/auth/oauth/github/callback`
4. 获取 Client ID 和 Client Secret

#### 环境变量配置
```bash
# .env
GITHUB_CLIENT_ID="your-github-client-id"
GITHUB_CLIENT_SECRET="your-github-client-secret"
```

### 3. GitLab OAuth

#### 创建 GitLab 应用
1. 访问 GitLab User Settings > Applications
2. 创建新应用：
   - Redirect URI: `http://your-domain/api/v1/auth/oauth/gitlab/callback`
   - Scopes: `read_user`
3. 获取 Application ID 和 Secret

#### 环境变量配置
```bash
# .env
GITLAB_CLIENT_ID="your-gitlab-application-id"
GITLAB_CLIENT_SECRET="your-gitlab-secret"
```

### 4. Microsoft OAuth (Azure AD)

#### 创建 Azure AD 应用
1. 访问 [Azure Portal](https://portal.azure.com/)
2. Azure Active Directory > App registrations > New registration
3. 设置重定向 URI: `http://your-domain/api/v1/auth/oauth/microsoft/callback`
4. API permissions > Microsoft Graph > User.Read
5. 获取 Application (client) ID 和 Client Secret

#### 环境变量配置
```bash
# .env
MICROSOFT_CLIENT_ID="your-azure-client-id"
MICROSOFT_CLIENT_SECRET="your-azure-client-secret"
```

## LDAP/Active Directory 配置

### 标准 LDAP 配置
```bash
# .env
LDAP_SERVER="ldap.company.com"
LDAP_PORT=389
LDAP_USE_TLS=false
LDAP_BASE_DN="dc=company,dc=com"
LDAP_USER_SEARCH="uid={}"
# 可选：管理员绑定
LDAP_BIND_DN="cn=admin,dc=company,dc=com"
LDAP_BIND_PASSWORD="admin-password"
```

### Active Directory 配置
```bash
# .env
LDAP_SERVER="ad.company.com"
LDAP_PORT=389
LDAP_USE_TLS=true
LDAP_BASE_DN="dc=company,dc=com"
LDAP_USER_SEARCH="sAMAccountName={}"
# AD 通常需要管理员绑定
LDAP_BIND_DN="cn=service-account,ou=Service Accounts,dc=company,dc=com"
LDAP_BIND_PASSWORD="service-password"
```

### LDAPS (LDAP over SSL) 配置
```bash
# .env
LDAP_SERVER="ldaps.company.com"
LDAP_PORT=636
LDAP_USE_TLS=true
LDAP_BASE_DN="dc=company,dc=com"
LDAP_USER_SEARCH="cn={}"
```

## 依赖安装

### OAuth 依赖（已包含在 requirements.txt）
```bash
pip install httpx  # HTTP 客户端
```

### LDAP 依赖（可选）
```bash
# 安装 LDAP 支持
pip install python-ldap ldap3

# Ubuntu/Debian 系统可能需要
sudo apt-get install libldap2-dev libsasl2-dev

# CentOS/RHEL 系统可能需要  
sudo yum install openldap-devel
```

## 前端集成

### 获取可用认证提供商
```javascript
// 获取可用的认证提供商
const response = await fetch('/api/v1/auth/providers');
const { providers } = await response.json();

// 显示可用的登录选项
Object.entries(providers).forEach(([key, provider]) => {
  if (provider.enabled) {
    console.log(`${provider.name} 认证可用`);
  }
});
```

### OAuth 登录流程
```javascript
// 1. 重定向到 OAuth 提供商
const initiateOAuth = async (provider) => {
  const response = await fetch(`/api/v1/auth/oauth/${provider}`);
  const { redirect_url } = await response.json();
  window.location.href = redirect_url;
};

// 2. 处理回调（自动处理，返回 JWT token）
// 用户授权后会自动返回到应用，携带 JWT token
```

### LDAP 登录表单
```javascript
// LDAP 登录
const ldapLogin = async (email, password) => {
  const response = await fetch('/api/v1/auth/ldap/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  
  if (response.ok) {
    const { access_token, refresh_token } = await response.json();
    // 保存 token 并重定向
    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
  }
};
```

## 用户权限管理

### 自动角色分配
- **第一个用户**：自动设置为管理员（admin）
- **后续用户**：默认设置为普通成员（member）

### 手动角色调整
管理员可以在用户管理页面调整用户角色：
- **admin** - 完全管理权限
- **member** - 标准用户权限  
- **viewer** - 只读权限

## 安全考虑

### OAuth 安全
1. **HTTPS 必需**：生产环境必须使用 HTTPS
2. **回调 URL 验证**：确保回调 URL 配置正确
3. **State 参数**：防止 CSRF 攻击
4. **Token 存储**：JWT token 应安全存储

### LDAP 安全
1. **TLS 加密**：建议启用 LDAP over TLS
2. **服务账户**：使用专用服务账户进行 LDAP 绑定
3. **最小权限**：服务账户只需读取用户属性的权限
4. **网络安全**：限制 LDAP 服务器网络访问

## 故障排除

### 常见问题

#### OAuth 登录失败
1. **检查客户端配置**
   ```bash
   curl http://localhost:8000/api/v1/auth/providers
   ```

2. **验证回调 URL**
   - 确保回调 URL 与 OAuth 应用配置一致
   - 检查 HTTPS/HTTP 协议匹配

3. **检查日志**
   ```bash
   docker logs nightmend-backend 2>&1 | grep oauth
   ```

#### LDAP 认证失败
1. **测试 LDAP 连接**
   ```bash
   ldapsearch -H ldap://ldap.company.com -D "uid=testuser,dc=company,dc=com" -W -b "dc=company,dc=com"
   ```

2. **检查用户搜索模式**
   - AD 通常使用：`sAMAccountName={}`
   - OpenLDAP 通常使用：`uid={}`

3. **验证 Base DN**
   ```bash
   ldapsearch -H ldap://ldap.company.com -x -b "dc=company,dc=com" -s base
   ```

### 调试模式
```bash
# 启用详细日志
PYTHON_LOG_LEVEL=DEBUG docker-compose up nightmend-backend
```

## 完整配置示例

```bash
# .env - 完整外部认证配置
# JWT 基础配置
JWT_SECRET_KEY="your-super-secret-jwt-key"

# Google OAuth
GOOGLE_CLIENT_ID="123456789-abcdef.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET="google-client-secret"

# GitHub OAuth  
GITHUB_CLIENT_ID="github-client-id"
GITHUB_CLIENT_SECRET="github-client-secret"

# GitLab OAuth
GITLAB_CLIENT_ID="gitlab-application-id" 
GITLAB_CLIENT_SECRET="gitlab-secret"

# Microsoft OAuth
MICROSOFT_CLIENT_ID="azure-client-id"
MICROSOFT_CLIENT_SECRET="azure-client-secret"

# LDAP Configuration
LDAP_SERVER="ad.company.com"
LDAP_PORT=389
LDAP_USE_TLS=true
LDAP_BASE_DN="dc=company,dc=com"
LDAP_USER_SEARCH="sAMAccountName={}"
LDAP_BIND_DN="cn=nightmend-service,ou=Service Accounts,dc=company,dc=com"
LDAP_BIND_PASSWORD="service-account-password"

# 其他配置...
FRONTEND_URL="https://nightmend.company.com"
```

通过以上配置，NightMend 可以无缝集成到企业现有的身份认证体系中，提供统一的单点登录体验。