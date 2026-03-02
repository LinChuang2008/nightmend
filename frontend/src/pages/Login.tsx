/**
 * 登录/注册页面
 *
 * 提供邮箱密码登录和注册功能，通过 Tabs 切换两种模式。
 * 登录或注册成功后将 token 和用户信息存入 localStorage，并跳转到首页。
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Tabs, Row, Col, Space } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, RocketOutlined, RobotOutlined, ThunderboltOutlined, DashboardOutlined, SafetyCertificateOutlined, GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { authService } from '../services/auth';

const { Title } = Typography;

/**
 * 登录注册页面组件
 *
 * 包含登录和注册两个 Tab，共用加载状态。登录/注册成功后自动获取用户信息并跳转。
 */
export default function Login() {
  // 添加动画样式
  const animationStyles = `
    @keyframes float {
      0%, 100% { transform: translateY(0px) rotate(0deg); }
      50% { transform: translateY(-20px) rotate(5deg); }
    }
    @keyframes slideDown {
      from { transform: translateY(-30px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
    @keyframes slideUp {
      from { transform: translateY(30px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
    @keyframes fadeInLeft {
      from { transform: translateX(-20px); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }
    .login-feature-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important;
    }
    .ant-input-affix-wrapper:focus,
    .ant-input-affix-wrapper-focused {
      border-color: #1677ff;
      box-shadow: 0 0 0 2px rgba(22,119,255,0.1);
    }
    @media (max-width: 768px) {
      .login-mobile-title { display: block !important; }
    }
  `;

  // 将样式注入到 head
  if (typeof document !== 'undefined') {
    const styleElement = document.getElementById('login-animations');
    if (!styleElement) {
      const style = document.createElement('style');
      style.id = 'login-animations';
      style.textContent = animationStyles;
      document.head.appendChild(style);
    }
  }
  /** 按钮加载状态（登录/注册共用） */
  const [loading, setLoading] = useState(false);
  /** 当前激活的 Tab（login | register） */
  const [activeTab, setActiveTab] = useState('login');
  /** 是否移动端 */
  const [isMobile, setIsMobile] = useState(false);
  const navigate = useNavigate();
  const [loginForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [authProviders, setAuthProviders] = useState<any>(null);
  const [ldapEnabled, setLdapEnabled] = useState(false);
  const { t, i18n } = useTranslation();

  /** 切换语言 */
  const toggleLanguage = () => {
    const newLang = i18n.language === 'zh' ? 'en' : 'zh';
    i18n.changeLanguage(newLang);
    localStorage.setItem('language', newLang);
  };

  // 监听窗口大小变化
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // 获取可用认证提供商
  useEffect(() => {
    const fetchAuthProviders = async () => {
      try {
        const response = await fetch('/api/v1/auth/providers');
        const data = await response.json();
        setAuthProviders(data.providers);
        setLdapEnabled(data.providers.ldap?.enabled || false);
      } catch (error) {
        console.error('Failed to fetch auth providers:', error);
      }
    };
    fetchAuthProviders();
  }, []);

  /** 处理登录：调用登录接口，存储 token，获取用户信息后跳转首页 */
  const handleLogin = async (values: { email: string; password: string }) => {
    setLoading(true);
    try {
      const { data } = await authService.login(values);
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      // 获取用户信息并存储用户名
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.loginSuccess'));
      navigate('/');
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      messageApi.error(err.response?.data?.detail || t('login.loginFailed'));
    } finally {
      setLoading(false);
    }
  };

  /** 处理注册：调用注册接口，流程与登录类似 */
  const handleRegister = async (values: { email: string; name: string; password: string }) => {
    setLoading(true);
    try {
      const { data } = await authService.register(values);
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.registerSuccess'));
      navigate('/');
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
        throw new Error(error.detail || 'LDAP登录失败');
      }
      
      const { access_token, refresh_token } = await response.json();
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      
      // 获取用户信息
      const { data: user } = await authService.me();
      localStorage.setItem('user_name', user.name);
      localStorage.setItem('user_role', user.role);
      messageApi.success(t('login.ldapLoginSuccess'));
      navigate('/');
    } catch (e: any) {
      messageApi.error(e.message || t('login.ldapLoginFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column' as const,
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #1677ff 0%, #722ed1 50%, #eb2f96 100%)',
      backgroundAttachment: 'fixed',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 背景装饰圆圈 */}
      <div style={{
        position: 'absolute',
        top: '-50px',
        left: '-50px',
        width: '200px',
        height: '200px',
        background: 'rgba(255,255,255,0.1)',
        borderRadius: '50%',
        animation: 'float 6s ease-in-out infinite',
      }} />
      <div style={{
        position: 'absolute',
        top: '20%',
        right: '-100px',
        width: '300px',
        height: '300px',
        background: 'rgba(255,255,255,0.05)',
        borderRadius: '50%',
        animation: 'float 8s ease-in-out infinite reverse',
      }} />
      <div style={{
        position: 'absolute',
        bottom: '-100px',
        left: '30%',
        width: '250px',
        height: '250px',
        background: 'rgba(255,255,255,0.08)',
        borderRadius: '50%',
        animation: 'float 7s ease-in-out infinite',
      }} />
      {contextHolder}
      {/* Logo */}
      <div style={{ 
        textAlign: 'center', 
        marginBottom: 32,
        animation: 'slideDown 0.6s ease-out',
        zIndex: 1,
        position: 'relative',
      }}>
        <div style={{
          width: 80,
          height: 80,
          margin: '0 auto 16px',
          background: 'transparent',
          borderRadius: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: 'none',
          backdropFilter: 'blur(10px)',
        }}>
          {/* VigilOps Shield+Eye Logo */}
          <svg width="48" height="48" viewBox="0 0 64 64" fill="none">
            <path d="M32 4L8 16v16c0 14.4 10.24 27.84 24 32 13.76-4.16 24-17.6 24-32V16L32 4z" fill="#1677ff"/>
            <path d="M32 8L12 18v14c0 12.6 8.96 24.36 20 28 11.04-3.64 20-15.4 20-28V18L32 8z" fill="#e6f4ff"/>
            <ellipse cx="32" cy="34" rx="12" ry="8" fill="#1677ff"/>
            <circle cx="32" cy="34" r="4" fill="#fff"/>
            <circle cx="32" cy="34" r="2" fill="#0958d9"/>
          </svg>
        </div>
        <Title level={2} style={{ 
          color: 'white', 
          margin: 0, 
          textShadow: '0 2px 8px rgba(0,0,0,0.3)',
          fontWeight: 600,
          fontSize: '32px'
        }}>
          VigilOps
        </Title>
        <Typography.Text style={{ 
          color: 'rgba(255,255,255,0.9)', 
          fontSize: '16px',
          display: 'block',
          marginTop: 8,
          textShadow: '0 1px 4px rgba(0,0,0,0.3)'
        }}>
          {t('login.subtitle')}
        </Typography.Text>
      </div>
      {/* Language toggle */}
      <div style={{ position: 'absolute', top: 20, right: 20, zIndex: 10 }}>
        <Button
          type="text"
          icon={<GlobalOutlined />}
          onClick={toggleLanguage}
          style={{ color: 'rgba(255,255,255,0.9)', fontSize: 14 }}
        >
          {i18n.language === 'zh' ? 'EN' : '中文'}
        </Button>
      </div>
      <Card style={{ 
        width: 960, 
        maxWidth: '95vw', 
        boxShadow: '0 24px 48px rgba(0,0,0,0.2)', 
        borderRadius: '16px',
        border: '1px solid rgba(255,255,255,0.1)',
        backdropFilter: 'blur(20px)',
        background: 'rgba(255,255,255,0.98)',
        animation: 'slideUp 0.8s ease-out',
        zIndex: 1,
        position: 'relative',
        overflow: 'auto',
        maxHeight: '85vh'
      }}>
        <Row gutter={32}>
          {/* 左侧产品特性 */}
          <Col xs={0} md={11} style={{ 
            borderRight: '1px solid #f0f0f0', 
            display: 'flex', 
            alignItems: 'center',
            background: '#ffffff'
          }}>
            <div style={{ padding: '32px 24px' }}>
              <div style={{ textAlign: 'center', marginBottom: 32 }}>
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '12px',
                  padding: '8px 16px',
                  background: 'linear-gradient(135deg, #1677ff 0%, #722ed1 100%)',
                  borderRadius: '24px',
                  color: 'white',
                  fontSize: '16px',
                  fontWeight: 600,
                  boxShadow: '0 4px 16px rgba(22,119,255,0.3)'
                }}>
                  <svg width="20" height="20" viewBox="0 0 64 64" fill="none">
                    <path d="M32 4L8 16v16c0 14.4 10.24 27.84 24 32 13.76-4.16 24-17.6 24-32V16L32 4z" fill="currentColor"/>
                  </svg>
                  {t('login.features.tagline')}
                </div>
              </div>
              <Space direction="vertical" size={20} style={{ width: '100%' }}>
                {[
                  { 
                    icon: <RobotOutlined style={{ fontSize: 24 }} />, 
                    title: t('login.features.aiAnalysis'), 
                    desc: t('login.features.aiAnalysisDesc'),
                    gradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                  },
                  { 
                    icon: <ThunderboltOutlined style={{ fontSize: 24 }} />, 
                    title: t('login.features.autoRemediation'), 
                    desc: t('login.features.autoRemediationDesc'),
                    gradient: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)'
                  },
                  { 
                    icon: <DashboardOutlined style={{ fontSize: 24 }} />, 
                    title: t('login.features.realTimeMonitoring'), 
                    desc: t('login.features.realTimeMonitoringDesc'),
                    gradient: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)'
                  },
                  { 
                    icon: <SafetyCertificateOutlined style={{ fontSize: 24 }} />, 
                    title: t('login.features.slaManagement'), 
                    desc: t('login.features.slaManagementDesc'),
                    gradient: 'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)'
                  },
                ].map((item, i) => (
                  <div key={i} className="login-feature-card" style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '16px',
                    padding: '16px',
                    borderRadius: '12px',
                    background: 'rgba(255,255,255,0.6)',
                    border: '1px solid rgba(0,0,0,0.05)',
                    transition: 'all 0.3s ease',
                    cursor: 'pointer',
                    animation: `fadeInLeft 0.6s ease-out ${i * 0.1}s both`,
                    boxShadow: '0 2px 8px rgba(0,0,0,0.05)'
                  }}>
                    <div style={{ 
                      width: 48, 
                      height: 48, 
                      borderRadius: 12, 
                      background: item.gradient, 
                      display: 'flex', 
                      alignItems: 'center', 
                      justifyContent: 'center',
                      color: 'white',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.15)'
                    }}>
                      {item.icon}
                    </div>
                    <div>
                      <Typography.Text strong style={{ fontSize: 15, color: '#1a1a2e' }}>{item.title}</Typography.Text>
                      <br />
                      <Typography.Text style={{ fontSize: 13, lineHeight: 1.5, color: '#555' }}>{item.desc}</Typography.Text>
                    </div>
                  </div>
                ))}
              </Space>
            </div>
          </Col>
          {/* 右侧登录表单 */}
          <Col xs={24} md={13}>
            <div style={{ padding: '32px 24px' }}>
              {/* Mobile-only title */}
              <div style={{ 
                textAlign: 'center', 
                marginBottom: 24,
                display: isMobile ? 'block' : 'none'
              }}>
                <Title level={3} style={{ margin: 0, color: '#1677ff' }}>VigilOps</Title>
                <Typography.Text type="secondary" style={{ fontSize: 14 }}>{t('login.subtitle')}</Typography.Text>
              </div>
        <Tabs 
          activeKey={activeTab} 
          onChange={setActiveTab} 
          centered 
          size="large"
          style={{ marginBottom: 24 }}
          items={[
          {
            key: 'login',
            label: <span style={{ fontSize: 16, fontWeight: 500 }}>{t('login.loginTab')}</span>,
            children: (
              <Form form={loginForm} onFinish={handleLogin} size="large">
                <Form.Item name="email" rules={[{ required: true, message: t('login.validation.emailRequired') }, { type: 'email', message: t('login.validation.emailInvalid') }]}>
                  <Input prefix={<MailOutlined />} placeholder={t('login.emailPlaceholder')} />
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
                    style={{
                      height: 48,
                      borderRadius: 8,
                      background: 'linear-gradient(135deg, #1677ff 0%, #722ed1 100%)',
                      border: 'none',
                      fontSize: 16,
                      fontWeight: 500,
                      boxShadow: '0 4px 16px rgba(22,119,255,0.3)'
                    }}
                  >
                    {t('login.loginButton')}
                  </Button>
                </Form.Item>
                <div style={{ textAlign: 'center', marginTop: 16 }}>
                  <Button
                    type="default"
                    icon={<RocketOutlined />}
                    size="large"
                    style={{
                      borderRadius: 8,
                      border: '1px solid #d9d9d9',
                      background: 'rgba(22,119,255,0.04)',
                      color: '#1677ff',
                      fontWeight: 500
                    }}
                    onClick={() => {
                      loginForm.setFieldsValue({ email: 'demo@vigilops.io', password: 'demo123' });
                      loginForm.submit();
                    }}
                  >
                    {t('login.demoButton')}
                  </Button>
                </div>

                {/* OAuth 登录选项 */}
                {authProviders && (
                  <div style={{ marginTop: 24 }}>
                    <div style={{ textAlign: 'center', marginBottom: 16, color: '#666' }}>
                      <span>{t('login.oauthTitle')}</span>
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
                              size="large"
                              style={{ 
                                flex: 1,
                                minWidth: 120,
                                borderRadius: 8,
                                border: '1px solid #d9d9d9',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center'
                              }}
                              onClick={() => handleOAuthLogin(key)}
                            >
                              <span style={{ marginRight: 8 }}>{providerIcons[key]}</span>
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
            label: <span style={{ fontSize: 16, fontWeight: 500 }}>{t('login.ldapTab')}</span>,
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
                    style={{
                      height: 48,
                      borderRadius: 8,
                      background: 'linear-gradient(135deg, #52c41a 0%, #73d13d 100%)',
                      border: 'none',
                      fontSize: 16,
                      fontWeight: 500,
                      boxShadow: '0 4px 16px rgba(82,196,26,0.3)'
                    }}
                  >
                    {t('login.ldapLogin')}
                  </Button>
                </Form.Item>
              </Form>
            ) : (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
                <Typography.Text type="secondary">
                  {t('login.ldapNotAvailable')}
                </Typography.Text>
              </div>
            ),
          },
          {
            key: 'register',
            label: <span style={{ fontSize: 16, fontWeight: 500 }}>{t('login.registerTab')}</span>,
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
                    style={{
                      height: 48,
                      borderRadius: 8,
                      background: 'linear-gradient(135deg, #722ed1 0%, #eb2f96 100%)',
                      border: 'none',
                      fontSize: 16,
                      fontWeight: 500,
                      boxShadow: '0 4px 16px rgba(114,46,209,0.3)'
                    }}
                  >
                    {t('login.registerButton')}
                  </Button>
                </Form.Item>
              </Form>
            ),
          },
        ]} />
            </div>
          </Col>
        </Row>
      </Card>
      <div style={{ 
        marginTop: 32, 
        textAlign: 'center', 
        color: 'rgba(255,255,255,0.8)', 
        fontSize: 14, 
        lineHeight: 1.6,
        zIndex: 1,
        position: 'relative',
      }}>
        <div style={{ fontWeight: 500, marginBottom: 4 }}>{t('login.footer.company')}</div>
        <div>
          <a href="mailto:contact@lchuangnet.com" style={{ 
            color: 'rgba(255,255,255,0.8)', 
            textDecoration: 'none',
            marginRight: 16
          }}>
            contact@lchuangnet.com
          </a>
          ·
          <a href="https://lchuangnet.com" style={{ 
            color: 'rgba(255,255,255,0.8)', 
            textDecoration: 'none',
            marginLeft: 16
          }}>
            lchuangnet.com
          </a>
        </div>
      </div>
    </div>
  );
}
