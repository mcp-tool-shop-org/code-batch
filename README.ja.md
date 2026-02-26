<p align="center">
  <a href="README.ja.md">日本語</a> | <a href="README.zh.md">中文</a> | <a href="README.es.md">Español</a> | <a href="README.fr.md">Français</a> | <a href="README.hi.md">हिन्दी</a> | <a href="README.it.md">Italiano</a> | <a href="README.pt-BR.md">Português (BR)</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/mcp-tool-shop-org/brand/main/logos/code-batch/readme.png" alt="CodeBatch" width="400">
</p>

<p align="center">
  <a href="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml"><img src="https://github.com/mcp-tool-shop-org/code-batch/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
  <a href="https://mcp-tool-shop-org.github.io/code-batch/"><img src="https://img.shields.io/badge/Landing_Page-live-blue" alt="Landing Page"></a>
</p>

コンテンツベースのアドレス指定によるバッチ実行エンジン。決定論的なシャード化と、クエリ可能な出力が特徴です。

**概要:** コードをスナップショットとして保存し、作業を決定論的に分割し、すべての出力を構造化されたクエリのためにインデックス化する、ファイルシステムベースの実行基盤です。データベースは不要です。

**対象ユーザー:** 繰り返し可能なコード分析パイプライン、CI統合、または再現性と監査可能性が必要なバッチ変換ワークフローを構築する開発者。

**特長:** すべての入力はコンテンツベースでアドレス指定され、すべての実行は決定論的です。同じバッチを6ヶ月後に再実行しても、同じ結果が得られます。ログを解析することなく、意味的なタイプで出力をクエリできます。

## 概要

CodeBatchは、コードベースに対して決定論的な変換を実行するためのファイルシステムベースの実行基盤を提供します。入力は不変のスナップショットとしてキャプチャされ、作業は隔離されたシャードで実行され、すべての意味的な出力が効率的なクエリのためにインデックス化されます。データベースは不要です。

## ドキュメント

- **[SPEC.md](./SPEC.md)** — ストレージおよび実行に関する詳細仕様
- **[docs/TASKS.md](./docs/TASKS.md)** — タスクリファレンス（解析、分析、シンボル、Lint）
- **[CHANGELOG.md](./CHANGELOG.md)** — バージョン履歴

## クイックスタート

```bash
# Initialize a store
codebatch init ./store

# Create a snapshot of a directory
codebatch snapshot ./my-project --store ./store

# List available pipelines
codebatch pipelines

# Initialize a batch with a pipeline
codebatch batch init --snapshot <id> --pipeline full --store ./store

# Run all tasks and shards (Phase 5 workflow)
codebatch run --batch <id> --store ./store

# View progress
codebatch status --batch <id> --store ./store

# View summary
codebatch summary --batch <id> --store ./store
```

## ヒューマンワークフロー（フェーズ5）

フェーズ5では、既存の基本的な機能を利用して、より使いやすいコマンドが追加されています。

```bash
# Run entire batch (no manual shard iteration needed)
codebatch run --batch <id> --store ./store

# Resume interrupted execution
codebatch resume --batch <id> --store ./store

# Progress summary
codebatch status --batch <id> --store ./store

# Output summary
codebatch summary --batch <id> --store ./store
```

## 発見可能性

```bash
# List pipelines
codebatch pipelines

# Show pipeline details
codebatch pipeline full

# List tasks in a batch
codebatch tasks --batch <id> --store ./store

# List shards for a task
codebatch shards --batch <id> --task 01_parse --store ./store
```

## クエリエイリアス

```bash
# Show errors
codebatch errors --batch <id> --store ./store

# List files in a snapshot
codebatch files --batch <id> --store ./store

# Top output kinds
codebatch top --batch <id> --store ./store
```

## 探索と比較（フェーズ6）

フェーズ6では、出力を探索し、バッチを比較するための読み取り専用ビューが追加されます。これにより、ストレージを変更することなく比較できます。

```bash
# Inspect all outputs for a file
codebatch inspect src/main.py --batch <id> --store ./store

# Compare two batches
codebatch diff <batchA> <batchB> --store ./store

# Show regressions (new/worsened diagnostics)
codebatch regressions <batchA> <batchB> --store ./store

# Show improvements (fixed/improved diagnostics)
codebatch improvements <batchA> <batchB> --store ./store

# Explain data sources for any command
codebatch inspect src/main.py --batch <id> --store ./store --explain
```

## 低レベルコマンド

より詳細な制御が必要な場合は、元のコマンドが引き続き利用可能です。

```bash
# Run a specific shard
codebatch run-shard --batch <id> --task 01_parse --shard ab --store ./store

# Query outputs
codebatch query outputs --batch <id> --task 01_parse --store ./store

# Query diagnostics
codebatch query diagnostics --batch <id> --task 01_parse --store ./store

# Build LMDB acceleration cache
codebatch index-build --batch <id> --store ./store
```

## 仕様のバージョン管理

仕様は、ドラフト/安定版のマーカーを使用したセマンティックバージョニングを採用しています。各バージョンはGitでタグ付けされます（例：`spec-v1.0-draft`）。互換性を破る変更がある場合は、メジャーバージョンがインクリメントされます。実装では、どの仕様バージョンを対象としているかを宣言し、互換性のために未知のフィールドを許容する必要があります。

## プロジェクト構造

```
schemas/      JSON Schema definitions for all record types
src/          Core implementation
tests/        Test suites and fixtures
docs/         Documentation
.github/      CI/CD workflows
```

## サポート

- **質問/ヘルプ:** [ディスカッション](https://github.com/mcp-tool-shop-org/code-batch/discussions)
- **バグレポート:** [イシュー](https://github.com/mcp-tool-shop-org/code-batch/issues)

## ライセンス

MIT
