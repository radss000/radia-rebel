FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
COPY apps/api/package.json apps/api/package.json
COPY apps/web/package.json apps/web/package.json
RUN npm install --omit=dev -w @radia-proof/api
COPY apps/api apps/api
COPY data data
EXPOSE 5001
CMD ["npm", "run", "start", "-w", "@radia-proof/api"]
