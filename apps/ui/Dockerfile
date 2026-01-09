# Stage 1: Build
FROM node:20 as builder

WORKDIR /app

# Version info passed at build time
ARG GIT_HASH=unknown
ARG APP_VERSION_BASE=2.2.0
ENV GIT_HASH=${GIT_HASH}
ENV APP_VERSION_BASE=${APP_VERSION_BASE}

# Copy package files
COPY package.json package-lock.json ./

# Install dependencies
RUN npm install --legacy-peer-deps

# Copy source files
COPY . .

# Show what we have
RUN echo "=== Files in /app ===" && ls -la
RUN echo "=== Files in /app/src ===" && ls -la src/
RUN echo "=== Node version ===" && node --version
RUN echo "=== NPM version ===" && npm --version
RUN echo "=== Git hash ===" && echo $GIT_HASH

# Run build with full output
RUN npm run build 2>&1

# Stage 2: Serve
FROM nginx:alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Create non-root user (UID 1000 to match backend, or use 568 for TrueNAS)
RUN addgroup -g 1000 appuser && \
    adduser -D -u 1000 -G appuser appuser

# Set up permissions for nginx to run as non-root
RUN chown -R appuser:appuser /usr/share/nginx/html /var/cache/nginx /var/run /var/log/nginx && \
    chmod -R 755 /usr/share/nginx/html && \
    touch /var/run/nginx.pid && \
    chown appuser:appuser /var/run/nginx.pid

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

USER appuser

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]