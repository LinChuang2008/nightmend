/**
 * 应用根组件
 * 配置 Ant Design 主题与国际化，定义全局路由结构
 * 所有需要认证的页面由 AuthGuard 守卫保护，嵌套在 AppLayout 布局内
 */
import { lazy, Suspense, useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider, App as AntApp, theme as antTheme, Spin } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { useTranslation } from 'react-i18next';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import AppLayout from './components/AppLayout';
import AuthGuard from './components/AuthGuard';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './pages/Login';
import Landing from './pages/Landing';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const HostList = lazy(() => import('./pages/HostList'));
const HostDetail = lazy(() => import('./pages/HostDetail'));
const ServiceList = lazy(() => import('./pages/ServiceList'));
const ServiceDetail = lazy(() => import('./pages/ServiceDetail'));
const AlertList = lazy(() => import('./pages/AlertList'));
const Settings = lazy(() => import('./pages/Settings'));
const NotificationChannels = lazy(() => import('./pages/NotificationChannels'));
const NotificationLogs = lazy(() => import('./pages/NotificationLogs'));
const NotificationTemplates = lazy(() => import('./pages/NotificationTemplates'));
const Logs = lazy(() => import('./pages/Logs'));
const Databases = lazy(() => import('./pages/Databases'));
const DatabaseDetail = lazy(() => import('./pages/DatabaseDetail'));
const OpsAssistant = lazy(() => import('./pages/OpsAssistant'));
const AIOperationLogs = lazy(() => import('./pages/AIOperationLogs'));
const Users = lazy(() => import('./pages/Users'));
const AuditLogs = lazy(() => import('./pages/AuditLogs'));
const Reports = lazy(() => import('./pages/Reports'));
const Topology = lazy(() => import('./pages/Topology'));
const ServerListPage = lazy(() => import('./pages/topology/ServerListPage'));
const ServerDetailPage = lazy(() => import('./pages/topology/ServerDetailPage'));
const ServiceGroupsPage = lazy(() => import('./pages/topology/ServiceGroupsPage'));
const SLA = lazy(() => import('./pages/SLA'));
const RemediationList = lazy(() => import('./pages/Remediation'));
const RemediationDetail = lazy(() => import('./pages/RemediationDetail'));
const AlertEscalation = lazy(() => import('./pages/AlertEscalation'));
const OnCall = lazy(() => import('./pages/OnCall'));
const Demo = lazy(() => import('./pages/Demo'));
const AIConfigs = lazy(() => import('./pages/AIConfigs'));
const RunbookManagement = lazy(() => import('./pages/RunbookManagement'));

/** 路由权限守卫：根据角色限制可访问的页面 */
const viewerAllowedPrefixes = ['/', '/dashboard', '/hosts', '/servers', '/services', '/topology', '/logs', '/databases', '/alerts', '/ops', '/remediations', '/runbooks', '/multi-server', '/service-groups', '/on-call', '/sla', '/ai-operation-logs', '/landing', '/demo'];
function RoleGuard({ children }: { children: React.ReactElement }) {
  const location = useLocation();
  const [role, setRole] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/v1/auth/me', { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((user) => {
        if (cancelled) return;
        const r = user.role || 'viewer';
        setRole(r);
        // 自愈：把 role 回写 localStorage，让 AppLayout 的菜单过滤正确工作
        // （即便 Login 时没写入 / 老会话 / OAuth 回跳 都能兜住）
        if (localStorage.getItem('user_role') !== r) {
          localStorage.setItem('user_role', r);
        }
        if (user.name && localStorage.getItem('user_name') !== user.name) {
          localStorage.setItem('user_name', user.name);
        }
      })
      .catch(() => { if (!cancelled) setRole('viewer'); });
    return () => { cancelled = true; };
  }, []);

  if (role === null) return <Spin size="large" />;

  const path = location.pathname;
  if (role === 'viewer') {
    const allowed = viewerAllowedPrefixes.some((p) => p === '/' ? path === '/' : path.startsWith(p));
    if (!allowed) return <Navigate to="/" replace />;
  }
  if (role === 'member') {
    if (path.startsWith('/users') || path.startsWith('/settings') || path.startsWith('/ai-configs')) return <Navigate to="/" replace />;
  }
  return children;
}

