# Apache Flink with the SQL Kafka connector.
#
# The Kafka connector ships outside the Flink release and is versioned against
# it, so both are pinned: connector 5.0.0-2.2 is the build for Flink 2.2.
FROM flink:2.2.1-java17

ARG KAFKA_CONNECTOR_VERSION=5.0.0-2.2

USER root

RUN curl -fsSL -o "${FLINK_HOME}/lib/flink-sql-connector-kafka.jar" \
        "https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/${KAFKA_CONNECTOR_VERSION}/flink-sql-connector-kafka-${KAFKA_CONNECTOR_VERSION}.jar" \
    && chown flink:flink "${FLINK_HOME}/lib/flink-sql-connector-kafka.jar"

COPY bin/ /opt/flink/bin-poc/
COPY sql/ /opt/flink/sql/

RUN chmod +x /opt/flink/bin-poc/*.sh \
    && chown -R flink:flink /opt/flink/bin-poc /opt/flink/sql

USER flink
