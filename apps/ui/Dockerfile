# Stage 1: Build
# Use Debian-based slim image instead of Alpine to avoid musl/glibc compatibility issues
FROM node:20-slim as builder

WORKDIR /app

# Increase memory limit for build to avoid OOM on smaller instances
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Install basics
RUN apt-get update && apt-get install -y python3 make g++

# Debug: Check environment
RUN node -v && npm -v

# Copy package files
COPY package.json ./

# Debug: List files
RUN ls -la

# Clean install with verbose output to see dependency issues
RUN npm install --verbose

# Copy source files
COPY . .

# Debug: List source files to ensure everything was copied
RUN ls -laR src/

# Run build with debug logging for Vite
# passing --logLevel debug to vite via npm run
RUN npm run build -- --logLevel debug

# Stage 2: Serve
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]