FROM node:18-alpine
RUN apk add --no-cache bash
WORKDIR /app
COPY app/package.json .
RUN npm install
COPY app/ .
COPY run.sh /run.sh
RUN chmod +x /run.sh
CMD ["/bin/bash", "/run.sh"]
