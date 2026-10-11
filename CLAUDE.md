# CLAUDE.md

## Automatic GitHub Commit and Push Policy

Intended repository: `https://github.com/mokshadpoojary9-bot/speakiq-ai-coach` (remote `origin`), branch `main`.

- Automatically create meaningful milestone commits and push them to the existing intended GitHub repository after each completed milestone.
- Do not ask for approval before every routine milestone commit or push.
- Before committing, inspect the Git diff and ensure relevant tests and builds pass.
- Never commit `.env` files, API keys, passwords, tokens, private data, or other secrets.
- Verify the Git remote and current branch before pushing. Push only to the intended repository and branch.
- Never force-push, rewrite shared history, or overwrite unrelated user work.
- If authentication fails, the remote is ambiguous, tests fail, or unexpected changes could be lost, stop and report the problem.
- After each successful push, report the commit hash, milestone, tests run, and push status.
- Never claim a commit or push succeeded unless Git confirms it.
