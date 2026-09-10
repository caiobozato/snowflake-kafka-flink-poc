# Container definitions

One directory per container. Each directory owns everything that container
needs, so services stay independently readable and reviewable:

```
docker/<service>/
  compose.yaml       service (and any volumes/networks it owns)
  Dockerfile         only if the service needs a custom image
  bin/               entrypoint and helper scripts
  init/, config/     assets baked into the image or mounted
  README.md          how to use it, and anything surprising about it
```

## Adding a service

1. Create `docker/<service>/` with a `compose.yaml` holding a single service.
   Paths inside it are resolved relative to that directory, so use
   `build: {context: .}` rather than reaching back up the tree. A fragment may
   hold a second, tightly-coupled one-shot container when a service needs
   provisioning it cannot do itself — `docker/nifi/` pairs the runtime with the
   job that builds its flow.
2. Register it in the root `docker-compose.yml`:

   ```yaml
   include:
     - docker/snowflake/compose.yaml
     - docker/<service>/compose.yaml
   ```

3. Expose tunables as `${VAR:-default}` and document them in `.env.example`.
4. Give the service a healthcheck, and depend on it with
   `depends_on: {<service>: {condition: service_healthy}}` so start-up ordering
   is enforced rather than assumed.
5. Verify with `docker compose config` before `docker compose up`.
