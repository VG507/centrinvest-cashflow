# Stage 1: Build production assets
FROM node:22-alpine AS builder

WORKDIR /app

# Copy root contracts for TypeScript verification
COPY contracts /app/contracts

# Install dependencies
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source and compile
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Nginx Server
FROM nginx:alpine

COPY frontend/deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
