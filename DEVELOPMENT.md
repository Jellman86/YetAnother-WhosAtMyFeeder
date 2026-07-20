# Development Workflow

This document explains the development workflow for YA-WAMF.

## Branch Strategy

### `main` Branch (Production)
- **Purpose:** Stable, production-ready code
- **Primary Image Tags:** full `:latest` / `:vX.Y.Z`, with optional `-cpu`, `-intel`, and `-cuda` variants
- **Deployment:** Use `docker-compose.monolith.yml`
- **Protection:** Only merge tested, stable code from `dev`

### `dev` Branch (Development)
- **Purpose:** Active development, testing new features and fixes
- **Primary Image Tags:** full `ghcr.io/jellman86/yawamf-monalithic:dev`, with optional `dev-cpu`, `dev-intel`, and `dev-cuda` variants
- **Deployment:** Use `docker-compose.monolith.yml` with `YAWAMF_MONALITHIC_TAG=dev`
- **Workflow:** All new features and fixes start here

The older split images (`wamf-backend` and `wamf-frontend`) are still built for
legacy v2.x installs, but new development and release validation should use the
monolithic image first. Unsuffixed tags always select the full compatibility
runtime. See [Hardware Acceleration](docs/setup/hardware-acceleration.md) for the
provider-family contract and safe switching procedure.

## Workflow Steps

### 1. Starting New Work

```bash
# Switch to dev branch
git checkout dev

# Pull latest changes
git pull origin dev

# Create a feature branch (optional, for complex features)
git checkout -b feature/my-new-feature
```

### 2. Development

Make your changes, commit frequently:

```bash
git add .
git commit -m "feat: description of changes"
```

### 3. Testing

```bash
# Push to dev branch
git checkout dev
git merge feature/my-new-feature  # if using feature branch
git push origin dev

# GitHub Actions will automatically build dev images
# Wait for the build to complete, then test:
YAWAMF_MONALITHIC_TAG=dev docker compose -f docker-compose.monolith.yml pull
YAWAMF_MONALITHIC_TAG=dev docker compose -f docker-compose.monolith.yml up -d
```

### 4. Promoting to Production

Once features are tested and stable on `dev`:

```bash
# Switch to main
git checkout main

# Merge dev into main
git merge dev

# Push main branch
git push origin main

# Ensure `VERSION` and `CHANGELOG.md` are correct, then create and push a release tag
# (the tag should match VERSION; this triggers the production image build)
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z

# Deploy production:
YAWAMF_MONALITHIC_TAG=latest docker compose -f docker-compose.monolith.yml pull
YAWAMF_MONALITHIC_TAG=latest docker compose -f docker-compose.monolith.yml up -d
```

## Quick Reference

| Environment | Branch | Image Tag | Docker Compose File |
|-------------|--------|-----------|---------------------|
| Production  | `main` | full `:latest` / `:vX.Y.Z`, or matching `-cpu` / `-intel` / `-cuda` | `docker-compose.monolith.yml` |
| Development | `dev`  | full `:dev`, or `:dev-cpu` / `:dev-intel` / `:dev-cuda` | `docker-compose.monolith.yml` |
| Local Build | any    | built locally | `docker-compose.yml` or service-specific Dockerfiles |
| Legacy Split | v2.x installs | `wamf-backend:*` + `wamf-frontend:*` | `docker-compose.dev.yml` / `docker-compose.prod.yml` |

## GitHub Actions

The workflow automatically builds and pushes Docker images:

- **Trigger:** Push to `dev` or `main`, and release tags (`v*`)
- **Primary monolith:** full, CPU, Intel, and CUDA images from one Dockerfile and commit
- **Raspberry Pi monolith:** `ghcr.io/jellman86/yawamf-monalithic-rpi:{tag}` when that build path succeeds
- **Legacy split images:** `ghcr.io/jellman86/wamf-backend:{tag}` and `ghcr.io/jellman86/wamf-frontend:{tag}`
- **Tag Logic:**
  - unsuffixed `dev`, `main`, `latest`, release, and SHA tags → full image
  - matching `-cpu`, `-intel`, and `-cuda` suffixes → provider-family images
  - builds publish SHA candidates first; channel/release tags move only after every flavor starts and the shared-volume full → CPU → full switch contract passes

## Manual Build (Local Development)

For rapid iteration without pushing to GitHub:

```bash
# Use the default docker-compose.yml which builds locally
docker compose up -d --build
```

## Tips

1. **Keep dev in sync with main:** Regularly merge main into dev to avoid conflicts
   ```bash
   git checkout dev
   git merge main
   ```

2. **Hotfixes:** For urgent production fixes:
   ```bash
   git checkout main
   git checkout -b hotfix/issue-name
   # Fix, test, merge to main, then merge main to dev
   ```

3. **Check build status:** Visit your GitHub repository → Actions tab

4. **Pull latest images:**
   ```bash
   # Development
   YAWAMF_MONALITHIC_TAG=dev docker compose -f docker-compose.monolith.yml pull

   # Production
   YAWAMF_MONALITHIC_TAG=latest docker compose -f docker-compose.monolith.yml pull
   ```
