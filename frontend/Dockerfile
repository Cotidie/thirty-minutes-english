FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
# Every release bumps the version in these two files, so this step reruns; the cache keeps it off the network.
RUN --mount=type=cache,target=/root/.npm npm ci

FROM deps AS build
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
