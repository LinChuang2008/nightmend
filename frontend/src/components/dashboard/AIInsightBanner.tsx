/**
 * AI 洞察摘要卡片组件
 * 深色科技背景，最新 AI 洞察 + CTA 按钮，无数据时压缩为单行提示
 */
import { useState } from 'react';
import { Button, Typography } from 'antd';
import { RobotOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import AIInsightDetailModal from './AIInsightDetailModal';
import type { AIInsightItem } from '../../services/aiAnalysis';

const { Text } = Typography;

export interface AIInsight {
  id: string;
  conclusion: string;
  created_at: string;
  severity: 'info' | 'warning' | 'critical';
  title?: string;
  summary?: string;
  insight_type?: string;
  details?: Record<string, unknown> | null;
  status?: string;
}

interface AIInsightBannerProps {
  insight: AIInsight | null;
  loading?: boolean;
  onViewDetail?: () => void;
}

export default function AIInsightBanner({ insight, loading = false }: AIInsightBannerProps) {
  const { t } = useTranslation();
  const [detailOpen, setDetailOpen] = useState(false);

  const insightForModal: AIInsightItem | null = insight
    ? {
        id: Number(insight.id) || 0,
        insight_type: insight.insight_type || 'anomaly',
        severity: insight.severity,
        title: insight.title || insight.conclusion || '',
        summary: insight.summary || insight.conclusion || '',
        details: insight.details || null,
        status: insight.status || 'new',
        created_at: insight.created_at,
      }
    : null;

  // 无数据且非加载中：压缩为单行空状态提示
  if (!insight && !loading) {
    return (
      <div
        style={{
          background: 'linear-gradient(135deg, #0d1b2a 0%, #1a2940 100%)',
          borderRadius: 12,
          border: '1px solid rgba(54, 207, 201, 0.15)',
          padding: '14px 20px',
          height: '100%',
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <RobotOutlined style={{ color: '#36cfc9', fontSize: 20, opacity: 0.7 }} />
          <Text style={{ color: 'rgba(138, 180, 204, 0.8)', fontSize: 14 }}>
            {t('dashboard.aiNoData', '暂无 AI 洞察数据')}
          </Text>
        </div>
        <Button
          type="link"
          size="small"
          style={{ color: '#36cfc9', padding: 0, fontSize: 13, height: 'auto', opacity: 0.8 }}
          onClick={onViewDetail}
          icon={<ArrowRightOutlined />}
        >
          {t('dashboard.viewFullAnalysis')}
        </Button>
      </div>
    );
  }

  return (
    <>
      <div
        style={{
          background: 'linear-gradient(135deg, #0d1b2a 0%, #1a2940 50%, #0d2235 100%)',
          borderRadius: 12,
          border: '1px solid rgba(54, 207, 201, 0.2)',
          padding: '20px 24px',
          position: 'relative',
          overflow: 'hidden',
          height: '100%',
          boxSizing: 'border-box',
        }}
      >
        {/* 右侧装饰波纹圆圈 */}
        <div
          style={{
            position: 'absolute',
            right: 24,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 80,
            height: 80,
            borderRadius: '50%',
            border: '2px solid rgba(54, 207, 201, 0.18)',
            animation: 'aiPulse 2.5s ease-in-out infinite',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            right: 34,
            top: '50%',
            transform: 'translateY(-50%)',
            width: 60,
            height: 60,
            borderRadius: '50%',
            border: '2px solid rgba(54, 207, 201, 0.1)',
            pointerEvents: 'none',
          }}
        />

        {/* 主内容 */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, paddingRight: 80 }}>
          <RobotOutlined style={{ color: '#36cfc9', fontSize: 28, marginTop: 2, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <Text
              style={{
                fontSize: 11,
                color: '#36cfc9',
                letterSpacing: 2,
                display: 'block',
                marginBottom: 6,
                textTransform: 'uppercase',
              }}
            >
              {t('dashboard.aiInsightTitle')}
            </Text>
            <Text
              style={{
                fontSize: 15,
                color: loading ? '#8ab4cc' : '#e8f4f8',
                fontWeight: 500,
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                lineHeight: '1.5em',
                maxHeight: '3em',
              }}
            >
              {loading
                ? t('dashboard.aiAnalyzing')
                : (insight?.conclusion ?? t('dashboard.aiNoData', '暂无 AI 洞察数据'))}
            </Text>
            <div
              style={{
                marginTop: 10,
                borderTop: '1px solid rgba(54, 207, 201, 0.15)',
                paddingTop: 8,
              }}
            >
              <Button
                type="link"
                size="small"
                style={{ color: '#36cfc9', padding: 0, fontSize: 13, height: 'auto' }}
                onClick={() => insight && setDetailOpen(true)}
                disabled={!insight}
              >
                {t('dashboard.viewFullAnalysis')}
              </Button>
            </div>
          </div>
        </div>

        <style>{`
          @keyframes aiPulse {
            0%   { box-shadow: 0 0 0 0 rgba(54, 207, 201, 0.4); }
            70%  { box-shadow: 0 0 0 12px rgba(54, 207, 201, 0); }
            100% { box-shadow: 0 0 0 0 rgba(54, 207, 201, 0); }
          }
        `}</style>
      </div>

      <AIInsightDetailModal
        open={detailOpen}
        insight={insightForModal}
        onClose={() => setDetailOpen(false)}
      />
    </>
  );
}
