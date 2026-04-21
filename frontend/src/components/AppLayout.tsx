/**
 * 应用主布局组件
 *
 * 提供侧边栏导航、顶部栏（含用户菜单）和内容区域的整体页面框架。
 * 所有需要认证的页面均嵌套在此布局内，通过 React Router 的 <Outlet /> 渲染子路由。
 * 支持移动端响应式设计，在小屏幕上使用抽屉式侧边栏。
 */
import { useState, useEffect } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Button, theme, Avatar, Dropdown, Drawer, Popover, Checkbox, Space, Divider, message } from 'antd';
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
  HistoryOutlined,
  DeploymentUnitOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
  BookOutlined,
  ScheduleOutlined,
  RiseOutlined,
  GlobalOutlined,
  ClusterOutlined,
  AppstoreOutlined,
  EyeInvisibleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import QuickStartGuide from './QuickStartGuide';
import GuidedTour, { useTourControl } from './GuidedTour';
import { Logo } from './Logo';
import { menuSettingsApi } from '../services/menuSettings';

const { Header, Sider, Content } = Layout;

/** viewer 可见的菜单 key */
const viewerKeys = new Set(['/', '/hosts', '/servers', '/services', '/topology', '/topology/servers', '/topology/service-groups', '/logs', '/databases', '/alerts', '/ops', '/remediations', '/runbooks', '/multi-server', '/service-groups', '/on-call', '/sla', '/ai-operation-logs']);
/** member 隐藏的菜单 key */
const memberHiddenKeys = new Set(['/users', '/settings', '/ai-configs']);

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

/** 根据用户设置隐藏菜单（支持分组结构） */
function filterMenuByHidden(items: ReturnType<typeof buildMenuItems>, hiddenKeys: Set<string>) {
  return items
    .map((group) => {
      const children = ((group as any).children as any[])
        .map((item: any) => {
          if ('children' in item && Array.isArray(item.children)) {
            const nestedChildren = item.children.filter((c: any) => !hiddenKeys.has(c.key));
            if (nestedChildren.length === 0) return null;
            return { ...item, children: nestedChildren };
          }
          return hiddenKeys.has(item.key) ? null : item;
        })
        .filter(Boolean);
      return { ...group, children };
    })
    .filter((group) => ((group as any).children as any[]).length > 0);
}

/** 从 label 中提取纯文本（兼容 JSX <span> 包裹和字符串） */
function extractLabelText(label: any): string {
  if (typeof label === 'string') return label;
  if (label && typeof label === 'object' && label.props?.children) {
    const children = label.props.children;
    return typeof children === 'string' ? children : String(children);
  }
  return String(label ?? '');
}

/** 提取可配置隐藏的叶子菜单项 */
function getConfigurableMenuItems(items: ReturnType<typeof buildMenuItems>) {
  const result: Array<{ key: string; label: string }> = [];
  for (const group of items as any[]) {
    for (const item of group.children || []) {
      if (item.children && Array.isArray(item.children)) {
        for (const child of item.children) {
          result.push({ key: child.key, label: extractLabelText(child.label) });
        }
      } else {
        result.push({ key: item.key, label: extractLabelText(item.label) });
      }
    }
  }
  return result;
}

