/**
 * 通用页面头 —— Phase 3 导航壳闭环
 *
 * 对齐 DESIGN.md：
 *   - h3 级字号 18px + Geist 600
 *   - 副标题 --nm-text-muted + 13px
 *   - 不加边框/阴影，靠留白分隔主内容
 *   - 右侧操作区（extra）与左侧主标对齐基线
 */
import type { ReactNode } from 'react';

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
  tags?: ReactNode;
}

export default function PageHeader({ title, subtitle, extra, tags }: PageHeaderProps) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-end',
        gap: 16,
        marginBottom: 'var(--nm-space-md, 16px)',
        paddingBottom: 'var(--nm-space-sm, 8px)',
        borderBottom: '1px solid var(--nm-border, #27272a)',
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <h2
            style={{
              margin: 0,
              fontFamily: 'var(--nm-font-sans)',
              fontSize: 'var(--nm-text-18, 18px)',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              color: 'var(--nm-text, #e4e4e7)',
              lineHeight: 1.3,
            }}
          >
            {title}
          </h2>
          {tags}
        </div>
        {subtitle && (
          <div
            style={{
              fontSize: 'var(--nm-text-13, 13px)',
              color: 'var(--nm-text-muted, #71717a)',
              marginTop: 4,
              fontFamily: 'var(--nm-font-sans)',
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
      {extra && <div style={{ flexShrink: 0 }}>{extra}</div>}
    </div>
  );
}
