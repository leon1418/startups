# Fly Machine Preset → Fargate Sizing Table

## Description

This table maps Fly.io machine presets to AWS Fargate task definition CPU and memory allocations. The Design Engine uses this table to produce Fargate task definitions that match or exceed the compute capacity of the source Fly machine configuration.

## Lookup Table

| Fly Preset      | vCPU      | RAM Range      | Fly ams Anchor $/mo | Fargate Task Size (vCPU / GB) |
| --------------- | --------- | -------------- | ------------------- | ----------------------------- |
| shared-cpu-1x   | 1x shared | 256 MB – 2 GB  | $2.02               | 0.25 vCPU / 0.5–1 GB          |
| shared-cpu-2x   | 2x shared | 512 MB – 4 GB  | $4.04               | 0.5 vCPU / 1–2 GB             |
| shared-cpu-4x   | 4x shared | 1 GB – 8 GB    | $8.08               | 1 vCPU / 2–4 GB               |
| shared-cpu-6x   | 6x shared | 1.5 GB – 12 GB | $12.12              | 1 vCPU / 3–6 GB               |
| shared-cpu-8x   | 8x shared | 2 GB – 16 GB   | $16.16              | 2 vCPU / 4–8 GB               |
| performance-1x  | 1 vCPU    | 2 GB – 8 GB    | $32.19              | 1 vCPU / 2–8 GB               |
| performance-2x  | 2 vCPU    | 4 GB – 16 GB   | $64.38              | 2 vCPU / 4–16 GB              |
| performance-4x  | 4 vCPU    | 8 GB – 32 GB   | $128.76             | 4 vCPU / 8–32 GB              |
| performance-8x  | 8 vCPU    | 16 GB – 64 GB  | $257.52             | 8 vCPU / 16–64 GB             |
| performance-16x | 16 vCPU   | 32 GB – 128 GB | $515.08             | 16 vCPU / 32–128 GB           |

## Interpretation Notes

- **Matching rule**: Select the row where the Fly preset exactly matches (case-insensitive) the source `[[vm]]` section's `size` field. For custom sizing via `cpus`/`memory`, use the nearest preset by vCPU count and RAM capacity.
- **Fargate mapping**: Shared CPUs approximate burstable economics — Fargate has no burstable tier; expect the always-on price of the mapped size. Performance presets map approximately 1:1 vCPU with 2–8 GB RAM per vCPU.
- **Custom sizing rules**: Fly allows custom `[[vm]]` configurations with RAM steps: shared CPUs use 256 MB steps (max 2 GB per CPU); performance CPUs use 2048 MB steps (max 8 GB per CPU). Map custom configs to the smallest Fargate combination rounding UP in both dimensions.
- **Fargate valid combinations**: Fargate enforces specific CPU/memory pairings. All rows in this table use valid Fargate combinations (0.25 vCPU with 0.5–2 GB; 0.5 vCPU with 1–4 GB; 1 vCPU with 2–8 GB; 2 vCPU with 4–16 GB; etc.).
- **Pricing context (FALLBACK ONLY)**: The `Fly ams Anchor $/mo` column holds static anchors from 2026-07-09 research, ±25%. They are the **fallback** for the Fly-side baseline, used when the Estimate Engine's live pricing fetch (`estimate.md` Part 1 tier 2, WebFetch of `fly.io/docs/about/pricing/`) fails entirely, or per-preset when a specific preset is not found on the fetched page — not the primary source. Prices are region-dependent (ams shown; iad is lower); the live fetch resolves the app's actual `primary_region`. The AWS-side cost calculation uses the awspricing MCP server and local cache, never this column.

## Error Handling

If a preset or custom sizing is not mappable to Fargate constraints, reject the mapping and report an error:

> "Unsupported Fly machine size: `{preset}` or custom config `{cpus} CPU / {memory} MB`. Cannot map to Fargate valid CPU/memory pairing. Please contact support or provide manual sizing."
