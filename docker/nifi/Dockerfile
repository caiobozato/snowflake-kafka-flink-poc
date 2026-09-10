# Apache NiFi, standing in for a Snowflake Openflow runtime.
#
# Openflow runtimes are managed Apache NiFi, so this is the same engine. What it
# is NOT is the Openflow "Snowflake to Kafka" connector, which is a proprietary
# flow definition from the Snowflake connector gallery — see README.md.
FROM apache/nifi:2.11.0

# Driver version is pinned so the flow is reproducible.
ARG SNOWFLAKE_JDBC_VERSION=4.3.4

USER root

RUN mkdir -p /opt/nifi/drivers \
    && curl -fsSL -o /opt/nifi/drivers/snowflake-jdbc.jar \
        "https://repo1.maven.org/maven2/net/snowflake/snowflake-jdbc/${SNOWFLAKE_JDBC_VERSION}/snowflake-jdbc-${SNOWFLAKE_JDBC_VERSION}.jar" \
    && chown -R nifi:nifi /opt/nifi/drivers

# The Snowflake driver parses Arrow result sets, which requires java.nio to be
# opened on JDK 17+. Without this, every query fails with
# ExceptionInInitializerError in Arrow's UnsafeAllocationManager.
RUN printf '\njava.arg.addOpensJavaNio=--add-opens=java.base/java.nio=ALL-UNNAMED\n' \
    >> /opt/nifi/nifi-current/conf/bootstrap.conf

COPY bin/ /opt/nifi/bin-poc/

# Pristine copy of conf, restored on every boot by the entrypoint. See the
# comment in bin/entrypoint.sh for why this is necessary.
RUN cp -a /opt/nifi/nifi-current/conf /opt/nifi/conf-template \
    && chown -R nifi:nifi /opt/nifi/conf-template /opt/nifi/bin-poc \
    && chmod +x /opt/nifi/bin-poc/*.sh

USER nifi

ENTRYPOINT ["/opt/nifi/bin-poc/entrypoint.sh"]
