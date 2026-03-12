/**
 * 新手引导组件（Quick Start Guide）
 *
 * 可收缩的右侧引导面板：
 * - 4步引导：安装 Agent → 查看主机数据 → 配置告警规则 → 设置通知渠道
 * - 默认收起状态，用户可手动展开/收起
 * - 仅新用户首次登录时自动展开
 * - 在拓扑图等需要大空间的页面强制隐藏
 * - 使用localStorage记住用户展开/收起偏好
 * - 支持中英双语（i18n）
 */
import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Drawer, Steps, Button, Space, Typography, theme, Tooltip, FloatButton } from 'antd';
import {
  CloudServerOutlined,
  MonitorOutlined,
  AlertOutlined,
  NotificationOutlined,
  CheckCircleOutlined,
  QuestionCircleOutlined,
  CloseOutlined,
  MenuFoldOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const ONBOARDING_KEY = 'onboarding_done';
const GUIDE_EXPANDED_KEY = 'guide_expanded';

// 需要强制隐藏引导面板的页面路径
const FORCE_HIDE_PAGES = ['/topology', '/topology/servers', '/topology/service-groups'];

const { Title, Text } = Typography;

interface StepConfig {
  icon: React.ReactNode;
  titleKey: string;
  descKey: string;
  actionKey: string;
  route: string;
}

const STEPS: StepConfig[] = [
  {
    icon: <CloudServerOutlined style={{ fontSize: 24, color: '#1677ff' }} />,
    titleKey: 'quickStart.steps.installAgent.title',
    descKey: 'quickStart.steps.installAgent.description',
    actionKey: 'quickStart.steps.installAgent.action',
    route: '/settings',
  },
  {
    icon: <MonitorOutlined style={{ fontSize: 24, color: '#52c41a' }} />,
    titleKey: 'quickStart.steps.viewHosts.title',
    descKey: 'quickStart.steps.viewHosts.description',
    actionKey: 'quickStart.steps.viewHosts.action',
    route: '/hosts',
  },
  {
    icon: <AlertOutlined style={{ fontSize: 24, color: '#faad14' }} />,
    titleKey: 'quickStart.steps.configureAlerts.title',
    descKey: 'quickStart.steps.configureAlerts.description',
    actionKey: 'quickStart.steps.configureAlerts.action',
    route: '/alerts',
  },
  {
    icon: <NotificationOutlined style={{ fontSize: 24, color: '#722ed1' }} />,
    titleKey: 'quickStart.steps.setNotification.title',
    descKey: 'quickStart.steps.setNotification.description',
    actionKey: 'quickStart.steps.setNotification.action',
    route: '/notification-channels',
  },
];

export default function QuickStartGuide() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken();

  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  // 检查当前页面是否需要强制隐藏引导面板
  const shouldForceHide = FORCE_HIDE_PAGES.some(path => location.pathname.startsWith(path));

  useEffect(() => {
    // 如果在强制隐藏页面，直接隐藏
    if (shouldForceHide) {
      setOpen(false);
      setExpanded(false);
      return;
    }

    // 检查是否已完成引导
    const done = localStorage.getItem(ONBOARDING_KEY);
    const userName = localStorage.getItem('user_name');
    
    if (done || !userName) {
      // 已完成引导或未登录，不显示面板
      setOpen(false);
      return;
    }

    // 新用户首次登录，显示面板
    setOpen(true);
    
    // 检查用户的展开偏好，默认收起状态
    const expandedPref = localStorage.getItem(GUIDE_EXPANDED_KEY);
    setExpanded(expandedPref === 'true');
  }, [location.pathname, shouldForceHide]);

  const handleClose = () => {
    setOpen(false);
    localStorage.setItem(ONBOARDING_KEY, '1');
  };

  const handleDoNotShow = () => {
    localStorage.setItem(ONBOARDING_KEY, '1');
    setOpen(false);
  };

  const handleToggleExpand = () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    localStorage.setItem(GUIDE_EXPANDED_KEY, newExpanded.toString());
  };

  const handleGoAction = (route: string) => {
    navigate(route);
    // 不关闭面板，让用户继续使用引导
  };

  const stepsItems = STEPS.map((step, idx) => ({
    title: t(step.titleKey),
    status: idx < currentStep ? 'finish' as const : idx === currentStep ? 'process' as const : 'wait' as const,
    icon: idx < currentStep ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : step.icon,
  }));

  const currentStepConfig = STEPS[currentStep];

  // 如果面板应该显示但未展开，显示浮动按钮
  if (open && !expanded) {
    return (
      <Tooltip title={t('quickStart.title')} placement="left">
        <FloatButton
          icon={<QuestionCircleOutlined />}
          type="primary"
          style={{
            position: 'fixed',
            right: 24,
            top: '50%',
            transform: 'translateY(-50%)',
            zIndex: 1000,
          }}
          onClick={handleToggleExpand}
        />
      </Tooltip>
    );
  }

  // 展开状态下的完整面板
  if (open && expanded) {
    return (
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <Title level={4} style={{ margin: 0 }}>{t('quickStart.title')}</Title>
              <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
                {t('quickStart.subtitle')}
              </Text>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <Tooltip title={t('quickStart.collapse')}>
                <Button
                  type="text"
                  icon={<MenuFoldOutlined />}
                  onClick={handleToggleExpand}
                  size="small"
                />
              </Tooltip>
              <Tooltip title={t('quickStart.close')}>
                <Button
                  type="text"
                  icon={<CloseOutlined />}
                  onClick={handleClose}
                  size="small"
                />
              </Tooltip>
            </div>
          </div>
        }
        placement="right"
        width={380}
        open={true}
        onClose={handleToggleExpand}
        mask={false}
        style={{ position: 'fixed' }}
        styles={{
          body: { padding: '16px 24px' },
          wrapper: { boxShadow: '-4px 0 20px rgba(0,0,0,0.12)' },
        }}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Button type="text" onClick={handleDoNotShow}>
              {t('quickStart.doNotShow')}
            </Button>
            <Space>
              <Button onClick={handleToggleExpand}>
                {t('quickStart.collapse')}
              </Button>
              <Button type="primary" onClick={handleClose}>
                {t('quickStart.close')}
              </Button>
            </Space>
          </div>
        }
        closable={false}
      >
        {/* Step indicators */}
        <Steps
          current={currentStep}
          items={stepsItems}
          size="small"
          direction="vertical"
          style={{ marginBottom: 24 }}
          onChange={setCurrentStep}
        />

        {/* Current step detail */}
        <div style={{
          background: colorBgContainer,
          border: '1px solid rgba(0,0,0,0.08)',
          borderRadius: borderRadiusLG,
          padding: 16,
        }}>
          <Space align="start" style={{ marginBottom: 12 }}>
            {currentStepConfig.icon}
            <div>
              <Title level={5} style={{ margin: 0 }}>
                {t(currentStepConfig.titleKey)}
              </Title>
            </div>
          </Space>
          <Text style={{ display: 'block', marginBottom: 16, color: '#666' }}>
            {t(currentStepConfig.descKey)}
          </Text>
          <Space>
            <Button
              type="primary"
              onClick={() => handleGoAction(currentStepConfig.route)}
            >
              {t(currentStepConfig.actionKey)}
            </Button>
            {currentStep < STEPS.length - 1 && (
              <Button onClick={() => setCurrentStep(prev => prev + 1)}>
                {t('quickStart.nextStep')}
              </Button>
            )}
          </Space>
        </div>
      </Drawer>
    );
  }

  // 不显示面板
  return null;
}
