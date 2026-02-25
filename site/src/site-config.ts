import type { SiteConfig } from "@mcptoolshop/site-theme"

export const config: SiteConfig = {
  title: "CodeBatch",
  description:
    "Content-addressed batch execution engine — deterministic sharding, queryable outputs, no database required.",
  logoBadge: "CB",
  brandName: "CodeBatch",
  repoUrl: "https://github.com/mcp-tool-shop-org/code-batch",
  footerText:
    'MIT Licensed — built by <a href="https://github.com/mcp-tool-shop-org" style="color:var(--color-muted);text-decoration:underline">mcp-tool-shop-org</a>',

  hero: {
    badge: "Python · Filesystem-native · No database",
    headline: "Deterministic batches.",
    headlineAccent: "Queryable outputs.",
    description:
      "CodeBatch snapshots your code, shards work deterministically across pipelines, and indexes every output for structured queries — all on the filesystem. Re-run the same batch six months later and get identical results.",
    primaryCta: { href: "#get-started", label: "Get started" },
    secondaryCta: { href: "#how-it-works", label: "How it works" },
    previews: [
      {
        label: "Quick start",
        code: "pip install codebatch\n\n# Initialize a store\ncodebatch init ./store\n\n# Snapshot a directory\ncodebatch snapshot ./my-project --store ./store\n\n# Initialize + run a batch\ncodebatch batch init --snapshot <id> --pipeline full --store ./store\ncodebatch run --batch <id> --store ./store"
      },
      {
        label: "Query outputs",
        code: "# Show errors across all shards\ncodebatch errors --batch <id> --store ./store\n\n# Top output kinds\ncodebatch top --batch <id> --store ./store\n\n# Inspect all outputs for a file\ncodebatch inspect src/main.py --batch <id> --store ./store\n\n# Compare two batches\ncodebatch diff <batchA> <batchB> --store ./store"
      },
      {
        label: "Phase 5 workflow",
        code: "# High-level commands — no manual shard iteration\ncodebatch run    --batch <id> --store ./store\ncodebatch resume --batch <id> --store ./store\ncodebatch status --batch <id> --store ./store\ncodebatch summary --batch <id> --store ./store\n\n# Phase 6: compare batches\ncodebatch regressions  <batchA> <batchB> --store ./store\ncodebatch improvements <batchA> <batchB> --store ./store"
      }
    ]
  },

  sections: [
    {
      kind: "features",
      id: "features",
      title: "Built for reproducibility",
      subtitle: "Same input. Same pipeline. Same result. Always.",
      features: [
        {
          title: "Content-addressed inputs",
          desc: "Every input is hashed and captured as an immutable snapshot. Same content → same hash → same result. Re-run any batch months later and get byte-identical outputs."
        },
        {
          title: "Deterministic sharding",
          desc: "Work is split into shards by a deterministic algorithm keyed on file paths. Same input, same pipeline, same shard layout. Parallelizable, resumable, and auditable."
        },
        {
          title: "No database required",
          desc: "All state lives on the filesystem as JSON records. Query outputs by semantic kind — diagnostics, symbols, errors — without SQL, without a server, without any setup."
        }
      ]
    },
    {
      kind: "data-table",
      id: "commands",
      title: "CLI reference",
      subtitle: "High-level workflow commands and low-level primitives.",
      columns: ["Command", "Description"],
      rows: [
        ["codebatch init", "Initialize a filesystem store"],
        ["codebatch snapshot", "Capture a directory as an immutable content-addressed snapshot"],
        ["codebatch batch init", "Initialize a batch from a snapshot and pipeline"],
        ["codebatch run", "Run all tasks and shards in a batch"],
        ["codebatch resume", "Resume an interrupted batch from where it stopped"],
        ["codebatch status", "Show per-shard progress across all tasks"],
        ["codebatch inspect", "Inspect all outputs for a specific file"],
        ["codebatch diff", "Compare outputs between two batches"],
        ["codebatch query", "Query outputs by type (outputs, diagnostics, symbols)"]
      ]
    },
    {
      kind: "code-cards",
      id: "get-started",
      title: "Get started",
      cards: [
        {
          title: "Initialize & snapshot",
          code: "pip install codebatch\n\n# Create a store\ncodebatch init ./store\n\n# Snapshot a project\ncodebatch snapshot ./my-project --store ./store\n\n# List available pipelines\ncodebatch pipelines"
        },
        {
          title: "Run a batch",
          code: "# Init batch with pipeline\ncodebatch batch init \\\n  --snapshot <id> \\\n  --pipeline full \\\n  --store ./store\n\n# Run everything\ncodebatch run --batch <id> --store ./store\n\n# Check progress\ncodebatch status --batch <id> --store ./store"
        },
        {
          title: "Query outputs",
          code: "# Show all errors\ncodebatch errors --batch <id> --store ./store\n\n# Top output kinds by count\ncodebatch top --batch <id> --store ./store\n\n# File-level inspection\ncodebatch inspect src/main.py \\\n  --batch <id> --store ./store --explain\n\n# List files in snapshot\ncodebatch files --batch <id> --store ./store"
        },
        {
          title: "Compare batches",
          code: "# Full diff between two runs\ncodebatch diff <batchA> <batchB> --store ./store\n\n# New or worsened diagnostics\ncodebatch regressions \\\n  <batchA> <batchB> --store ./store\n\n# Fixed or improved diagnostics\ncodebatch improvements \\\n  <batchA> <batchB> --store ./store"
        }
      ]
    },
    {
      kind: "features",
      id: "how-it-works",
      title: "How it works",
      subtitle: "Three deterministic steps from source tree to queryable output store.",
      features: [
        {
          title: "Snapshot",
          desc: "Content-address a directory by hashing every file. The snapshot is immutable — a stable reference to an exact codebase state. Stored in the filesystem store, zero copies needed."
        },
        {
          title: "Shard & execute",
          desc: "A pipeline defines ordered tasks. Each task is sharded deterministically by file path. Shards execute in isolation and write structured JSON output records — no shared state."
        },
        {
          title: "Index & query",
          desc: "Outputs are indexed by semantic kind (diagnostics, symbols, errors). Query by type without parsing logs. Build an LMDB acceleration cache for large stores with `index-build`."
        }
      ]
    }
  ]
}
