# Local, Snowflake-compatible SQL endpoint for the POC.
#
# Snowflake has no official container image. This image runs `fakesnow`, which
# serves the same HTTP wire protocol that snowflake-connector-python (and the
# JDBC/ODBC drivers' REST endpoints) speak, and executes the SQL on DuckDB.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FAKESNOW_HOST=0.0.0.0 \
    FAKESNOW_PORT=8085 \
    FAKESNOW_INIT_DIR=/opt/snowflake/init \
    FAKESNOW_LOG_LEVEL=info

WORKDIR /opt/snowflake

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY bin/ ./bin/
COPY init/ ./init/

# Optional persistence target (see FAKESNOW_DB_PATH); unused when in-memory.
RUN useradd --create-home --uid 10001 snowflake \
    && mkdir -p /var/lib/snowflake \
    && chown -R snowflake:snowflake /opt/snowflake /var/lib/snowflake

USER snowflake

EXPOSE 8085

HEALTHCHECK --interval=10s --timeout=10s --start-period=15s --retries=10 \
    CMD ["python", "/opt/snowflake/bin/healthcheck.py"]

ENTRYPOINT ["python", "/opt/snowflake/bin/serve.py"]
