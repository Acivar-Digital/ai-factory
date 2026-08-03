# Shared Dolt SQL Server Setup for Beads Concurrency

## Purpose

This guide converts `bd` (beads) from **embedded Dolt mode** (file-lock based, breaks under concurrent subagent writes) to **shared Dolt SQL server mode** (MySQL protocol, handles concurrent connections with transaction isolation). One server serves all repos; each repo gets its own database.

## Prerequisites

- Linux machine with `tmux`, `curl`, `tar`
- User: `yapilwsl`
- Home: `/home/yapilwsl`
- Existing `BEAMS_DOLT_PASSWORD=ZysxTSZtlLL` in `~/.bashrc`
- Existing `dolt` binary at `~/.local/bin/dolt` (v2.2.3+)

If dolt is missing, install:
```bash
curl -L https://github.com/dolthub/dolt/releases/latest/download/dolt-linux-amd64.tar.gz -o /tmp/dolt.tar.gz
tar -xzf /tmp/dolt.tar.gz -C /tmp/
cp /tmp/dolt-linux-amd64/bin/dolt ~/.local/bin/dolt
chmod +x ~/.local/bin/dolt
rm -rf /tmp/dolt-linux-amd64 /tmp/dolt.tar.gz
dolt version  # verify
```

## Step 1: Create Server Data Directory

```bash
mkdir -p ~/arthityap/infra/dolt-server
```

## Step 2: Create Management Script

Create `~/arthityap/dolt.sh`:

```bash
#!/usr/bin/env bash
# Manages shared Dolt SQL server via tmux

DATA_DIR="$HOME/arthityap/infra/dolt-server"
LOG_FILE="$DATA_DIR/server.log"
TMUX_SESSION="dolt-server"
PORT=15432

case "${1:-start}" in
  start)
    if tmux has-session -t "$TMUX_SESSION" 2>/dev/null; then
      echo "Dolt server already running (tmux: $TMUX_SESSION, port: $PORT)"
    else
      mkdir -p "$DATA_DIR"
      tmux new-session -d -s "$TMUX_SESSION" \
        "dolt sql-server --data-dir '$DATA_DIR' --host=127.0.0.1 --port=$PORT --allow-cleartext-passwords=true --loglevel=warning 2>&1 | tee -a '$LOG_FILE'"
      sleep 2
      tmux has-session -t "$TMUX_SESSION" 2>/dev/null && echo "✓ Started" || (echo "✗ Failed"; exit 1)
    fi
    ;;
  stop)
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null && echo "✓ Stopped" || echo "Not running"
    ;;
  restart)
    "$0" stop 2>/dev/null; sleep 1; "$0" start
    ;;
  status)
    tmux has-session -t "$TMUX_SESSION" 2>/dev/null && echo "✓ Running" || echo "✗ Not running"
    ;;
  *) echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
```

```bash
chmod +x ~/arthityap/dolt.sh
```

## Step 3: Start Server and Set Root Password

```bash
# Ensure BEAMS_DOLT_PASSWORD is exported (it's in ~/.bashrc)
export BEAMS_DOLT_PASSWORD=ZysxTSZtlLL

# Start server
~/arthityap/dolt.sh start
sleep 3  # let server initialize

# Set root password (Dolt auto-creates root with no password on first run)
dolt --data-dir ~/arthityap/infra/dolt-server sql -q \
  "ALTER USER 'root'@'localhost' IDENTIFIED BY 'ZysxTSZtlLL';"

# Verify auth
dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q "SELECT 1"
# Expected: | 1 |
```

## Step 4: Create Database Per Repo

For each repo, create a database matching its `dolt_database` name:

```bash
dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q \
  "CREATE DATABASE IF NOT EXISTS factory"

dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q \
  "CREATE DATABASE IF NOT EXISTS literouter"

dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q \
  "CREATE DATABASE IF NOT EXISTS search"

dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q \
  "CREATE DATABASE IF NOT EXISTS ocorotate"

dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql -q \
  "CREATE DATABASE IF NOT EXISTS flourishME"
```

## Step 5: Configure Each Repo

