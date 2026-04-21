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

export default function AIInsightBanner({ insight, loading = false, onViewDetail }: AIInsightBannerProps) {
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

  // 无数据且非加载中：压缩为单行空状态提示 —— 去渐变，遵守 DESIGN.md
  if (!insight && !loading) {
    return (
      <div
        style={{
          background: 'var(--nm-surface, #141419)',
          borderRadius: 'var(--nm-radius-md, 6px)',
          border: '1px solid var(--nm-border, #27272a)',
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
          <RobotOutlined style={{ color: 'var(--nm-accent, #10B981)', fontSize: 20 }} />
          <Text style={{ color: 'var(--nm-text-muted, #71717a)', fontSize: 14 }}>
            {t('dashboard.aiNoData', '暂无 AI 洞察数据')}
          </Text>
        </div>
        <Button
          type="link"
          size="small"
          style={{ color: 'var(--nm-accent, #10B981)', padding: 0, fontSize: 13, height: 'auto' }}
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
          background: 'var(--nm-surface, #141419)',
          borderRadius: 'var(--nm-radius-md, 6px)',
          border: '1px solid var(--nm-border, #27272a)',
          padding: '20px 24px',
          position: 'relative',
          height: '100%',
          boxSizing: 'border-box',
        }}
      >
        {/* 装饰性波纹圆圈已移除（DESIGN.md: no decorative elements）*/}

        {/* 主内容 —— 对齐 DESIGN.md token */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <RobotOutlined style={{ color: 'var(--nm-accent, #10B981)', fontSize: 28, marginTop: 2, flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <Text
              style={{
                fontSize: 11,
                color: 'var(--nm-accent, #10B981)',
                letterSpacing: 2,
                display: 'block',
                marginBottom: 6,
                textTransform: 'uppercase',
                fontFamily: 'var(--nm-font-mono, ui-monospace, monospace)',
              }}
            >
              {t('dashboard.aiInsightTitle')}
            </Text>
            <Text
              style={{
                fontSize: 15,
                color: loading ? 'var(--nm-text-muted, #71717a)' : 'var(--nm-text, #e4e4e7)',
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
                borderTop: '1px solid var(--nm-border, #27272a)',
                paddingTop: 8,
              }}
            >
              <Button
                type="link"
                size="small"
                style={{ color: 'var(--nm-accent, #10B981)', padding: 0, fontSize: 13, height: 'auto' }}
                onClick={() => insight && setDetailOpen(true)}
                disabled={!insight}
              >
                {t('dashboard.viewFullAnalysis')}
              </Button>
            </div>
          </div>
        </div>
      </div>

      <AIInsightDetailModal
        open={detailOpen}
        insight={insightForModal}
        onClose={() => setDetailOpen(false)}
      />
    </>
  );
}
