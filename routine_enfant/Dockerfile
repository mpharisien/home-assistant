FROM node:18-alpine
WORKDIR /app
COPY app/package.json .
RUN npm install
COPY app/ .
CMD ["node", "server.js"]
