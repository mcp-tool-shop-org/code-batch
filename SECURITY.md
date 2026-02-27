# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

**Email:** 64996768+mcp-tool-shop@users.noreply.github.com

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

**Response timeline:**
- Acknowledgment: within 48 hours
- Assessment: within 7 days
- Fix (if confirmed): within 30 days

## Scope

CodeBatch is a **local-first CLI tool** for content-addressed batch execution.
- **Data accessed:** Reads source files for content-addressed snapshotting (SHA-256 hashing). Writes batch stores, shard outputs, and LMDB index files to user-specified directories. All operations are deterministic and filesystem-only.
- **Data NOT accessed:** No network requests. No telemetry. No cloud services. No credential storage. Source files are hashed but never transmitted.
- **Permissions required:** File system read for source directories. File system write for store and output directories. No elevated permissions required.
