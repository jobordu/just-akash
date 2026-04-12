# Security Policy

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report vulnerabilities privately by emailing: **jonathanborduas@gmail.com**

Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact

You will receive a response within 72 hours. If the issue is confirmed, a fix will be prioritised and a patched release published as soon as possible. You will be credited in the release notes unless you prefer otherwise.

## Scope

This tool deploys compute instances on Akash Network via the Console API. The main security surface areas are:

- **`.env` file** — contains your Akash Console API key and provider allowlist. Gitignored. Never commit it.
- **`AKASH_API_KEY`** — your Console API key. Read from environment, never hardcoded.
- **`SSH_PUBKEY`** — injected into containers at deploy time. Not stored in the repo.
- **Provider allowlist** — controls which providers can host your workloads. Keep it restricted to providers you trust.

## Secret Scanning

This repository uses three layers of secret detection:
- **Gitleaks** — pre-commit hook + CI on every push/PR + weekly full-history scan
- **TruffleHog** — CI on every push/PR (verified secrets only)
- **detect-secrets** — baseline file + CI diff check

If you find a secret in the repository, report it immediately using the process above.
