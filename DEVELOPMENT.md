# Development Workflow

This document explains the development workflow for YA-WAMF.

## Branch Strategy

### `main` Branch (Production)
- **Purpose:** Stable, production-ready code
- **Image Tags:** `ghcr.io/jellman86/wamf-backend:latest` and `wamf-frontend:latest`
- **Deployment:** Use `docker-compose.prod.yml`
- **Protection:** Only merge tested, stable code from `dev`

### `dev` Branch (Development)
- **Purpose:** Active development, testing new features and fixes
- **Image Tags:** `ghcr.io/jellman86/wamf-backend:dev` and `wamf-frontend:dev`
- **Deployment:** Use `docker-compose.dev.yml`
- **Workflow:** All new features and fixes start here

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
docker compose -f docker-compose.dev.yml pull
docker compose -f docker-compose.dev.yml up -d
```

### 4. Promoting to Production

Once features are tested and stable on `dev`:

```bash
# Switch to main
git checkout main

# Merge dev into main
git merge dev

# Push to main
git push origin main

# GitHub Actions will automatically build latest images
# Deploy production:
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Quick Reference

| Environment | Branch | Image Tag | Docker Compose File |
|-------------|--------|-----------|---------------------|
| Production  | `main` | `:latest` | `docker-compose.prod.yml` |
| Development | `dev`  | `:dev`    | `docker-compose.dev.yml` |
| Local Build | any    | built locally | `docker-compose.yml` |

## GitHub Actions

The workflow automatically builds and pushes Docker images:

- **Trigger:** Push to `main` or `dev` branch
- **Backend:** `ghcr.io/jellman86/wamf-backend:{tag}`
- **Frontend:** `ghcr.io/jellman86/wamf-frontend:{tag}`
- **Tag Logic:**
  - `main` → `:latest`
  - `dev` → `:dev`
  - Both get additional SHA tag: `:{commit-sha}`

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
   docker compose -f docker-compose.dev.yml pull

   # Production
   docker compose -f docker-compose.prod.yml pull
   ```
