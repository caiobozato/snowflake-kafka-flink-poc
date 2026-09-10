# Web SQL console for the local Snowflake service.
#
# Deliberately small: it drives snowflake-connector-python, the one client
# fakesnow implements the protocol for, so the UI cannot drift from what
# application code can do.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SNOWFLAKE_UI_HOST=0.0.0.0 \
    SNOWFLAKE_UI_PORT=8086

WORKDIR /opt/snowflake-ui

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app/ ./app/

RUN useradd --create-home --uid 10002 snowflakeui \
    && chown -R snowflakeui:snowflakeui /opt/snowflake-ui
USER snowflakeui

EXPOSE 8086

HEALTHCHECK --interval=10s --timeout=10s --start-period=20s --retries=10 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8086/healthz').read()"]

WORKDIR /opt/snowflake-ui/app
ENTRYPOINT ["python", "main.py"]
