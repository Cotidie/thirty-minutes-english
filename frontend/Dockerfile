FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Development: Vite dev server with the source bind-mounted (see compose.dev.yaml).
FROM deps AS dev
COPY . .
ENV VITE_API_PROXY=http://backend:8765
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "80"]

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
