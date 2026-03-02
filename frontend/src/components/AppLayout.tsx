/**
 * 应用主布局组件
 *
 * 提供侧边栏导航、顶部栏（含用户菜单）和内容区域的整体页面框架。
 * 所有需要认证的页面均嵌套在此布局内，通过 React Router 的 <Outlet /> 渲染子路由。
 * 支持移动端响应式设计，在小屏幕上使用抽屉式侧边栏。
 */
import { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, theme, Avatar, Dropdown, Drawer } from 'antd';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../contexts/ThemeContext';
import {
  DashboardOutlined,
  SunOutlined,
  MoonOutlined,
  CloudServerOutlined,
  ApiOutlined,
  AlertOutlined,
  FileTextOutlined,
  SettingOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  LogoutOutlined,
  DatabaseOutlined,
  NotificationOutlined,
  UnorderedListOutlined,
  FormOutlined,
  RobotOutlined,
  TeamOutlined,
  AuditOutlined,
  FileSearchOutlined,
  DeploymentUnitOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  ScheduleOutlined,
  RiseOutlined,
  GlobalOutlined,
  ClusterOutlined,
  AppstoreOutlined,
} from '@ant-design/icons';

const { Header, Sider, Content } = Layout;

/** viewer 可见的菜单 key */
const viewerKeys = new Set(['/', '/hosts', '/services', '/topology', '/topology/servers', '/topology/service-groups', '/logs', '/databases', '/alerts', '/ai-analysis', '/remediations']);
/** member 隐藏的菜单 key */
const memberHiddenKeys = new Set(['/users', '/settings']);

/** 根据角色过滤菜单（支持分组结构） */
function filterMenuByRole(items: ReturnType<typeof buildMenuItems>, role: string) {
  if (role === 'admin') return items;
  return items
    .map((group) => {
      const children = ((group as any).children as any[])
        .filter((item: any) => {
          if (role === 'viewer') return viewerKeys.has(item.key);
          if (role === 'member') return !memberHiddenKeys.has(item.key);
          return true;
        })
        .map((item: any) => {
          if ('children' in item && Array.isArray(item.children) && role === 'viewer') {
            return { ...item, children: item.children.filter((c: any) => viewerKeys.has(c.key)) };
          }
          return item;
        });
      return { ...group, children };
    })
    .filter((group) => ((group as any).children as any[]).length > 0);
}

