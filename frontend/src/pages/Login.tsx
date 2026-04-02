/**
 * 登录/注册页面
 *
 * 提供邮箱密码登录和注册功能，通过 Tabs 切换两种模式。
 * 登录或注册成功后将 token 和用户信息存入 localStorage，并跳转到首页。
 */
import { useState, useEffect } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Typography, message, Tabs, Modal } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, RocketOutlined, GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { authService } from '../services/auth';

const { Title } = Typography;

/* ── Design tokens from DESIGN.md ──────────────────────────── */
const T = {
  bg:          '#0a0a0f',
  surface:     '#141419',
  surfaceHover:'#1a1a21',
  border:      '#27272a',
  textPrimary: '#e4e4e7',
  textMuted:   '#71717a',
  textDim:     '#52525b',
  accent:      '#10B981',
  accentDim:   '#065f46',
  error:       '#ef4444',
  fontFamily:  "'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  monoFamily:  "'Geist Mono', 'SF Mono', 'Consolas', monospace",
  radiusSm:    4,
  radiusMd:    6,
  radiusLg:    8,
} as const;

/**
 * 登录注册页面组件
 *
 * 包含登录、LDAP和注册三个 Tab，共用加载状态。登录/注册成功后自动获取用户信息并跳转。
 */
export default function Login() {

  /* ── inject global overrides for antd on this page ───────── */
  const pageStyles = `
    /* Antd input overrides */
    .nightmend-login .ant-input-affix-wrapper,
    .nightmend-login .ant-input {
      background: ${T.surface} !important;
      border-color: ${T.border} !important;
      color: ${T.textPrimary} !important;
      border-radius: ${T.radiusMd}px !important;
      font-family: ${T.fontFamily} !important;
    }
    .nightmend-login .ant-input-affix-wrapper:hover,
    .nightmend-login .ant-input:hover {
      border-color: ${T.textMuted} !important;
    }
    .nightmend-login .ant-input-affix-wrapper:focus,
    .nightmend-login .ant-input-affix-wrapper-focused,
    .nightmend-login .ant-input:focus {
      border-color: ${T.accent} !important;
      box-shadow: 0 0 0 2px rgba(16,185,129,0.15) !important;
    }
    .nightmend-login .ant-input-affix-wrapper .ant-input-prefix {
      color: ${T.textDim} !important;
    }
    .nightmend-login .ant-input::placeholder {
      color: ${T.textDim} !important;
    }
    .nightmend-login .ant-input-password-icon {
      color: ${T.textDim} !important;
    }
    .nightmend-login .ant-input-password-icon:hover {
      color: ${T.textMuted} !important;
    }

    /* Tabs overrides */
    .nightmend-login .ant-tabs-nav::before {
      border-bottom-color: ${T.border} !important;
    }
    .nightmend-login .ant-tabs-tab {
      color: ${T.textMuted} !important;
      font-family: ${T.fontFamily} !important;
    }
    .nightmend-login .ant-tabs-tab:hover {
      color: ${T.textPrimary} !important;
    }
    .nightmend-login .ant-tabs-tab-active .ant-tabs-tab-btn {
      color: ${T.accent} !important;
    }
    .nightmend-login .ant-tabs-ink-bar {
      background: ${T.accent} !important;
    }

    /* Form validation */
    .nightmend-login .ant-form-item-explain-error {
      color: ${T.error} !important;
      font-size: 12px !important;
    }

    /* Modal overrides */
    .nightmend-login-modal .ant-modal-content {
      background: ${T.surface} !important;
      border: 1px solid ${T.border} !important;
      border-radius: ${T.radiusLg}px !important;
    }
    .nightmend-login-modal .ant-modal-header {
      background: transparent !important;
      border-bottom: 1px solid ${T.border} !important;
    }
    .nightmend-login-modal .ant-modal-title {
      color: ${T.textPrimary} !important;
    }
    .nightmend-login-modal .ant-modal-close-x {
      color: ${T.textMuted} !important;
    }
    .nightmend-login-modal .ant-modal-body {
      color: ${T.textMuted} !important;
    }
    .nightmend-login-modal .ant-modal-footer .ant-btn-primary {
      background: ${T.accent} !important;
      border-color: ${T.accent} !important;
    }
  `;

  if (typeof document !== 'undefined') {
    const existing = document.getElementById('nightmend-login-styles');
    if (!existing) {
      const style = document.createElement('style');
      style.id = 'nightmend-login-styles';
      style.textContent = pageStyles;
      document.head.appendChild(style);
    }
  }

  /** 按钮加载状态（登录/注册共用） */
  const [loading, setLoading] = useState(false);
  /** 当前激活的 Tab（login | ldap | register） */
  const [activeTab, setActiveTab] = useState('login');
  /** 忘记密码弹窗 */
  const [forgotModalOpen, setForgotModalOpen] = useState(false);
  const navigate = useNavigate();
  const [loginForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [authProviders, setAuthProviders] = useState<any>(null);
  const [ldapEnabled, setLdapEnabled] = useState(false);
  const { t, i18n } = useTranslation();
  const { isMobile } = useResponsive();

  /** 切换语言 */
  const toggleLanguage = () => {
    const newLang = i18n.language === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(newLang);
    localStorage.setItem('language', newLang);
  };

  // 获取可用认证提供商
  useEffect(() => {
    const fetchAuthProviders = async () => {
      try {
        const response = await fetch('/api/v1/auth/providers');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setAuthProviders(data.providers);
        setLdapEnabled(data.providers.ldap?.enabled || false);
      } catch (error) {
        console.error('Failed to fetch auth providers:', error);
      }
    };
    fetchAuthProviders();
  }, []);

  /** 处理登录：JWT 已迁移至 httpOnly Cookie，后端自动 set-cookie，无需前端手动存储 */
  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      await authService.login(values);
      // Cookie 由后端 set-cookie 自动写入，仅缓存非敏感显示信息
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.loginSuccess'));
      navigate('/dashboard');
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      messageApi.error(err.response?.data?.detail || t('login.loginFailed'));
    } finally {
      setLoading(false);
    }
  };

  /** 处理注册：JWT 已迁移至 httpOnly Cookie，流程与登录类似 */
  const handleRegister = async (values: { email: string; name: string; password: string }) => {
    setLoading(true);
    try {
      await authService.register(values);
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.registerSuccess'));
      navigate('/dashboard');
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      messageApi.error(err.response?.data?.detail || t('login.registerFailed'));
    } finally {
      setLoading(false);
    }
  };

  /** 处理OAuth登录 */
  const handleOAuthLogin = async (provider: string) => {
    try {
      const response = await fetch(`/api/v1/auth/oauth/${provider}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const { redirect_url } = await response.json();
      window.location.href = redirect_url;
    } catch (error) {
      messageApi.error(`${t('login.oauthFailed')}: ${provider}`);
    }
  };

  /** 处理LDAP登录 */
  const handleLdapLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/auth/ldap/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values)
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || t('login.ldapLoginFailed'));
      }

      // LDAP 登录：Cookie 由后端 set-cookie 自动写入
      await response.json();

      // 获取用户信息
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.ldapLoginSuccess'));
      navigate('/dashboard');
    } catch (e: any) {
      messageApi.error(e.message || t('login.ldapLoginFailed'));
    } finally {
      setLoading(false);
    }
  };

  /* ── Shared button styles ──────────────────────────────────── */
  const primaryBtnStyle: React.CSSProperties = {
    height: 44,
    borderRadius: T.radiusMd,
    background: T.accent,
    border: 'none',
    fontSize: 14,
    fontWeight: 600,
    fontFamily: T.fontFamily,
    color: '#fff',
    letterSpacing: '0.02em',
  };

  const secondaryBtnStyle: React.CSSProperties = {
    borderRadius: T.radiusMd,
    border: `1px solid ${T.border}`,
    background: 'transparent',
    color: T.textMuted,
    fontFamily: T.fontFamily,
    fontWeight: 500,
  };

  return (
    <div
      className="nightmend-login"
      style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: T.bg,
        fontFamily: T.fontFamily,
        padding: isMobile ? '24px 16px' : '48px 16px',
      }}
    >
      {contextHolder}

      {/* Language toggle - top right */}
      <div style={{ position: 'fixed', top: 16, right: 16, zIndex: 10 }}>
        <Button
          type="text"
          icon={<GlobalOutlined />}
          onClick={toggleLanguage}
          style={{
            color: T.textMuted,
            fontSize: 13,
            fontFamily: T.fontFamily,
            border: 'none',
          }}
        >
          {i18n.language === 'zh' ? 'EN' : '中文'}
        </Button>
      </div>

      {/* Logo / brand */}
      <div style={{ textAlign: 'center', marginBottom: 32 }}>
        <div style={{
          width: 48,
          height: 48,
          margin: '0 auto 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <svg width="48" height="48" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="40" height="40" rx="8" fill={T.accentDim}/>
            <circle cx="20" cy="21" r="11.5" fill="none" stroke={T.accent} strokeWidth="2.2"/>
            <path d="M13 15.5L20 26.5L27 15.5" fill="none" stroke={T.accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <Title level={3} style={{
          color: T.textPrimary,
          margin: 0,
          fontFamily: T.fontFamily,
          fontWeight: 700,
          fontSize: 24,
          letterSpacing: '-0.02em',
        }}>
          NightMend
        </Title>
        <div style={{
          color: T.textMuted,
          fontSize: 13,
          marginTop: 6,
          fontFamily: T.fontFamily,
        }}>
          {t('login.subtitle')}
        </div>
      </div>

      {/* Main card */}
      <div style={{
        width: '100%',
        maxWidth: 420,
        background: T.surface,
        border: `1px solid ${T.border}`,
        borderRadius: T.radiusLg,
        padding: isMobile ? '24px 20px' : '32px 32px',
        boxSizing: 'border-box',
      }}>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          size="middle"
          style={{ marginBottom: 8 }}
          items={[
            {
              key: 'login',
              label: <span style={{ fontSize: 14, fontWeight: 600, fontFamily: T.fontFamily }}>{t('login.loginTab')}</span>,
              children: (
                <Form form={loginForm} onFinish={handleLogin} size="large">
                  <Form.Item name="email" rules={[{ required: true, message: t('login.validation.emailRequired') }, { type: 'email', message: t('login.validation.emailInvalid') }]}>
                    <Input prefix={<MailOutlined />} placeholder={t('login.emailPlaceholder')} />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: t('login.validation.passwordRequired') }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder={t('login.passwordPlaceholder')} />
                  </Form.Item>
                  <div style={{ textAlign: 'right', marginTop: -16, marginBottom: 12 }}>
                    <Button
                      type="link"
                      size="small"
                      style={{ padding: 0, color: T.textMuted, fontSize: 12, fontFamily: T.fontFamily }}
                      onClick={() => setForgotModalOpen(true)}
                    >
                      {t('login.forgotPassword')}
                    </Button>
                  </div>
                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                      size="large"
                      style={primaryBtnStyle}
                    >
                      {t('login.loginButton')}
                    </Button>
                  </Form.Item>

                  {/* Demo account */}
                  <div style={{ textAlign: 'center', marginTop: 8 }}>
                    <Button
                      type="default"
                      icon={<RocketOutlined />}
                      size="middle"
                      style={secondaryBtnStyle}
                      onClick={() => {
                        loginForm.setFieldsValue({ email: 'demo@nightmend.io', password: 'demo123' });
                        loginForm.submit();
                      }}
                    >
                      {t('login.demoButton')}
                    </Button>
                  </div>

                  {/* OAuth 登录选项 */}
                  {authProviders && (
                    <div style={{ marginTop: 24 }}>
                      <div style={{
                        textAlign: 'center',
                        marginBottom: 16,
                        color: T.textDim,
                        fontSize: 12,
                        fontFamily: T.fontFamily,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 12,
                      }}>
                        <div style={{ flex: 1, height: 1, background: T.border }} />
                        <span>{t('login.oauthTitle')}</span>
                        <div style={{ flex: 1, height: 1, background: T.border }} />
                      </div>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        {Object.entries(authProviders).map(([key, provider]: [string, any]) => {
                          if (key !== 'ldap' && provider.enabled) {
                            const providerIcons: Record<string, string> = {
                              google: '🔍',
                              github: '⚡',
                              gitlab: '🦊',
                              microsoft: '🪟'
                            };

                            return (
                              <Button
                                key={key}
                                size="middle"
                                style={{
                                  flex: 1,
                                  minWidth: 100,
                                  borderRadius: T.radiusMd,
                                  border: `1px solid ${T.border}`,
                                  background: 'transparent',
                                  color: T.textMuted,
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  fontFamily: T.fontFamily,
                                }}
                                onClick={() => handleOAuthLogin(key)}
                              >
                                <span style={{ marginRight: 6 }}>{providerIcons[key]}</span>
                                {provider.name}
                              </Button>
                            );
                          }
                          return null;
                        })}
                      </div>
                    </div>
                  )}
                </Form>
              ),
            },
            {
              key: 'ldap',
              label: <span style={{ fontSize: 14, fontWeight: 600, fontFamily: T.fontFamily }}>{t('login.ldapTab')}</span>,
              children: ldapEnabled ? (
                <Form onFinish={handleLdapLogin} size="large">
                  <Form.Item name="email" rules={[{ required: true, message: t('login.validation.usernameOrEmailRequired') }]}>
                    <Input prefix={<UserOutlined />} placeholder={t('login.usernameOrEmail')} />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, message: t('login.validation.passwordRequired') }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder={t('login.passwordPlaceholder')} />
                  </Form.Item>
                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                      size="large"
                      style={primaryBtnStyle}
                    >
                      {t('login.ldapLogin')}
                    </Button>
                  </Form.Item>
                </Form>
              ) : (
                <div style={{ textAlign: 'center', padding: '40px 0', color: T.textDim }}>
                  <Typography.Text style={{ color: T.textDim }}>
                    {t('login.ldapNotAvailable')}
                  </Typography.Text>
                </div>
              ),
            },
            {
              key: 'register',
              label: <span style={{ fontSize: 14, fontWeight: 600, fontFamily: T.fontFamily }}>{t('login.registerTab')}</span>,
              children: (
                <Form onFinish={handleRegister} size="large">
                  <Form.Item name="email" rules={[{ required: true, message: t('login.validation.emailRequired') }, { type: 'email', message: t('login.validation.emailInvalid') }]}>
                    <Input prefix={<MailOutlined />} placeholder={t('login.emailPlaceholder')} />
                  </Form.Item>
                  <Form.Item name="name" rules={[{ required: true, message: t('login.validation.usernameRequired') }]}>
                    <Input prefix={<UserOutlined />} placeholder={t('login.usernamePlaceholder')} />
                  </Form.Item>
                  <Form.Item name="password" rules={[{ required: true, min: 6, message: t('login.validation.passwordMin') }]}>
                    <Input.Password prefix={<LockOutlined />} placeholder={t('login.passwordPlaceholder')} />
                  </Form.Item>
                  <Form.Item>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={loading}
                      block
                      size="large"
                      style={primaryBtnStyle}
                    >
                      {t('login.registerButton')}
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
          ]}
        />
      </div>

      {/* Forgot password modal */}
      <Modal
        title={t('login.forgotPasswordTitle')}
        open={forgotModalOpen}
        onCancel={() => setForgotModalOpen(false)}
        onOk={() => setForgotModalOpen(false)}
        cancelButtonProps={{ style: { display: 'none' } }}
        rootClassName="nightmend-login-modal"
      >
        <p>{t('login.forgotPasswordContent')}</p>
      </Modal>

      {/* Footer */}
      <div style={{
        marginTop: 32,
        textAlign: 'center',
        color: T.textDim,
        fontSize: 12,
        lineHeight: 1.6,
        fontFamily: T.fontFamily,
      }}>
        <div style={{ marginBottom: 4 }}>{t('login.footer.company')}</div>
        <div>
          <a
            href="mailto:contact@lchuangnet.com"
            style={{ color: T.textDim, textDecoration: 'none', marginRight: 12 }}
          >
            contact@lchuangnet.com
          </a>
          <span style={{ color: T.border }}>·</span>
          <a
            href="https://lchuangnet.com"
            style={{ color: T.textDim, textDecoration: 'none', marginLeft: 12 }}
          >
            lchuangnet.com
          </a>
        </div>
      </div>
    </div>
  );
}
