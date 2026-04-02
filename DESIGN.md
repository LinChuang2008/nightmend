# Design System — NightMend

## Product Context
- **What this is:** AI-powered infrastructure monitoring platform that doesn't just detect issues, but automatically diagnoses and fixes them
- **Who it's for:** DevOps/SRE engineers who manage production infrastructure and are tired of alert fatigue
- **Space/industry:** Monitoring & Observability (peers: Grafana, Datadog, PagerDuty, Uptime Kuma)
- **Project type:** App UI (dashboard + admin) + Marketing Landing page

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian
- **Decoration level:** Minimal — typography and layout do all the visual work, zero decorative elements
- **Mood:** Professional, trustworthy, competent. This is a tool that SRE engineers trust with their production systems at 3am. It should feel like a precision instrument, not a toy.
- **Anti-patterns:** No purple/pink gradients, no decorative blobs/circles, no 3-column icon grids, no centered-everything layouts, no generic SaaS template patterns

## Typography
- **Display/Hero:** Geist 700 — clean geometric sans from Vercel, modern without being trendy
- **Body:** Geist 400/500 — excellent readability at small sizes, wide language support
- **UI/Labels:** Geist 600 — same family for consistency, semi-bold for hierarchy
- **Data/Tables:** Geist Mono 400 — tabular-nums support, aligns numbers perfectly in columns
- **Code:** Geist Mono 400 — consistent with data font, no context switch
- **Loading:** Google Fonts CDN `https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500`
- **Scale:** 11px (label) / 13px (body) / 14px (ui) / 18px (h3) / 24px (h2) / 48px (hero)

## Color
- **Approach:** Restrained — one accent color + cool neutrals. Color is rare and meaningful.
- **Background:** #0a0a0f — near-black, reduces eye strain for long sessions
- **Surface:** #141419 — cards, panels, sidebars
- **Surface Hover:** #1a1a21 — interactive surface state
- **Border:** #27272a — subtle separation
- **Text Primary:** #e4e4e7 — high contrast on dark bg
- **Text Muted:** #71717a — secondary information
- **Text Dim:** #52525b — tertiary, labels, timestamps
- **Accent:** #10B981 (emerald green) — represents "healthy / active / positive action"
- **Accent Dim:** #065f46 — accent backgrounds, badges
- **Semantic:**
  - Success: #10B981 (same as accent — health IS the brand)
  - Warning: #f59e0b (amber)
  - Error: #ef4444 (red)
  - Info: #3b82f6 (blue)
- **Dark mode:** This IS the primary theme. No light mode planned. All surfaces dark.

## Spacing
- **Base unit:** 4px
- **Density:** Compact — monitoring tools need information density
- **Scale:** 2xs(2px) xs(4px) sm(8px) md(16px) lg(24px) xl(32px) 2xl(48px) 3xl(64px)

## Layout
- **Approach:** Hybrid — strict grid for App UI, editorial for Landing page
- **Grid:** App uses sidebar (200px fixed) + fluid main content
- **Max content width:** 1200px (Landing), fluid (App)
- **Border radius:** sm:4px, md:6px, lg:8px — intentionally small, not bubbly

## Motion
- **Approach:** Minimal-functional — only transitions that aid comprehension
- **Easing:** enter(ease-out) exit(ease-in) move(ease-in-out)
- **Duration:** micro(50ms) short(150ms) medium(250ms)
- **Rule:** No decorative animations. No entrance animations on page load. Hover states get 150ms transitions. Loading states use subtle pulse, not spinners.

## Component Patterns
- **Buttons:** Primary (emerald bg), Secondary (transparent + border), Ghost (no border), Danger (red tint)
- **Cards:** Surface bg + border, no shadow. Cards earn their existence — don't use cards for decoration.
- **Tables:** Dense, monospace for data columns, muted row separators, hover highlight
- **Inputs:** Surface bg + border, accent border on focus
- **Severity badges:** Tinted background + matching text color (critical=red, warning=amber, info=blue)
- **Navigation:** Left sidebar, grouped sections, active item uses accent color + right border

## Landing Page Rules
- **Full dark theme** — same as App, zero style transition from Landing to Login to Dashboard
- **No decoration:** No gradients, no floating shapes, no background patterns
- **Hero:** Left-aligned, overline (monospace accent) + headline + description + CTA buttons
- **Features:** Data-driven blocks with big numbers (Geist Mono 700), not icon-in-circle grids
- **Copy:** Product language, not marketing speak. "47 秒平均修复时间" beats "让你的运维更高效"

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-02 | Initial design system created | Created by /design-consultation based on competitive research (Grafana, Datadog, Uptime Kuma) and product positioning as professional DevOps tool |
| 2026-04-02 | Full dark theme, including Landing | Eliminates style transition between Landing/Login/App. DevOps engineers prefer dark. Professional positioning. |
| 2026-04-02 | Emerald green (#10B981) as accent | "Health" is the core concept of a monitoring tool. Green = healthy = the brand. |
| 2026-04-02 | Geist + Geist Mono typography | Modern, professional, excellent tabular-nums. From Vercel, actively maintained. |
| 2026-04-02 | No decorative elements anywhere | Monitoring tools earn trust through competence, not decoration. Every pixel serves a function. |
