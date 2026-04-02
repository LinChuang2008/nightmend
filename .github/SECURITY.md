# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.9.x   | ✅ Yes             |
| < 0.9   | ❌ No              |

## Reporting a Vulnerability

If you discover a security vulnerability in NightMend, please report it responsibly:

1. **DO NOT** open a public issue
2. Email us at **security@lchuang.net** with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. We will respond within **48 hours**
4. We will work with you to understand and fix the issue before public disclosure

## Security Best Practices

When deploying NightMend:

- **Change default credentials** (`admin` / `nightmend`) immediately
- Use HTTPS in production (reverse proxy with TLS)
- Keep your `.env` file secure and never commit it
- Restrict database ports (5432/6379) to internal networks
- Enable audit logging for compliance tracking
- Use Agent tokens with minimal required permissions

Thank you for helping keep NightMend secure! 🛡️
