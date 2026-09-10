# Redpanda

Kafka-API-compatible broker in a single binary — no ZooKeeper, no KRaft
bootstrap, no cluster id to format. Runs in `dev-container` mode, which relaxes
the production checks on memory, disk and cores that would otherwise stop it
from starting on a laptop.

## Endpoints

Every API is bound twice. The `internal` listener advertises `redpanda:<port>`
for other containers; the `external` listener advertises `localhost:<port>` so
clients on the host resolve the broker correctly through the port mapping.

| API             | From another container | From the host     |
| --------------- | ---------------------- | ----------------- |
| Kafka           | `redpanda:9092`        | `localhost:19092` |
| Schema Registry | `http://redpanda:8081` | `http://localhost:18081` |
| HTTP proxy      | `http://redpanda:8082` | `http://localhost:18082` |
| Admin / metrics | `http://redpanda:9644` | `http://localhost:19644` |

No auth, no TLS. Use `PLAINTEXT` / `security.protocol=PLAINTEXT`.

The advertised external address is derived from the same variable as the port
mapping, so changing `REDPANDA_KAFKA_PORT` keeps host clients working.

## Everyday commands

```bash
# topics
docker compose exec redpanda rpk topic create my-topic -p 1 -r 1
docker compose exec redpanda rpk topic list
docker compose exec redpanda rpk topic delete my-topic

# produce / consume
docker compose exec redpanda sh -c "echo hello | rpk topic produce my-topic"
docker compose exec redpanda rpk topic consume my-topic -n 1

# cluster
docker compose exec redpanda rpk cluster health
docker compose exec redpanda rpk cluster info
```

Browse the same data at http://localhost:8090 — see
[../kafka-ui/README.md](../kafka-ui/README.md).

## Environment variables

| Variable                        | Default | Purpose |
| ------------------------------- | ------- | ------- |
| `REDPANDA_KAFKA_PORT`           | `19092` | Host port for the Kafka API, and the advertised external address. |
| `REDPANDA_SCHEMA_REGISTRY_PORT` | `18081` | Host port for Schema Registry. |
| `REDPANDA_PROXY_PORT`           | `18082` | Host port for the HTTP proxy. |
| `REDPANDA_ADMIN_PORT`           | `19644` | Host port for the Admin API. |
| `REDPANDA_LOG_LEVEL`            | `info`  | `error`, `warn`, `info`, `debug`, `trace`. |

## Notes

- Data lives in the `redpanda-data` volume and survives restarts. Wipe it with
  `docker compose down -v`.
- Single node, so every topic is `-r 1`. Replication factor 3 requests fail.
- `auto_create_topics_enabled` is `true`, so a client that asks for it
  (`allow.auto.create.topics=true`) gets the topic. `rpk topic produce` never
  asks, so create topics explicitly when working from the CLI.
- The broker reports a built-in Redpanda evaluation license on startup with
  `enterprise_features_enabled: false`. Core Kafka functionality is unaffected.
