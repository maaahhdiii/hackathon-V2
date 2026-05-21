FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY status.html /usr/share/nginx/html/status.html
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
