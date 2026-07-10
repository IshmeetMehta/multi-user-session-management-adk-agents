# Use highly optimized Nginx Alpine image for static serving
FROM nginx:alpine

# Copy the static web UI file into Nginx's default public directory
COPY index.html /usr/share/nginx/html/index.html

# Expose port 80
EXPOSE 80

# Start Nginx in foreground
CMD ["nginx", "-g", "daemon off;"]
