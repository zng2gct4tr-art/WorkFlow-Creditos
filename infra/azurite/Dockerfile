FROM node:22-alpine
WORKDIR /opt/azurite
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=environment_ca \
    if [ -f /run/secrets/environment_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/environment_ca; fi; \
    npm ci --no-audit --no-fund --fetch-retries=1 --fetch-timeout=30000
RUN mkdir -p /data && chown node:node /data && ln -s /opt/azurite/node_modules/.bin/azurite-blob /usr/local/bin/azurite-blob
USER node
EXPOSE 10000
CMD ["azurite-blob", "--blobHost", "0.0.0.0", "--disableProductStyleUrl", "--location", "/data"]
