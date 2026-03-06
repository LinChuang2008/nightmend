/**
 * 应用根组件
 * 配置 Ant Design 主题与国际化，定义全局路由结构
 * 所有需要认证的页面由 AuthGuard 守卫保护，嵌套在 AppLayout 布局内
 */
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { ConfigProvider, App as AntApp, theme as antTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import { useTranslation } from 'react-i18next';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import AppLayout from './components/AppLayout';
import AuthGuard from './components/AuthGuard';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import HostList from './pages/HostList';
import HostDetail from './pages/HostDetail';
import ServiceList from './pages/ServiceList';
import ServiceDetail from './pages/ServiceDetail';
import AlertList from './pages/AlertList';
import Settings from './pages/Settings';
import NotificationChannels from './pages/NotificationChannels';
import NotificationLogs from './pages/NotificationLogs';
import NotificationTemplates from './pages/NotificationTemplates';
import Logs from './pages/Logs';
import Databases from './pages/Databases';
import DatabaseDetail from './pages/DatabaseDetail';
import AIAnalysis from './pages/AIAnalysis';
import Users from './pages/Users';
import AuditLogs from './pages/AuditLogs';
import Reports from './pages/Reports';
import Topology from './pages/Topology';
import ServerListPage from './pages/topology/ServerListPage';
import ServerDetailPage from './pages/topology/ServerDetailPage';
import ServiceGroupsPage from './pages/topology/ServiceGroupsPage';
import SLA from './pages/SLA';
import RemediationList from './pages/Remediation';
import RemediationDetail from './pages/RemediationDetail';
import AlertEscalation from './pages/AlertEscalation';
import OnCall from './pages/OnCall';
import ErrorBoundary from './components/ErrorBoundary';

/** 路由权限守卫：根据角色限制可访问的页面 */
const viewerAllowedPrefixes = ['/', '/hosts', '/servers', '/services', '/topology', '/logs', '/databases', '/alerts', '/ai-analysis', '/remediation', '/multi-server', '/service-groups', '/on-call', '/sla'];
function RoleGuard({ children }: { children: React.ReactElement }) {
  const location = useLocation();
  const role = localStorage.getItem('user_role') || 'viewer';
  const path = location.pathname;
  if (role === 'viewer') {
    const allowed = viewerAllowedPrefixes.some((p) => p === '/' ? path === '/' : path.startsWith(p));
    if (!allowed) return <Navigate to="/" replace />;
  }
  if (role === 'member') {
    if (path.startsWith('/users') || path.startsWith('/settings')) return <Navigate to="/" replace />;
  }
  return children;
}

const antdLocaleMap: Record<string, typeof zhCN> = { zh: zhCN, en: enUS };

function AppInner() {
  const { isDark } = useTheme();
  const { i18n } = useTranslation();
  const antdLocale = antdLocaleMap[i18n.language] || zhCN;
  return (
    <ConfigProvider
      locale={antdLocale}
      theme={{
        algorithm: isDark ? antTheme.darkAlgorithm : antTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#1677ff',
          borderRadius: 6,
        },
      }}
    >
      <AntApp>
        <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            {/* 登录页（无需认证） */}
            <Route path="/login" element={<Login />} />
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
              <Route path="/" element={<Dashboard />} />
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
              <Route path="/sla" element={<SLA />} />
              <Route path="/ai-analysis" element={<AIAnalysis />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/notification-channels" element={<NotificationChannels />} />
              <Route path="/notification-templates" element={<NotificationTemplates />} />
              <Route path="/notification-logs" element={<NotificationLogs />} />
              <Route path="/users" element={<Users />} />
              <Route path="/audit-logs" element={<AuditLogs />} />
              <Route path="/alert-escalation" element={<AlertEscalation />} />
              <Route path="/on-call" element={<OnCall />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
            {/* 未匹配路由重定向到首页 */}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
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
