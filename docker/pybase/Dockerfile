FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends libaio1 unzip curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Oracle Instant Client Basic Lite (modo thick de python-oracledb; necesario para Oracle 11g).
# Plan B si falla contra 11.2 (DPI-1050 / ORA-28040): cambiar IC_DIR/IC_FILE/IC_FOLDER a 12.2.
ARG IC_DIR=1923000
ARG IC_FILE=instantclient-basiclite-linux.x64-19.23.0.0.0dbru.zip
ARG IC_FOLDER=instantclient_19_23
RUN curl -fsSL -o /tmp/ic.zip "https://download.oracle.com/otn_software/linux/instantclient/${IC_DIR}/${IC_FILE}" \
 && mkdir -p /opt/oracle \
 && unzip -q /tmp/ic.zip -d /opt/oracle \
 && rm /tmp/ic.zip \
 && echo "/opt/oracle/${IC_FOLDER}" > /etc/ld.so.conf.d/oracle-ic.conf \
 && ldconfig

# Instala las dependencias declaradas en server/pyproject.toml (extras "dev").
# En ejecucion, PYTHONPATH=/work/server hace que mande el codigo montado, no esta copia.
COPY server /tmp/server
RUN pip install --no-cache-dir "/tmp/server[dev]" && rm -rf /tmp/server

WORKDIR /work
