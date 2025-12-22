# Stage 1: Build
# Use Debian-based slim image instead of Alpine to avoid musl/glibc compatibility issues
# with native binaries (like esbuild) which often cause "exit code 1" failures.
FROM node:20-slim as builder

WORKDIR /app

# Increase memory limit for build to avoid OOM on smaller instances
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Install basics
RUN apt-get update && apt-get install -y python3 make g++

# Copy package files
# We only copy package.json to ensure we get fresh, architecture-correct binaries
COPY package.json ./

# Clean install
RUN npm install

# Copy source files
COPY . .

# Run build with verbose logging to help debug if it still fails
RUN npm run build

# Stage 2: Serve
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]