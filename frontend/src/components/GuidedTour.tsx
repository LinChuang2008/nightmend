/**
 * 新手引导 Tour 组件
 *
 * 使用 Ant Design Tour 实现 5 步引导，覆盖核心功能路径：
 * 1. Dashboard概览 — 健康分含义
 * 2. 主机列表 — 查看已监控服务器
 * 3. 告警中心 — 当前活跃告警
 * 4. AI分析 — 点击告警查看AI根因分析
 * 5. 自动修复 — Runbook审批与执行
 *
 * - 首次登录自动触发
 * - localStorage 记录完成状态
 * - 可通过用户菜单「重新引导」再次触发
 */
import { useState, useEffect, useCallback } from 'react';
import { Tour } from 'antd';
import type { TourStepProps } from 'antd/es/tour/interface';
import {
  DashboardOutlined,
  CloudServerOutlined,
  AlertOutlined,
  RobotOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const TOUR_COMPLETED_KEY = 'nightmend_tour_completed';

export function useTourControl() {
  const [tourOpen, setTourOpen] = useState(false);

  const startTour = useCallback(() => {
    setTourOpen(true);
  }, []);

  const closeTour = useCallback(() => {
    setTourOpen(false);
    localStorage.setItem(TOUR_COMPLETED_KEY, '1');
  }, []);

  useEffect(() => {
    const done = localStorage.getItem(TOUR_COMPLETED_KEY);
    const userName = localStorage.getItem('user_name');
    if (!done && userName) {
      const timer = setTimeout(() => setTourOpen(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const restartTour = useCallback(() => {
    localStorage.removeItem(TOUR_COMPLETED_KEY);
    setTourOpen(true);
  }, []);

  return { tourOpen, startTour, closeTour, restartTour };
}

interface GuidedTourProps {
  open: boolean;
  onClose: () => void;
}

export default function GuidedTour({ open, onClose }: GuidedTourProps) {
  const { t } = useTranslation();

  const steps: TourStepProps[] = [
    {
      title: t('guidedTour.steps.dashboard.title'),
      description: t('guidedTour.steps.dashboard.description'),
      cover: (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <DashboardOutlined style={{ fontSize: 48, color: '#1677ff' }} />
        </div>
      ),
      target: () => document.querySelector('[data-tour="dashboard"]') as HTMLElement,
    },
    {
      title: t('guidedTour.steps.hosts.title'),
      description: t('guidedTour.steps.hosts.description'),
      cover: (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <CloudServerOutlined style={{ fontSize: 48, color: '#52c41a' }} />
        </div>
      ),
      target: () => document.querySelector('[data-tour="hosts"]') as HTMLElement,
    },
    {
      title: t('guidedTour.steps.alerts.title'),
      description: t('guidedTour.steps.alerts.description'),
      cover: (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <AlertOutlined style={{ fontSize: 48, color: '#faad14' }} />
        </div>
      ),
      target: () => document.querySelector('[data-tour="alerts"]') as HTMLElement,
    },
    {
      title: t('guidedTour.steps.aiAnalysis.title'),
      description: t('guidedTour.steps.aiAnalysis.description'),
      cover: (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <RobotOutlined style={{ fontSize: 48, color: '#722ed1' }} />
        </div>
      ),
      target: () => document.querySelector('[data-tour="ai-analysis"]') as HTMLElement,
    },
    {
      title: t('guidedTour.steps.remediation.title'),
      description: t('guidedTour.steps.remediation.description'),
      cover: (
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <ThunderboltOutlined style={{ fontSize: 48, color: '#eb2f96' }} />
        </div>
      ),
      target: () => document.querySelector('[data-tour="remediation"]') as HTMLElement,
    },
  ];

  return (
    <Tour
      open={open}
      onClose={onClose}
      steps={steps}
      indicatorsRender={(current, total) => (
        <span>{current + 1} / {total}</span>
      )}
    />
  );
}