/** 生成侧边栏菜单项（分 6 个分组），使用 i18n 翻译 */
function buildMenuItems(t: (key: string) => string) {
  return [
    {
      type: 'group' as const,
      label: t('menu.groupMonitoring'),
      children: [
        { key: '/', icon: <DashboardOutlined />, label: t('menu.dashboard') },
        { key: '/hosts', icon: <CloudServerOutlined />, label: t('menu.hosts') },
        { key: '/services', icon: <ApiOutlined />, label: t('menu.services') },
        { key: '/topology', icon: <DeploymentUnitOutlined />, label: t('menu.topologyService') },
        { key: '/topology/servers', icon: <ClusterOutlined />, label: t('menu.topologyServers') },
        { key: '/topology/service-groups', icon: <AppstoreOutlined />, label: t('menu.topologyServiceGroups') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupLogsAlerts'),
      children: [
        { key: '/logs', icon: <FileTextOutlined />, label: t('menu.logs') },
        { key: '/databases', icon: <DatabaseOutlined />, label: t('menu.databases') },
        { key: '/alerts', icon: <AlertOutlined />, label: t('menu.alerts') },
        { key: '/alert-escalation', icon: <RiseOutlined />, label: t('menu.alertEscalation') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupAutomation'),
      children: [
        { key: '/on-call', icon: <ScheduleOutlined />, label: t('menu.onCall') },
        { key: '/remediations', icon: <ThunderboltOutlined />, label: t('menu.remediation') },
        { key: '/sla', icon: <SafetyCertificateOutlined />, label: t('menu.sla') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupAI'),
      children: [
        { key: '/ai-analysis', icon: <RobotOutlined />, label: t('menu.aiAnalysis') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupNotifications'),
      children: [
        { key: '/notification-channels', icon: <NotificationOutlined />, label: t('menu.notificationChannels') },
        { key: '/notification-templates', icon: <FormOutlined />, label: t('menu.notificationTemplates') },
        { key: '/notification-logs', icon: <UnorderedListOutlined />, label: t('menu.notificationLogs') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupSystem'),
      children: [
        { key: '/users', icon: <TeamOutlined />, label: t('menu.users') },
        { key: '/reports', icon: <FileSearchOutlined />, label: t('menu.reports') },
        { key: '/audit-logs', icon: <AuditOutlined />, label: t('menu.auditLogs') },
        { key: '/settings', icon: <SettingOutlined />, label: t('menu.settings') },
      ],
    },
  ];
}

/**
 * 应用主布局组件
 *
 * 包含可折叠侧边栏、顶部导航栏（用户头像与退出登录）、以及子路由内容区域。
 * 在移动端使用抽屉式侧边栏以优化用户体验。
 */
export default function AppLayout() {
  /** 侧边栏折叠状态 */
  const [collapsed, setCollapsed] = useState(false);
  /** 移动端抽屉打开状态 */
  const [drawerVisible, setDrawerVisible] = useState(false);
  /** 是否为移动端 */
  const [isMobile, setIsMobile] = useState(false);
  /** 菜单展开的 SubMenu keys */
  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([]);
  
  const navigate = useNavigate();
  const location = useLocation();
  const { token: { colorBgContainer, borderRadiusLG, colorBgLayout } } = theme.useToken();
  const { isDark, toggleTheme } = useTheme();
  const { t, i18n } = useTranslation();

  /** 动态生成菜单 */
  const allMenuItems = buildMenuItems(t);

  /** 切换语言 */
  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem('language', lang);
  };

  /** 检测屏幕大小变化 */
  useEffect(() => {
    const checkMobile = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) {
        setCollapsed(true); // 移动端默认折叠侧边栏
      }
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  /** 从 localStorage 读取用户名和角色 */
  const userName = localStorage.getItem('user_name') || 'Admin';
  const userRole = localStorage.getItem('user_role') || 'viewer';
  const menuItems = filterMenuByRole(allMenuItems, userRole);

  /** 退出登录：清除本地存储的认证信息并跳转到登录页 */
  const handleLogout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_role');
    navigate('/login');
  };

  /** 处理菜单点击 - 移动端自动关闭抽屉 */
  const handleMenuClick = ({ key }: { key: string }) => {
    if (key.startsWith('/')) {
      navigate(key);
      if (isMobile) {
        setDrawerVisible(false); // 移动端点击菜单后关闭抽屉
      }
    }
  };

  /** 切换侧边栏/抽屉 */
  const toggleSidebar = () => {
    if (isMobile) {
      setDrawerVisible(!drawerVisible);
    } else {
      setCollapsed(!collapsed);
    }
  };

  /** 将分组菜单展平为一级列表，用于选中状态检测 */
  const allFlatItems = allMenuItems.flatMap((g) => (g as any).children as any[]);

  /** 根据当前路径匹配侧边栏选中菜单项（支持分组 + 嵌套子菜单） */
  const findSelectedKey = (): string => {
    const path = location.pathname;
    // 收集所有可匹配的菜单 key（含子菜单）
    const allKeys: string[] = [];
    for (const item of allFlatItems) {
      if ('children' in item && Array.isArray(item.children)) {
        for (const child of item.children) {
          if (child.key && child.key !== '/') allKeys.push(child.key);
        }
      }
      if (item.key && item.key !== '/' && item.key.startsWith('/')) {
        allKeys.push(item.key);
      }
    }
    // 按 key 长度倒序排列，确保最长匹配优先（/topology/servers 优先于 /topology）
    allKeys.sort((a, b) => b.length - a.length);
    const matched = allKeys.find(k => path.startsWith(k));
    return matched || '/';
  };
  const selectedKey = findSelectedKey();
  const openKey = allFlatItems.find(
    (item: any) => 'children' in item && item.children?.some((c: any) => c.key === selectedKey)
  )?.key;

  // 路由变化时自动展开对应的 SubMenu
  useEffect(() => {
    if (openKey && !menuOpenKeys.includes(openKey)) {
      setMenuOpenKeys(prev => [...new Set([...prev, openKey])]);
    }
  }, [openKey, location.pathname]);

  /** 渲染菜单内容 */
  const renderMenuContent = (inDrawer = false) => (
    <>
      {/* 品牌标识区域 */}
      <div style={{
        height: 64,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: inDrawer ? 'inherit' : '#fff',
        fontSize: (inDrawer || !collapsed) ? 20 : 16,
        fontWeight: 'bold',
        letterSpacing: 2,
        borderBottom: inDrawer ? '1px solid #f0f0f0' : undefined,
      }}>
        {(inDrawer || !collapsed) ? 'VigilOps' : 'VO'}
      </div>
      <Menu
        theme={inDrawer ? 'light' : 'dark'}
        mode="inline"
        selectedKeys={[selectedKey]}
        openKeys={menuOpenKeys}
        onOpenChange={(keys) => setMenuOpenKeys(keys as string[])}
        items={menuItems}
        onClick={handleMenuClick}
      />
    </>
  );

  return (
    <Layout style={{ minHeight: '100vh', background: colorBgLayout }}>
      {/* 桌面端侧边栏 */}
      {!isMobile && (
        <Sider trigger={null} collapsible collapsed={collapsed} theme="dark">
          {renderMenuContent()}
        </Sider>
      )}

      {/* 移动端抽屉 */}
      {isMobile && (
        <Drawer
          title={null}
          placement="left"
          closable={false}
          onClose={() => setDrawerVisible(false)}
          open={drawerVisible}
          bodyStyle={{ padding: 0 }}
          width={280}
        >
          {renderMenuContent(true)}
        </Drawer>
      )}
      <Layout>
        <Header style={{
          padding: isMobile ? '0 16px' : '0 24px',
          background: colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          {/* 侧边栏折叠切换按钮 */}
          <Button
            type="text"
            icon={isMobile ? <MenuUnfoldOutlined /> : (collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />)}
            onClick={toggleSidebar}
            size={isMobile ? 'large' : 'middle'}
          />
          {/* 右侧操作区：主题切换 + 用户菜单 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Dropdown menu={{
              items: [
                { key: 'zh', label: '🇨🇳 中文', onClick: () => changeLanguage('zh') },
                { key: 'en', label: '🇺🇸 English', onClick: () => changeLanguage('en') },
              ],
              selectedKeys: [i18n.language],
            }}>
              <Button type="text" icon={<GlobalOutlined />} title={t('header.language')}>
                {i18n.language === 'zh' ? '中文' : 'EN'}
              </Button>
            </Dropdown>
            <Button
              type="text"
              icon={isDark ? <SunOutlined /> : <MoonOutlined />}
              onClick={toggleTheme}
              title={isDark ? t('header.lightMode') : t('header.darkMode')}
            />
            <Dropdown menu={{
              items: [
                { key: 'logout', icon: <LogoutOutlined />, label: t('header.logout'), onClick: handleLogout },
              ],
            }}>
              <div style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                <Avatar icon={<UserOutlined />} size="small" />
                <span>{userName}</span>
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{
          margin: isMobile ? 12 : 24,
          padding: isMobile ? 16 : 24,
          background: colorBgContainer,
          borderRadius: borderRadiusLG,
          minHeight: 280,
        }}>
          {/* 子路由内容渲染区 */}
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
