/**
 * 新手引导组件（Quick Start Guide）
 *
 * 首次登录时在右下角弹出引导抽屉：
 * - 4步引导：安装 Agent → 查看主机数据 → 配置告警规则 → 设置通知渠道
 * - 可随时关闭，点「不再显示」则永久关闭
 * - 支持中英双语（i18n）
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Drawer, Steps, Button, Space, Typography, theme } from 'antd';
import {
  CloudServerOutlined,
  MonitorOutlined,
  AlertOutlined,
  NotificationOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const ONBOARDING_KEY = 'onboarding_done';

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
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken();

  const [open, setOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    // Only show if onboarding not done and user is logged in
    const done = localStorage.getItem(ONBOARDING_KEY);
    const userName = localStorage.getItem('user_name');
    if (!done && userName) {
      // Small delay so dashboard loads first
      const timer = setTimeout(() => setOpen(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const handleClose = () => {
    setOpen(false);
  };

  const handleDoNotShow = () => {
    localStorage.setItem(ONBOARDING_KEY, '1');
    setOpen(false);
  };

  const handleGoAction = (route: string) => {
    navigate(route);
    setOpen(false);
  };

  const stepsItems = STEPS.map((step, idx) => ({
    title: t(step.titleKey),
    status: idx < currentStep ? 'finish' as const : idx === currentStep ? 'process' as const : 'wait' as const,
    icon: idx < currentStep ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> : step.icon,
  }));

  const currentStepConfig = STEPS[currentStep];

  return (
    <Drawer
      title={
        <div>
          <Title level={4} style={{ margin: 0 }}>{t('quickStart.title')}</Title>
          <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
            {t('quickStart.subtitle')}
          </Text>
        </div>
      }
      placement="right"
      width={400}
      open={open}
      onClose={handleClose}
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
          <Button onClick={handleClose}>
            {t('quickStart.close')}
          </Button>
        </div>
      }
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
