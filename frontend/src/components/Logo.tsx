/**
 * NightMend Logo 组件
 *
 * 三种形态：
 *   - icon: 仅图标（64x64 等比）—— 侧栏折叠 / favicon / 头像位
 *   - wordmark: 图标 + NightMend 文字横排 —— 侧栏展开 / 页头
 *   - stacked: 图标在上、文字在下 —— 登录页中央
 *
 * 样式策略：
 *   直接 inline SVG，保持和 favicon.svg 结构一致，避免 <img> 加载闪烁 +
 *   允许 CSS 通过 currentColor/--accent 覆盖主色。
 */
import type { CSSProperties } from 'react';

interface LogoProps {
  variant?: 'icon' | 'wordmark' | 'stacked';
  /** icon size in px；wordmark 会按 icon 比例推 text 大小 */
  size?: number;
  className?: string;
  style?: CSSProperties;
}

/** 盾牌 + 闭眼 + 心跳 —— 所有变体共用的 SVG 主体（viewBox 64x64）。
    盾 = 守护；闭眼 = 你睡；心跳 = AI 仍醒着做事。 */
function IconSVG({ size }: { size: number }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      fill="none"
      aria-hidden
    >
      {/* 盾牌外形 */}
      <path
        d="M 12 8 L 52 8 Q 56 8 56 12 L 56 32 Q 56 48 32 60 Q 8 48 8 32 L 8 12 Q 8 8 12 8 Z"
        fill="#0a0a0f"
        stroke="#10B981"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      {/* 闭眼 */}
      <path
        d="M 18 26 Q 32 33 46 26"
        stroke="#e4e4e7"
        strokeWidth="3"
        strokeLinecap="round"
        fill="none"
      />
      {/* 睫毛 / 针脚（sleep + 修补双关）*/}
      {[
        { x1: 22, y1: 24, x2: 21, y2: 20 },
        { x1: 27, y1: 25, x2: 26, y2: 20 },
        { x1: 32, y1: 25.5, x2: 32, y2: 20 },
        { x1: 37, y1: 25, x2: 38, y2: 20 },
        { x1: 42, y1: 24, x2: 43, y2: 20 },
      ].map((p, i) => (
        <line key={i} {...p} stroke="#e4e4e7" strokeWidth="2" strokeLinecap="round" />
      ))}
      {/* 心跳波形 */}
      <path
        d="M 13 42 L 20 42 L 23 37 L 27 48 L 31 42 L 38 42 L 41 45 L 45 38 L 51 42"
        stroke="#10B981"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* 波峰亮点 */}
      <circle cx="27" cy="48" r="2" fill="#10B981" />
    </svg>
  );
}

export function Logo({ variant = 'wordmark', size = 28, className, style }: LogoProps) {
  if (variant === 'icon') {
    return (
      <span className={className} style={{ display: 'inline-flex', ...style }} aria-label="NightMend">
        <IconSVG size={size} />
      </span>
    );
  }

  if (variant === 'stacked') {
    const textSize = Math.round(size * 0.7);
    return (
      <div
        className={className}
        style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 12, ...style }}
        aria-label="NightMend"
      >
        <IconSVG size={size} />
        <span
          style={{
            fontFamily: "Geist, 'Geist Sans', system-ui, -apple-system, sans-serif",
            fontWeight: 700,
            fontSize: textSize,
            letterSpacing: '-0.02em',
            color: 'var(--nm-text, #e4e4e7)',
            lineHeight: 1,
          }}
        >
          NightMend
        </span>
      </div>
    );
  }

  // wordmark (默认)
  const textSize = Math.round(size * 0.78);
  return (
    <div
      className={className}
      style={{ display: 'inline-flex', alignItems: 'center', gap: Math.round(size * 0.28), ...style }}
      aria-label="NightMend"
    >
      <IconSVG size={size} />
      <span
        style={{
          fontFamily: "Geist, 'Geist Sans', system-ui, -apple-system, sans-serif",
          fontWeight: 700,
          fontSize: textSize,
          letterSpacing: '-0.02em',
          color: 'var(--nm-text, #e4e4e7)',
          lineHeight: 1,
        }}
      >
        NightMend
      </span>
    </div>
  );
}

export default Logo;
