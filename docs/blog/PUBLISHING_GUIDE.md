# Blog Publishing Guide

All 8 articles are ready in `docs/blog/`. This guide covers how to publish them to external platforms.

## Publishing Schedule

Stagger releases across 2 weeks for maximum reach:

| Day | Article | Platforms |
|-----|---------|-----------|
| Week 1 Mon | alert-fatigue-zh.md | 掘金, 知乎 |
| Week 1 Wed | alert-fatigue-problem-en.md | Dev.to, Hashnode |
| Week 1 Fri | ai-noise-reduction-zh.md | 掘金, 知乎, V2EX |
| Week 2 Mon | auto-remediation-runbooks-en.md | Dev.to, Medium |
| Week 2 Tue | opensource-monitoring-comparison-zh.md | 掘金, 知乎, V2EX |
| Week 2 Wed | open-source-monitoring-landscape-en.md | Dev.to, Hashnode |
| Week 2 Thu | mcp-ai-ops-zh.md | 掘金, 知乎 |
| Week 2 Fri | mcp-protocol-ai-native-ops-en.md | Dev.to, Medium, Hashnode |

## Platform-Specific Instructions

### Dev.to
1. Go to https://dev.to/enter
2. Paste the article content (markdown supported natively)
3. Add front matter tags at top:
   ```
   ---
   title: [article title]
   published: true
   tags: monitoring, ai, devops, opensource
   canonical_url: https://github.com/LinChuang2008/nightmend/blob/main/docs/blog/[filename]
   cover_image: [optional]
   ---
   ```
4. Add footer: `---\n*[NightMend](https://github.com/LinChuang2008/nightmend) is an open-source AI-powered monitoring platform. Star us on GitHub!*`
5. Publish

### Hashnode
1. Create new article at your Hashnode blog
2. Paste markdown content
3. Tags: `monitoring`, `ai`, `devops`, `open-source`
4. Set canonical URL to GitHub blog file
5. Add footer CTA linking to GitHub repo

### Medium
1. Import from markdown or paste content
2. Add tags: Monitoring, AI, DevOps, Open Source, AIOps
3. Add footer CTA with GitHub link
4. Submit to publications: "Better Programming", "ITNEXT", "Towards Data Science"

### 掘金 (Juejin)
1. Go to https://juejin.cn/editor/drafts/new
2. Paste markdown content (supported natively)
3. Category: 后端 or 运维
4. Tags: 运维, AI, 监控, DevOps, 开源
5. Add footer:
   ```
   ---
   > NightMend 是全球首个内置 AI 自动修复的开源监控平台。
   > GitHub: https://github.com/LinChuang2008/nightmend
   > 在线演示: https://demo.lchuangnet.com
   ```

### 知乎 (Zhihu)
1. Go to https://zhuanlan.zhihu.com/write
2. Paste content (convert markdown to rich text as needed)
3. Add topic tags: 运维, DevOps, 人工智能, 开源项目, 监控系统
4. Add footer CTA with GitHub and demo links
5. Also answer related questions linking to the article:
   - "有哪些好用的开源监控工具？"
   - "AIOps 有什么实际应用？"
   - "运维告警太多怎么办？"

### V2EX
1. Go to https://v2ex.com/new
2. Node: DevOps or 分享发现
3. Post a condensed version (V2EX prefers shorter posts)
4. Include key points + link to full article on GitHub
5. Keep promotional tone minimal — V2EX community dislikes overt marketing

## Tracking

After publishing, record links here:

| Article | Platform | URL | Date |
|---------|----------|-----|------|
| | | | |

## Cross-Linking Strategy

- Each article should link to at least 1 other article in the series
- All articles include GitHub repo link and demo link
- Chinese articles link to the 中文README (README.zh-CN.md)
- English articles link to the main README
