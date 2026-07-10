# Fly Postgres → RDS/Aurora Sizing Table

## Description

This table maps Fly.io Managed Postgres (MPG) plans and legacy Fly Postgres configurations to recommended AWS RDS PostgreSQL and Aurora PostgreSQL instance classes. The Design Engine uses this table to select the smallest AWS instance class that meets or exceeds the source plan's compute, storage, and connection capacity.

---

## Fly Managed Postgres (MPG) Plans

Fly Managed Postgres is a fully managed offering with bundled PgBouncer connection pooling, automated backups, and PostgreSQL 16.

### MPG Lookup Table

| MPG Plan    | Monthly Price | Compute        | RAM   | Storage     | Recommended RDS Multi-AZ | Notes                 |
| ----------- | ------------- | -------------- | ----- | ----------- | ------------------------ | --------------------- |
| Basic       | $38           | shared-cpu-2x  | 1 GB  | $0.28/GB-mo | db.t4g.small             | Fly's entry tier      |
| Starter     | $72           | shared-cpu-2x  | 2 GB  | $0.28/GB-mo | db.t4g.medium            | Step-up compute       |
| Launch      | $282          | performance-2x | 8 GB  | $0.28/GB-mo | db.m7g.large             | Production baseline   |
| Scale       | $962          | performance-4x | 32 GB | $0.28/GB-mo | db.r7g.xlarge            | High-memory workloads |
| Performance | $1,922        | performance-8x | 64 GB | $0.28/GB-mo | db.r7g.2xlarge           | Enterprise tier       |

### MPG Interpretation Notes

- **PgBouncer parity**: Fly MPG bundles PgBouncer for connection pooling. On AWS, include **RDS Proxy** in the design to stand in for the bundled PgBouncer role.
- **Storage**: Configure RDS storage allocation to meet or exceed the source MPG plan's provisioned storage (max 1 TB on Fly). AWS RDS gp3 pricing starts at $0.08/GB-month (lower than Fly's $0.28/GB-mo).
- **Scale-to-zero parity**: For applications requiring scale-to-zero database semantics (uncommon but possible with Fly), use **Aurora Serverless v2 with min 0 ACU**. Resume latency is typically ~15 seconds. **IMPORTANT**: RDS Proxy prevents pausing — configure proxy only if connection pooling is required at the expense of pause capability.
- **Aurora compatibility**: Aurora Serverless v2 min-0-ACU requires Aurora PostgreSQL ≥13.15 / 14.12 / 15.7 / 16.3.
- **Detection signals**: `*.flympg.net` hostname, user `fly-user`, database `fly-db`, or `fly mpg` commands in scripts.

---

## Legacy Fly Postgres (Unmanaged)

Fly's legacy Postgres offering uses the `postgres-flex` image and is **not managed**. Fly's own documentation states:

> "We are not able to provide support or guidance for unmanaged Postgres."

Fly's docs list **Amazon RDS** as a recommended alternative for managed Postgres. Migration to AWS RDS is framed as a **managedness upgrade**.

### Legacy Fly Postgres → RDS

| Configuration            | Fly Approach                                                        | AWS Target                                     | Notes                                 |
| ------------------------ | ------------------------------------------------------------------- | ---------------------------------------------- | ------------------------------------- |
| Dev/test single-instance | postgres-flex image, manual fly.toml, `<pg-app>.internal:5432/5433` | db.t4g.micro (~$12/mo) + 20 GB gp3 (~$2.30/mo) | Smallest RDS instance for development |
| Production               | User-managed replication, backups                                   | RDS Multi-AZ + automated backups               | Durability and managedness upgrade    |

### Detection Signals

- `postgres-flex` image in a separate fly.toml
- Database connection string pointing to `<pg-app>.internal:5432` or `:5433`
- Manual `fly pg` commands in scripts (legacy CLI, distinct from `fly mpg`)

### Migration Path

Legacy Fly Postgres → RDS migration uses **pg_dump | psql** for data transfer. Do NOT assume AWS DMS CDC (Change Data Capture) — the standard approach is plain dump/restore with a cutover window.

---

## Error Handling

If an MPG plan tier or legacy Postgres configuration is not found in this table, reject the mapping and report an error:

> "Unrecognized Fly Postgres configuration: `{plan}`. Cannot determine AWS sizing. Deferring to specialist engagement."
