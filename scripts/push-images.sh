#!/bin/bash
# NightMend Docker Image Build & Push Script
# Push to GitHub Container Registry (ghcr.io)
#
# Prerequisites:
#   1. Docker installed and running
#   2. GitHub PAT with write:packages scope
#      echo $GITHUB_TOKEN | docker login ghcr.io -u LinChuang2008 --password-stdin
#
# Usage:
#   ./scripts/push-images.sh [tag]
#   ./scripts/push-images.sh v1.0.0

set -euo pipefail

REPO="ghcr.io/linchuang2008"
TAG="${1:-latest}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== NightMend Image Build & Push ==="
echo "Registry: $REPO"
echo "Tag: $TAG"
echo ""

# Check docker login
if ! docker manifest inspect "$REPO/nightmend-backend:test" >/dev/null 2>&1; then
  echo "⚠️  Make sure you're logged in to ghcr.io:"
  echo '   echo $GITHUB_TOKEN | docker login ghcr.io -u LinChuang2008 --password-stdin'
  echo ""
fi

# Build backend
echo "🔨 Building backend..."
docker build --no-cache -t "$REPO/nightmend-backend:$TAG" "$ROOT/backend"
echo "✅ Backend built"

# Build frontend
echo "🔨 Building frontend..."
docker build --no-cache -t "$REPO/nightmend-frontend:$TAG" "$ROOT/frontend"
echo "✅ Frontend built"

# Push
echo "🚀 Pushing backend..."
docker push "$REPO/nightmend-backend:$TAG"
echo "✅ Backend pushed"

echo "🚀 Pushing frontend..."
docker push "$REPO/nightmend-frontend:$TAG"
echo "✅ Frontend pushed"

# Tag as latest if version tag
if [ "$TAG" != "latest" ]; then
  echo "🏷️  Tagging as latest..."
  docker tag "$REPO/nightmend-backend:$TAG" "$REPO/nightmend-backend:latest"
  docker tag "$REPO/nightmend-frontend:$TAG" "$REPO/nightmend-frontend:latest"
  docker push "$REPO/nightmend-backend:latest"
  docker push "$REPO/nightmend-frontend:latest"
  echo "✅ Latest tags pushed"
fi

echo ""
echo "=== Done! ==="
echo "Images available:"
echo "  $REPO/nightmend-backend:$TAG"
echo "  $REPO/nightmend-frontend:$TAG"
echo ""
echo "Users can now run:"
echo "  curl -fsSL https://raw.githubusercontent.com/LinChuang2008/nightmend/main/install.sh | bash"
