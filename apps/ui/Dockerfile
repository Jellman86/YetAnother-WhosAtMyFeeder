# Stage 1: Build
FROM node:20 as builder

WORKDIR /app

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

# Run build with full output
RUN npm run build 2>&1

# Stage 2: Serve
FROM nginx:alpine

# Install curl for health checks
RUN apk add --no-cache curl

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]