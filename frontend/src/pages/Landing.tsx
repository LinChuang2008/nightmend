/**
 * Landing Page - 产品首页
 * 未登录用户的默认入口，展示产品价值、核心特性和CTA
 * Design system: DESIGN.md (dark theme, emerald accent, Geist typography)
 */
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../contexts/ThemeContext';

/* ── Design Tokens (from DESIGN.md) ────────────────────────── */
const C = {
  bg: '#0a0a0f',
  surface: '#141419',
  surfaceHover: '#1a1a21',
  border: '#27272a',
  text: '#e4e4e7',
  muted: '#71717a',
  dim: '#52525b',
  accent: '#10B981',
  accentDim: '#065f46',
  success: '#10B981',
  error: '#ef4444',
} as const;

const font = {
  sans: "'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
  mono: "'Geist Mono', 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace",
} as const;

/* ── Comparison Data ───────────────────────────────────────── */
const comparisonRows = (t: (key: string) => string) => [
  { key: '1', feature: t('landing.comparison.aiAnalysis'), nightmend: true, datadog: true, grafana: false, zabbix: false },
  { key: '2', feature: t('landing.comparison.autoRemediation'), nightmend: true, datadog: false, grafana: false, zabbix: false },
  { key: '3', feature: t('landing.comparison.mcpIntegration'), nightmend: true, datadog: false, grafana: false, zabbix: false },
  { key: '4', feature: t('landing.comparison.topologyVisualization'), nightmend: true, datadog: true, grafana: false, zabbix: true },
  { key: '5', feature: t('landing.comparison.slaManagement'), nightmend: true, datadog: true, grafana: false, zabbix: true },
  { key: '6', feature: t('landing.comparison.selfHosted'), nightmend: true, datadog: false, grafana: true, zabbix: true },
  { key: '7', feature: t('landing.comparison.openSource'), nightmend: true, datadog: false, grafana: true, zabbix: true },
];

const vendors = ['NightMend', 'Datadog', 'Grafana', 'Zabbix'] as const;
const vendorKeys = ['nightmend', 'datadog', 'grafana', 'zabbix'] as const;

/* ── Inline check / cross SVGs (no Ant Design icons) ──────── */
function Check() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M4 9.5L7.5 13L14 5" stroke={C.success} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
function Cross() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
      <path d="M5 5L13 13M13 5L5 13" stroke={C.dim} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

