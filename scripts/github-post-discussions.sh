#!/bin/bash
# Post community content to GitHub Discussions
# Run AFTER enabling Discussions in GitHub Settings
# Prerequisites: gh CLI authenticated

set -euo pipefail

REPO="LinChuang2008/nightmend"

echo "=== Posting GitHub Discussions ==="

# Post 1: Welcome
gh api graphql -f query='
mutation {
  createDiscussion(input: {
    repositoryId: "'$(gh repo view "$REPO" --json id -q .id)'"
    categoryId: "'$(gh api graphql -f query='{ repository(owner: "LinChuang2008", name: "nightmend") { discussionCategories(first: 10) { nodes { id name } } } }' -q '.data.repository.discussionCategories.nodes[] | select(.name == "Announcements") | .id')'"
    title: "Welcome to NightMend Community!"
    body: "'"$(cat docs/community/01-welcome.md)"'"
  }) { discussion { url } }
}' 2>/dev/null && echo "  Posted: Welcome" || echo "  Skipped: Welcome (may already exist or category not found)"

# Post 2: Quick Start Guide
gh api graphql -f query='
mutation {
  createDiscussion(input: {
    repositoryId: "'$(gh repo view "$REPO" --json id -q .id)'"
    categoryId: "'$(gh api graphql -f query='{ repository(owner: "LinChuang2008", name: "nightmend") { discussionCategories(first: 10) { nodes { id name } } } }' -q '.data.repository.discussionCategories.nodes[] | select(.name == "Q&A" or .name == "General") | .id' | head -1)'"
    title: "Quick Start Guide: Your First 30 Minutes with NightMend"
    body: "'"$(cat docs/community/02-quick-start.md)"'"
  }) { discussion { url } }
}' 2>/dev/null && echo "  Posted: Quick Start" || echo "  Skipped: Quick Start"

# Post 3: Architecture Deep Dive
gh api graphql -f query='
mutation {
  createDiscussion(input: {
    repositoryId: "'$(gh repo view "$REPO" --json id -q .id)'"
    categoryId: "'$(gh api graphql -f query='{ repository(owner: "LinChuang2008", name: "nightmend") { discussionCategories(first: 10) { nodes { id name } } } }' -q '.data.repository.discussionCategories.nodes[] | select(.name == "General" or .name == "Show and tell") | .id' | head -1)'"
    title: "Architecture Deep Dive: How NightMend Works Under the Hood"
    body: "'"$(cat docs/community/03-architecture.md)"'"
  }) { discussion { url } }
}' 2>/dev/null && echo "  Posted: Architecture" || echo "  Skipped: Architecture"

# Post 4: 2026 Roadmap
gh api graphql -f query='
mutation {
  createDiscussion(input: {
    repositoryId: "'$(gh repo view "$REPO" --json id -q .id)'"
    categoryId: "'$(gh api graphql -f query='{ repository(owner: "LinChuang2008", name: "nightmend") { discussionCategories(first: 10) { nodes { id name } } } }' -q '.data.repository.discussionCategories.nodes[] | select(.name == "Announcements") | .id')'"
    title: "NightMend 2026 Roadmap — Help Us Prioritize"
    body: "'"$(cat docs/community/04-roadmap-2026.md)"'"
  }) { discussion { url } }
}' 2>/dev/null && echo "  Posted: Roadmap" || echo "  Skipped: Roadmap"

# Post 5: How AI Powers NightMend
gh api graphql -f query='
mutation {
  createDiscussion(input: {
    repositoryId: "'$(gh repo view "$REPO" --json id -q .id)'"
    categoryId: "'$(gh api graphql -f query='{ repository(owner: "LinChuang2008", name: "nightmend") { discussionCategories(first: 10) { nodes { id name } } } }' -q '.data.repository.discussionCategories.nodes[] | select(.name == "General" or .name == "Show and tell") | .id' | head -1)'"
    title: "How AI Powers NightMend: From Detection to Auto-Remediation"
    body: "'"$(cat docs/community/05-ai-powers-nightmend.md)"'"
  }) { discussion { url } }
}' 2>/dev/null && echo "  Posted: AI Powers" || echo "  Skipped: AI Powers"

echo ""
echo "=== Discussions Posted ==="
echo "View at: https://github.com/$REPO/discussions"