For each repo (example: `ai-factory`), update two files:

### 5a. Update `.beads/metadata.json`

```json
{
  "database": "dolt",
  "backend": "dolt",
  "dolt_mode": "server",
  "dolt_database": "<repo_name>",
  "dolt_server_host": "127.0.0.1",
  "dolt_server_user": "root",
  "project_id": "<existing-uuid>"
}
```

- Change `dolt_mode` from `"embedded"` to `"server"`
- Add `dolt_server_host: "127.0.0.1"` and `dolt_server_user: "root"`
- DO NOT add `dolt_server_port` (deprecated, causes warning)
- Keep `dolt_database` as the repo's existing database name
- Preserve the existing `project_id`

### 5b. Create port file

```bash
echo "15432" > <repo>/.beads/dolt-server.port
```

### Repo-specific values

| Repo | dolt_database |
|------|---------------|
| ai-factory | factory |
| literouter | literouter |
| search | search |
| ocorotate | ocorotate |
| flourishME | flourishME |

## Step 6: Migrate Existing Data (One-Time)

For each repo, migrate data from the old embedded Dolt database:

```bash
# 1. Export from embedded (must cd into the repo's embedded data dir)
cd <repo>/.beads/embeddeddolt/<database_name>
dolt dump -f -o /tmp/<repo>_dump.sql

# 2. Import into server database
dolt --host=127.0.0.1 --port=15432 --user=root --password=ZysxTSZtlLL --no-tls sql \
  < /tmp/<repo>_dump.sql

# 3. Clean up
rm /tmp/<repo>_dump.sql
```

**Note**: `dolt dump` does NOT support the `--data-dir` flag. Must `cd` into the repo directory.

## Step 7: Delete Obsolete JSONL Files

After migration is verified, delete the JSONL backups (data now lives in the Dolt server):

```bash
rm <repo>/.beads/issues.jsonl
rm <repo>/.beads/interactions.jsonl
```

## Step 8: Verify

```bash
# Connection test
cd <repo>
bd dolt test
# Expected: ✓ Connection successful

# List issues (should match old counts)
bd list --status=open --limit 0 | head -5

# Concurrent write test (10 parallel processes)
for i in $(seq 1 10); do bd remember "test-concurrent-$i" & done
wait
# Expected: all 10 "Remembered" messages, no errors

# Verify all memories present
bd memories "test-concurrent"
# Expected: 10 matching memories
```

## Troubleshooting

### Warning: "nothing to commit"

Benign. bd auto-commits after every operation; Dolt warns when nothing changed.

### Warning: "dolt_ignore table does not exist"

Benign. bd queries for a Dolt-specific ignore table that doesn't exist in server mode.

### Error: "Access denied for user 'root'"

Cause: Password mismatch between `BEAMS_DOLT_PASSWORD` and server root password.

Fix:
```bash
# Set root password to match env var
dolt --data-dir ~/arthityap/infra/dolt-server sql -q \
  "ALTER USER 'root'@'localhost' IDENTIFIED BY 'ZysxTSZtlLL';"
```

### Error: "TLS requested but server does not support TLS"

Cause: Dolt CLI defaults to TLS. Use `--no-tls` flag when connecting via `dolt sql`.

### Server won't start

Check: `~/arthityap/infra/dolt-server/server.log`

If port conflict: change `PORT=15432` in `~/arthityap/dolt.sh` to an unused port.

## Architecture Summary

```
~/arthityap/infra/dolt-server/    ← Dolt SQL server data (mysql protocol, port 15432)
~/arthityap/dolt.sh              ← tmux-based server manager
/home/yapilwsl/.bashrc           ← BEAMS_DOLT_PASSWORD=ZysxTSZtlLL (shared by all repos)

repos:
  ai-factory/.beads/metadata.json   → dolt_mode=server, dolt_database=factory
  ai-factory/.beads/dolt-server.port  → 15432
  literouter/.beads/metadata.json   → dolt_mode=server, dolt_database=literouter
  literouter/.beads/dolt-server.port  → 15432
  (repeat for search, ocorotate, flourishME)
```