/* ── Main Component ────────────────────────────────────────── */
export default function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  useTheme(); // hook required by context, theme always dark per DESIGN.md

  // Metrics data for the "big numbers" section
  const metrics = [
    { number: '47s', title: t('landing.feature1Title'), desc: t('landing.stat1Metric') },
    { number: '13', title: t('landing.feature2Title'), desc: t('landing.stat2Metric') },
    { number: '5', title: t('landing.feature3Title'), desc: t('landing.stat3Metric') },
  ];

  return (
    <div style={{ minHeight: '100vh', background: C.bg, fontFamily: font.sans, color: C.text }}>

      {/* ── Nav ──────────────────────────────────────────── */}
      <nav
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 100,
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0 48px',
          background: 'rgba(10, 10, 15, 0.85)',
          backdropFilter: 'blur(12px)',
          borderBottom: `1px solid ${C.border}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span
            style={{
              fontFamily: font.mono,
              fontWeight: 700,
              fontSize: 18,
              color: C.text,
              letterSpacing: '-0.02em',
            }}
          >
            NightMend
          </span>
          <span
            style={{
              fontFamily: font.mono,
              fontSize: 11,
              color: C.dim,
              border: `1px solid ${C.border}`,
              borderRadius: 4,
              padding: '1px 6px',
            }}
          >
            OSS
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <a
            href="https://github.com/LinChuang2008/nightmend"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              color: C.muted,
              fontSize: 13,
              textDecoration: 'none',
              fontWeight: 500,
              padding: '6px 12px',
              borderRadius: 6,
              transition: 'color 150ms',
            }}
            onMouseEnter={e => (e.currentTarget.style.color = C.text)}
            onMouseLeave={e => (e.currentTarget.style.color = C.muted)}
          >
            GitHub
          </a>
          <button
            onClick={() => navigate('/login')}
            style={{
              fontFamily: font.sans,
              fontSize: 13,
              fontWeight: 600,
              color: C.bg,
              background: C.accent,
              border: 'none',
              borderRadius: 6,
              padding: '6px 16px',
              cursor: 'pointer',
              transition: 'opacity 150ms',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            {t('landing.signIn')}
          </button>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────── */}
      <section
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '96px 48px 80px',
        }}
      >
        {/* Overline */}
        <div
          style={{
            fontFamily: font.mono,
            fontSize: 12,
            fontWeight: 500,
            color: C.accent,
            textTransform: 'uppercase',
            letterSpacing: '0.08em',
            marginBottom: 16,
          }}
        >
          {t('landing.heroTag')}
        </div>

        {/* Headline */}
        <h1
          style={{
            fontSize: 48,
            fontWeight: 700,
            lineHeight: 1.15,
            color: C.text,
            margin: '0 0 20px',
            maxWidth: 720,
            fontFamily: font.sans,
          }}
        >
          {t('landing.heroTitle')}
        </h1>

        {/* Description */}
        <p
          style={{
            fontSize: 16,
            lineHeight: 1.65,
            color: C.muted,
            margin: '0 0 40px',
            maxWidth: 560,
          }}
        >
          {t('landing.heroDescription')}
        </p>

        {/* CTA Buttons */}
        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => navigate('/login')}
            style={{
              fontFamily: font.sans,
              fontSize: 14,
              fontWeight: 600,
              color: C.bg,
              background: C.accent,
              border: 'none',
              borderRadius: 6,
              padding: '10px 24px',
              cursor: 'pointer',
              transition: 'opacity 150ms',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            {t('landing.getStarted')}
          </button>
          <a
            href="https://github.com/LinChuang2008/nightmend/blob/main/README.md"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontFamily: font.sans,
              fontSize: 14,
              fontWeight: 600,
              color: C.text,
              background: 'transparent',
              border: `1px solid ${C.border}`,
              borderRadius: 6,
              padding: '9px 24px',
              cursor: 'pointer',
              textDecoration: 'none',
              display: 'inline-flex',
              alignItems: 'center',
              transition: 'border-color 150ms',
            }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = C.muted)}
            onMouseLeave={e => (e.currentTarget.style.borderColor = C.border)}
          >
            {t('landing.viewDocs')}
          </a>
        </div>
      </section>

      {/* ── Metrics (Big Numbers) ────────────────────────── */}
      <section style={{ maxWidth: 1200, margin: '0 auto', padding: '0 48px 96px' }}>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 24,
          }}
        >
          {metrics.map((m, i) => (
            <div
              key={i}
              style={{
                background: C.surface,
                border: `1px solid ${C.border}`,
                borderRadius: 8,
                padding: '32px 28px',
              }}
            >
              <div
                style={{
                  fontFamily: font.mono,
                  fontSize: 48,
                  fontWeight: 700,
                  color: C.accent,
                  lineHeight: 1,
                  marginBottom: 12,
                }}
              >
                {m.number}
              </div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: C.text,
                  marginBottom: 4,
                }}
              >
                {m.title}
              </div>
              <div
                style={{
                  fontSize: 13,
                  color: C.muted,
                  lineHeight: 1.4,
                }}
              >
                {m.desc}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Comparison Table ─────────────────────────────── */}
      <section style={{ maxWidth: 1200, margin: '0 auto', padding: '0 48px 96px' }}>
        <h2
          style={{
            fontSize: 24,
            fontWeight: 700,
            color: C.text,
            margin: '0 0 8px',
            fontFamily: font.sans,
          }}
        >
          {t('landing.comparisonTitle')}
        </h2>
        <p
          style={{
            fontSize: 14,
            color: C.muted,
            margin: '0 0 32px',
          }}
        >
          {t('landing.comparisonSubtitle')}
        </p>

        <div
          style={{
            border: `1px solid ${C.border}`,
            borderRadius: 8,
            overflow: 'hidden',
          }}
        >
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontFamily: font.sans,
              fontSize: 13,
            }}
          >
            <thead>
              <tr style={{ background: C.surface }}>
                <th
                  style={{
                    textAlign: 'left',
                    padding: '12px 16px',
                    fontWeight: 600,
                    color: C.muted,
                    fontSize: 11,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    borderBottom: `1px solid ${C.border}`,
                  }}
                >
                  {t('landing.comparison.feature')}
                </th>
                {vendors.map(v => (
                  <th
                    key={v}
                    style={{
                      textAlign: 'center',
                      padding: '12px 16px',
                      fontWeight: 600,
                      color: v === 'NightMend' ? C.accent : C.muted,
                      fontSize: 11,
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                      borderBottom: `1px solid ${C.border}`,
                      fontFamily: v === 'NightMend' ? font.mono : font.sans,
                    }}
                  >
                    {v}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {comparisonRows(t).map((row, ri) => (
                <tr
                  key={row.key}
                  style={{
                    borderBottom: ri < comparisonRows(t).length - 1 ? `1px solid ${C.border}` : 'none',
                    transition: 'background 150ms',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = C.surfaceHover)}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ padding: '10px 16px', color: C.text, fontWeight: 500 }}>
                    {row.feature}
                  </td>
                  {vendorKeys.map(vk => (
                    <td key={vk} style={{ padding: '10px 16px', textAlign: 'center' }}>
                      {(row as Record<string, unknown>)[vk] ? <Check /> : <Cross />}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── CTA Section ──────────────────────────────────── */}
      <section
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '48px',
          borderTop: `1px solid ${C.border}`,
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 24,
          }}
        >
          <div>
            <h2
              style={{
                fontSize: 24,
                fontWeight: 700,
                color: C.text,
                margin: '0 0 6px',
                fontFamily: font.sans,
              }}
            >
              {t('landing.ctaTitle')}
            </h2>
            <p style={{ fontSize: 14, color: C.muted, margin: 0 }}>
              {t('landing.ctaDescription')}
            </p>
          </div>
          <button
            onClick={() => navigate('/login')}
            style={{
              fontFamily: font.sans,
              fontSize: 14,
              fontWeight: 600,
              color: C.bg,
              background: C.accent,
              border: 'none',
              borderRadius: 6,
              padding: '10px 24px',
              cursor: 'pointer',
              transition: 'opacity 150ms',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={e => (e.currentTarget.style.opacity = '0.85')}
            onMouseLeave={e => (e.currentTarget.style.opacity = '1')}
          >
            {t('landing.getStarted')}
          </button>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────── */}
      <footer
        style={{
          maxWidth: 1200,
          margin: '0 auto',
          padding: '24px 48px 32px',
          borderTop: `1px solid ${C.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <span style={{ fontSize: 12, color: C.dim }}>
          &copy; {new Date().getFullYear()} NightMend. {t('landing.footer')}
        </span>
        <a
          href="https://github.com/LinChuang2008/nightmend"
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 12, color: C.dim, textDecoration: 'none' }}
          onMouseEnter={e => (e.currentTarget.style.color = C.muted)}
          onMouseLeave={e => (e.currentTarget.style.color = C.dim)}
        >
          GitHub
        </a>
      </footer>
    </div>
  );
}
