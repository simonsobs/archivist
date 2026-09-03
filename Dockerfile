FROM python:3.13

COPY . archivist
RUN pip install --no-cache-dir --upgrade ./archivist

ENV ARCHIVIST_CONFIG_PATH=/etc/archivist/config.json
ENTRYPOINT ["archivist", "-c", "/etc/archivist/config.json"]
CMD ["start-server"]