/** 生成侧边栏菜单项（分 4 个分组），使用 i18n 翻译 */
function buildMenuItems(t: (key: string) => string) {
  return [
    {
      type: 'group' as const,
      label: t('menu.groupMonitoring'),
      children: [
        { key: '/dashboard', icon: <DashboardOutlined />, label: <span data-tour="dashboard">{t('menu.dashboard')}</span> },
        { key: '/hosts', icon: <CloudServerOutlined />, label: <span data-tour="hosts">{t('menu.hosts')}</span> },
        { key: '/services', icon: <ApiOutlined />, label: t('menu.services') },
        { key: '/topology', icon: <DeploymentUnitOutlined />, label: t('menu.topologyService') },
        { key: '/topology/servers', icon: <ClusterOutlined />, label: t('menu.topologyServers') },
        { key: '/topology/service-groups', icon: <AppstoreOutlined />, label: t('menu.topologyServiceGroups') },
        { key: '/logs', icon: <FileTextOutlined />, label: t('menu.logs') },
        { key: '/databases', icon: <DatabaseOutlined />, label: t('menu.databases') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupAlerts'),
      children: [
        { key: '/alerts', icon: <AlertOutlined />, label: <span data-tour="alerts">{t('menu.alerts')}</span> },
        { key: '/alert-escalation', icon: <RiseOutlined />, label: t('menu.alertEscalation') },
        { key: '/on-call', icon: <ScheduleOutlined />, label: t('menu.onCall') },
        { key: '/sla', icon: <SafetyCertificateOutlined />, label: t('menu.sla') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupAnalysis'),
      children: [
        { key: '/ops', icon: <RobotOutlined />, label: <span data-tour="ai-analysis">{t('menu.aiAnalysis')}</span> },
        { key: '/ai-operation-logs', icon: <HistoryOutlined />, label: t('menu.aiOperationLogs') },
        { key: '/remediations', icon: <ThunderboltOutlined />, label: <span data-tour="remediation">{t('menu.remediation')}</span> },
        { key: '/runbooks', icon: <BookOutlined />, label: t('menu.runbooks') },
        { key: '/reports', icon: <FileSearchOutlined />, label: t('menu.reports') },
      ],
    },
    {
      type: 'group' as const,
      label: t('menu.groupConfig'),
      children: [
        { key: '/notification-channels', icon: <NotificationOutlined />, label: t('menu.notificationChannels') },
        { key: '/notification-templates', icon: <FormOutlined />, label: t('menu.notificationTemplates') },
        { key: '/notification-logs', icon: <UnorderedListOutlined />, label: t('menu.notificationLogs') },
        { key: '/users', icon: <TeamOutlined />, label: t('menu.users') },
        { key: '/audit-logs', icon: <AuditOutlined />, label: t('menu.auditLogs') },
        { key: '/ai-configs', icon: <RobotOutlined />, label: t('menu.aiConfigs') },
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
  /** 菜单展开的 SubMenu keys */
  const [menuOpenKeys, setMenuOpenKeys] = useState<string[]>([]);
  
  const navigate = useNavigate();
  const location = useLocation();
  const { token: { colorBgContainer, borderRadiusLG, colorBgLayout } } = theme.useToken();
  const { isDark, toggleTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const { isMobile } = useResponsive();
  const isOpsPage = location.pathname === '/ops';
  const { tourOpen, closeTour, restartTour } = useTourControl();

  /** 动态生成菜单 */
  const allMenuItems = buildMenuItems(t);

  /** 切换语言 */
  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
    localStorage.setItem('language', lang);
  };

  /** 移动端自动折叠侧边栏 */
  useEffect(() => {
    if (isMobile) setCollapsed(true);
  }, [isMobile]);

  /** 从 localStorage 读取用户名和角色 */
  const userName = localStorage.getItem('user_name') || 'Admin';
  const userRole = localStorage.getItem('user_role') || 'viewer';
  const [messageApi, messageContextHolder] = message.useMessage();
  const [hiddenMenuKeys, setHiddenMenuKeys] = useState<string[]>([]);
  const [menuSettingsOpen, setMenuSettingsOpen] = useState(false);
  const [menuDraftKeys, setMenuDraftKeys] = useState<string[]>([]);
  const [menuSaving, setMenuSaving] = useState(false);

  useEffect(() => {
    const loadMenuSettings = async () => {
      try {
        const data = await menuSettingsApi.get();
        const keys = Array.isArray(data.hidden_keys)
          ? data.hidden_keys.filter((k) => typeof k === 'string')
          : [];
        setHiddenMenuKeys(keys);
        setMenuDraftKeys(keys);
      } catch {
        setHiddenMenuKeys([]);
        setMenuDraftKeys([]);
      }
    };
    loadMenuSettings();
  }, []);

  const handleSaveMenuSettings = async () => {
    try {
      setMenuSaving(true);
      const data = await menuSettingsApi.update({ hidden_keys: menuDraftKeys });
      const keys = Array.isArray(data.hidden_keys)
        ? data.hidden_keys.filter((k) => typeof k === 'string')
        : [];
      setHiddenMenuKeys(keys);
      setMenuDraftKeys(keys);
      setMenuSettingsOpen(false);
      messageApi.success(t('header.menuSettingsSaved'));
    } catch {
      messageApi.error(t('header.menuSettingsSaveFailed'));
    } finally {
      setMenuSaving(false);
    }
  };

  const roleFilteredMenuItems = filterMenuByRole(allMenuItems, userRole);
  const menuItems = filterMenuByHidden(roleFilteredMenuItems, new Set(hiddenMenuKeys));
  const configurableMenuItems = getConfigurableMenuItems(roleFilteredMenuItems);

  /** 退出登录：清除本地存储的认证信息并跳转到登录页
   * P0-2 骨架：同步调用后端 /auth/logout 清除 httpOnly cookie
   */
  const handleLogout = async () => {
    try {
      // 清除后端 httpOnly cookie（JWT 已迁移至 cookie，无法从 JS 直接删除）
      await fetch('/api/v1/auth/logout', { method: 'POST', credentials: 'include' });
    } catch {
      // 即使请求失败也继续本地清理，不阻塞退出流程
    }
    // 清除非敏感显示信息（access_token/refresh_token 不再存 localStorage）
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
    return matched || '/dashboard';
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
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* 品牌标识区域 —— 替换为统一的 <Logo /> 组件 */}
      <div
        style={{
          height: 64,
          flexShrink: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: (inDrawer || !collapsed) ? 'flex-start' : 'center',
          paddingLeft: (inDrawer || !collapsed) ? 20 : 0,
          paddingRight: (inDrawer || !collapsed) ? 12 : 0,
          borderBottom: `1px solid var(--nm-border, #27272a)`,
        }}
      >
        {(inDrawer || !collapsed) ? (
          <Logo variant="wordmark" size={22} />
        ) : (
          <Logo variant="icon" size={28} />
        )}
      </div>
      <div className="app-sidebar-menu-scroll">
        <Menu
          theme={inDrawer ? (isDark ? 'dark' : 'light') : 'dark'}
          mode="inline"
          selectedKeys={[selectedKey]}
          openKeys={menuOpenKeys}
          onOpenChange={(keys) => setMenuOpenKeys(keys as string[])}
          items={menuItems}
          onClick={handleMenuClick}
        />
      </div>
    </div>
  );

  return (
    <Layout
      style={{
        height: '100vh',
        overflow: 'hidden',
        background: colorBgLayout,
      }}
    >
      {/* 桌面端侧边栏 —— DESIGN.md 规定 200px 固定宽 */}
      {!isMobile && (
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          theme="dark"
          className="app-sidebar"
          width={200}
          collapsedWidth={64}
        >
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
          bodyStyle={{ padding: 0, background: isDark ? '#141414' : undefined }}
          width={280}
          styles={{ header: { background: isDark ? '#141414' : undefined }, body: { background: isDark ? '#141414' : undefined } }}
        >
          {renderMenuContent(true)}
        </Drawer>
      )}
      <Layout
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100vh',
          overflow: 'hidden',
        }}
      >
        <Header style={{
          padding: isMobile ? '0 16px' : '0 24px',
          background: colorBgContainer,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flex: '0 0 auto',
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
            {userRole === 'admin' && (
              <Popover
                trigger="click"
                placement="bottomRight"
                open={menuSettingsOpen}
                onOpenChange={(open) => {
                  setMenuSettingsOpen(open);
                  if (open) setMenuDraftKeys(hiddenMenuKeys);
                }}
                content={(
                  <div style={{ width: 280, maxHeight: 400, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ fontWeight: 600, marginBottom: 8 }}>{t('header.menuSettings')}</div>
                    <div style={{ flex: 1, overflowY: 'auto', marginBottom: 8 }}>
                      <Checkbox.Group
                        style={{ width: '100%' }}
                        value={configurableMenuItems.map(i => i.key).filter(k => !menuDraftKeys.includes(k))}
                        onChange={(visibleKeys) => {
                          const allKeys = configurableMenuItems.map(i => i.key);
                          setMenuDraftKeys(allKeys.filter(k => !(visibleKeys as string[]).includes(k)));
                        }}
                      >
                        <Space direction="vertical" style={{ width: '100%' }}>
                          {configurableMenuItems.map((item) => (
                            <Checkbox key={item.key} value={item.key}>
                              {item.label}
                            </Checkbox>
                          ))}
                        </Space>
                      </Checkbox.Group>
                    </div>
                    <Divider style={{ margin: '12px 0' }} />
                    <Space>
                      <Button size="small" onClick={() => setMenuDraftKeys([])}>
                        {t('header.resetMenuSettings')}
                      </Button>
                      <Button size="small" onClick={() => setMenuSettingsOpen(false)}>
                        {t('common.cancel')}
                      </Button>
                      <Button size="small" type="primary" loading={menuSaving} onClick={handleSaveMenuSettings}>
                        {t('common.save')}
                      </Button>
                    </Space>
                  </div>
                )}
              >
                <Button type="text" icon={<EyeInvisibleOutlined />} title={t('header.menuSettings')} />
              </Popover>
            )}
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
                { key: 'restart-tour', icon: <QuestionCircleOutlined />, label: t('header.restartTour'), onClick: restartTour },
                { type: 'divider' as const },
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
        <Content style={
          isOpsPage
            ? {
                margin: 0,
                padding: 0,
                background: 'transparent',
                flex: 1,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
              }
            : {
                margin: isMobile ? 12 : 24,
                padding: isMobile ? 16 : 24,
                background: colorBgContainer,
                borderRadius: borderRadiusLG,
                minHeight: 280,
                flex: 1,
                overflow: 'auto',
              }
        }>
          {/* 子路由内容渲染区 */}
          <Outlet />
        </Content>
      </Layout>
      {/* 新手引导（首次登录时弹出） */}
      <QuickStartGuide />
      {messageContextHolder}
      {/* 步骤式引导 Tour */}
      <GuidedTour open={tourOpen} onClose={closeTour} />
    </Layout>
  );
}
