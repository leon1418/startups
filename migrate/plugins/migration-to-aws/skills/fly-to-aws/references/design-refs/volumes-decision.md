# Fly Volumes → AWS Storage Decision Tree

## Description

This document provides a decision framework for migrating Fly.io volumes to AWS storage primitives. Fly volumes are local NVMe block storage with 1:1 machine attachment and **no replication** (Fly's own guidance: "always provision at least two"). AWS offers multiple storage options with different durability, latency, and persistence characteristics.

---

## Decision Order (Apply First Match)

### 1. DEFAULT: de-volume (Recommended)

**When to use**: The application stores structured data (SQLite, embedded databases) or file blobs on volumes.

**AWS target**:

- **Structured data** (SQLite, embedded DBs) → **RDS** or **Aurora PostgreSQL/MySQL**
- **File blobs** → **Amazon S3**

**Why**: Fly volumes are unreplicated local NVMe. AWS EBS is a **durability upgrade** (replicated within-AZ), but ECS+EBS has significant constraints (see below). Migrating data out of block storage to managed services eliminates volume management and improves reliability.

**Migration effort**: Moderate to high (application refactor required).

---

### 2. Shared Filesystem Need → EFS

**When to use**: The application requires a POSIX filesystem shared across multiple tasks/machines, or NFS-like semantics.

**AWS target**: **Amazon EFS** (Elastic File System)

**Constraints**:

- **Latency**: NFS latency ≫ local NVMe. IOPS-sensitive workloads (SQLite, embedded databases, high-throughput logs) will regress badly. Do NOT use EFS for latency-critical workloads.
- **Cost**: EFS pricing is $0.30/GB-month for Standard class (vs. Fly volumes at $0.15/GB-month; EBS gp3 at ~$0.08/GB-month).

**Best for**: Shared static assets, infrequently accessed data, or workloads tolerant of NFS latency.

---

### 3. True Single-Writer Persistence → ECS-on-EC2 + EBS gp3

**When to use**: The application requires durable, low-latency block storage with persistence across task restarts (single-writer, high IOPS).

**AWS target**: **ECS on EC2** with **EBS gp3 volumes**

**Why this is necessary**: Fargate+EBS is **per-task scratch** storage with the following constraints:

- 1 volume per task
- Volumes are created **new at launch only** (cannot attach existing volumes)
- Service-managed volumes are **deleted on task stop** (not task termination — they do not persist across service updates or task restarts)
- **NOT** a durable named volume equivalent to Fly's persistent volumes

To achieve true persistence, you must use **ECS on EC2** with manually managed EBS volumes or EBS-backed Docker volumes.

**Migration effort**: High (requires EC2 cluster management, volume lifecycle orchestration).

---

## Fly Volumes Context (for Sizing Reference)

- **Pricing**: $0.15/GB-month provisioned (charged even when detached)
- **Snapshots**: $0.08/GB-month actual usage, 10 GB free, daily snapshots, retention 1–60 days (default 5 days)
- **Max size**: 500 GB per volume
- **IOPS**: 4k–32k based on machine size; rootfs capped at 2000 IOPS / 8 MiB/s
- **Replication**: None — Fly's own guidance: "always provision at least two"

**AWS EBS gp3 for comparison**:

- **Pricing**: ~$0.08/GB-month
- **Durability**: Replicated within-AZ (99.8%–99.9% annual failure rate)
- **IOPS**: 3000 IOPS baseline (included), up to 16,000 IOPS provisioned
- **Max size**: 16 TiB per volume

---

## Detection Signals

Look for `[[mounts]]` sections in fly.toml:

```toml
[[mounts]]
source = "data"
destination = "/data"
```

Additional grep signals: `fly volumes`, `/mnt/`, `/data/`, SQLite database paths, embedded DB paths (e.g., LevelDB, RocksDB).

---

## Error Handling

If the application's volume usage pattern is unclear or does not fit the above categories, flag for manual review:

> "Volume usage pattern unclear: `{mount_path}`. Cannot determine AWS storage primitive. Deferring to specialist engagement for storage architecture review."
