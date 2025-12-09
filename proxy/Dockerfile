FROM nginx:1.29

# Only used for generating self-signed certificates
RUN apt-get update && apt-get install -y openssl

VOLUME /var/log/nginx
VOLUME /run/proxy

COPY bin /usr/local/bin
COPY ssl /usr/local/share/ssl

ENTRYPOINT ["/usr/local/bin/packit-proxy"]
