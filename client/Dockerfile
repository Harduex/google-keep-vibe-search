# Stage 1: Build the React application
FROM node:18-alpine as build

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json ./
RUN npm ci

# Copy the application code
COPY . .

# Build the app
RUN npm run build

# Stage 2: Serve the build with Nginx
FROM nginx:alpine

# Copy the production-ready build
COPY --from=build /app/dist /usr/share/nginx/html

# Copy a custom nginx config to properly handle React routing
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 for the web server
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
