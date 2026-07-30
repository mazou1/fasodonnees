FROM node:20-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

FROM nginx:alpine
# Gabarit substitué au démarrage par l'image officielle. Le filtre limite la
# substitution aux variables FDP_ : sans lui, envsubst viderait $host, $uri et
# les autres variables de nginx.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER=FDP_
# Valeurs de la pile autonome. La cohabitation avec une autre pile les surcharge
# (noms de services différents, autre instance Garage) — cf. deploy/README.md.
ENV FDP_API_UPSTREAM=api:8000 \
    FDP_GARAGE_UPSTREAM=garage:3902 \
    FDP_GARAGE_BUCKET_HOST=faso-archives.web.garage
COPY --from=build /src/dist /usr/share/nginx/html
