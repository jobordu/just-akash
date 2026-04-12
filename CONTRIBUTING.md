# Contributing

Contributions are welcome — bug reports, fixes, and well-scoped features.

## Before you start

For anything beyond a small bug fix, open an issue first to discuss the change. This avoids wasted effort if the direction doesn't fit the project.

## Setup

```bash
git clone https://github.com/jobordu/just-akash
cd just-akash
cp .env.example .env
# Edit .env — add your API key, providers, SSH pubkey
```

## Workflow

```bash
git checkout -b fix/your-change   # or feature/your-change
# make changes
just lint                          # ruff lint + format check
just secrets                       # gitleaks secret scan
git commit -m "..."
git push origin fix/your-change
# open a PR against main
```

## Guidelines

- Keep changes focused. One concern per PR.
- Do not commit `.env` or `.tags.json` — both are gitignored for good reason.
- Run `just secrets` before pushing to confirm no secrets are staged.
- All PRs run the gitleaks secret scan CI check. It must pass before merging.
- Write clear commit messages. Prefer the imperative mood ("Add X", "Fix Y", "Remove Z").

## What fits this project

- Bug fixes
- New deployment strategies or bid selection logic
- Improved provider diagnostics
- Better SDL templates
- Documentation improvements

## What doesn't fit

- Adding external Python dependencies (this tool is intentionally stdlib-only)
- Storing API keys or credentials anywhere other than environment variables
- Changes that require a specific cloud provider beyond Akash Network

## Reporting bugs

Use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) issue template. Include the deployment log output — the structured JSON lines make diagnosis much faster.
