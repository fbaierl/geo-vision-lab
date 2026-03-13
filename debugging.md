# Debugging Log - 2026-03-13

## Issue: MongoDB Container Fails to Start

### Symptoms
`docker compose up` failed to start the `mongodb` service. The container remained in a `Restarting` or `Exited` state.

### Logs
The `geovision-mongodb` container logs showed the following fatal error:

```json
{"t":{"$date":"2026-03-13T10:08:34.048+00:00"},"s":"F", "c":"CONTROL", "id":20575, "ctx":"main","msg":"Error creating service context","attr":{"error":"Location5579201: Unable to acquire security key[s]"}}
```

Additionally, there was an entry indicating a missing keyfile:
`"errmsg":"Error reading file /data/configdb/keyfile: No such file or directory"`

### Root Cause
The `mongodb/mongodb-atlas-local` image expects a specific security configuration (replica set keyfile) when initializing from existing volumes. If the volumes are partially initialized or the keyfile is missing/corrupted, the service context cannot be created, leading to a fatal crash.

### Resolution
The initial fix involved purging the local MongoDB state. However, persistent issues with "RSGhost" and "Primary" selection timeouts required a more thorough cleanup.

**Commands executed for final resolution:**

1.  Stop all services and remove ALL persistent state (volumes and networks):
    ```bash
    docker compose down -v --remove-orphans
    ```
2.  Aggressively prune unused Docker volumes and networks to ensure a clean slate:
    ```bash
    docker volume prune -f
    ```
    ```bash
    docker network prune -f
    ```
3.  Restart services sequentially (starting MongoDB first to verify initialization):
    ```bash
    docker compose up -d mongodb
    ```
    *Wait for MongoDB to be healthy and verified as Primary via `docker exec geovision-mongodb mongosh --eval "rs.isMaster()"`.*
4.  Start remaining services:
    ```bash
    docker compose up -d
    ```

### Verification
- `docker ps` confirmed all services (`geovision-mongodb`, `geovision-mongo-express`, `geovision-app`) are `Up`.
- MongoDB `rs.isMaster()` confirmed a stable `Writable Primary` elected as `geovision-mongodb:27017`.
- `geovision-mongo-express` logs confirmed: `Mongo Express server listening at http://0.0.0.0:8081`.
- `geovision-app` successfully connected to MongoDB and remained `running`.
