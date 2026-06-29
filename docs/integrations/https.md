# HTTPS 配置指南

NightMend 通过 nginx 反向代理实现 SSL 终止，内部容器间通信仍使用 HTTP。

## 架构

```
用户 → nginx-ssl (443/SSL) → frontend (80) → backend (8000)
                            ↗ (API/WS proxy)
```

## 快速开始

### 开发环境（自签名证书）

```bash
# 1. 生成自签名证书
bash scripts/generate-self-signed-cert.sh localhost

# 2. 启动（含 HTTPS）
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d

# 3. 访问
#    https://localhost (浏览器会警告，忽略即可)
#    http://localhost  (自动跳转 HTTPS)
```

### 生产环境（Let's Encrypt）

```bash
# 1. 确保域名 DNS 指向服务器，80/443 端口开放

# 2. 初始化证书
bash scripts/init-letsencrypt.sh your-domain.com admin@your-domain.com

# 3. 启动（含自动续期）
DOMAIN=your-domain.com docker compose \
  -f docker-compose.yml \
  -f docker-compose.ssl.yml \
  --profile production up -d
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DOMAIN` | `localhost` | 域名 |
| `HTTPS_PORT` | `443` | HTTPS 端口 |
| `HTTP_PORT` | `80` | HTTP 端口（用于重定向） |
| `SSL_CERT_DIR` | `./nginx/certs` | 证书目录 |
| `CERTBOT_WEBROOT` | `./nginx/certbot` | ACME 验证目录 |

## 仅 HTTP 模式（默认）

不使用 SSL overlay 即可：

```bash
docker compose up -d  # 原有方式，不受影响
```

## 证书续期

Let's Encrypt 证书 90 天过期。启用 `production` profile 后，certbot 容器每 12 小时自动检查续期。

手动续期：
```bash
docker compose -f docker-compose.yml -f docker-compose.ssl.yml run --rm certbot renew
docker compose -f docker-compose.yml -f docker-compose.ssl.yml exec nginx-ssl nginx -s reload
```

## 注意事项

- `nginx/certs/` 已加入 `.gitignore`，证书不会提交到代码库
- 自签名证书仅用于开发，浏览器会显示安全警告
- 生产环境务必使用 Let's Encrypt 或商业证书
- 内部容器通信无需 HTTPS，nginx 做 SSL 终止即可
