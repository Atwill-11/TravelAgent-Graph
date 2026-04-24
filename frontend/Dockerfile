FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=
ARG VITE_AMAP_WEB_JS_KEY=

ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_AMAP_WEB_JS_KEY=${VITE_AMAP_WEB_JS_KEY}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]