/** 首页入口：已登录用户进 Dashboard，未登录用户跳转 Landing */
function HomeRedirect() {
  const isLoggedIn = !!localStorage.getItem('user_name');
  return <Navigate to={isLoggedIn ? '/dashboard' : '/landing'} replace />;
}

const antdLocaleMap: Record<string, typeof zhCN> = { zh: zhCN, en: enUS };

function AppInner() {
  // DESIGN.md 规定 dark 唯一，isDark 不再消费
  useTheme();
  const { i18n } = useTranslation();
  const antdLocale = antdLocaleMap[i18n.language] || zhCN;
  return (
    <ConfigProvider
      locale={antdLocale}
      theme={{
        // 强制 dark algorithm —— DESIGN.md 规定 dark 为唯一主题
        algorithm: antTheme.darkAlgorithm,
        token: {
          // 唯一品牌色：emerald；borderRadius 保持紧凑；其他 token 全交给 darkAlgorithm 计算
          colorPrimary: '#10B981',
          colorSuccess: '#10B981',
          borderRadius: 6,
        },
      }}
    >
      <AntApp>
        <ErrorBoundary>
        <BrowserRouter>
          <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>}>
          <Routes>
            {/* Landing Page（无需认证） */}
            <Route path="/landing" element={<Landing />} />
            {/* Demo 页面（无需认证） */}
            <Route path="/demo" element={<Demo />} />
            {/* 登录页（无需认证） */}
            <Route path="/login" element={<Login />} />
            {/* 首页入口：未登录→Landing，已登录→Dashboard */}
            <Route path="/" element={<HomeRedirect />} />
            {/* 需要认证的路由，统一使用 AppLayout 布局 */}
            <Route
              element={
                <AuthGuard>
                  <RoleGuard>
                    <AppLayout />
                  </RoleGuard>
                </AuthGuard>
              }
            >
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/hosts" element={<HostList />} />
              <Route path="/hosts/:id" element={<HostDetail />} />
              <Route path="/services" element={<ServiceList />} />
              <Route path="/services/:id" element={<ServiceDetail />} />
              <Route path="/topology" element={<Topology />} />
              <Route path="/topology/servers" element={<ServerListPage />} />
              <Route path="/topology/servers/:id" element={<ServerDetailPage />} />
              <Route path="/topology/service-groups" element={<ServiceGroupsPage />} />
              <Route path="/logs" element={<Logs />} />
              <Route path="/databases" element={<Databases />} />
              <Route path="/databases/:id" element={<DatabaseDetail />} />
              <Route path="/alerts" element={<AlertList />} />
              <Route path="/remediations" element={<RemediationList />} />
              <Route path="/remediations/:id" element={<RemediationDetail />} />
              <Route path="/runbooks" element={<RunbookManagement />} />
              <Route path="/sla" element={<SLA />} />
              <Route path="/ai-analysis" element={<Navigate to="/ops" replace />} />
              <Route path="/ops" element={<OpsAssistant />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/notification-channels" element={<NotificationChannels />} />
              <Route path="/notification-templates" element={<NotificationTemplates />} />
              <Route path="/notification-logs" element={<NotificationLogs />} />
              <Route path="/users" element={<Users />} />
              <Route path="/audit-logs" element={<AuditLogs />} />
              <Route path="/ai-operation-logs" element={<AIOperationLogs />} />
              <Route path="/alert-escalation" element={<AlertEscalation />} />
              <Route path="/on-call" element={<OnCall />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="/ai-configs" element={<AIConfigs />} />
            </Route>
            {/* 未匹配路由重定向到首页 */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </Suspense>
        </BrowserRouter>
        </ErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AppInner />
    </ThemeProvider>
  );
}
