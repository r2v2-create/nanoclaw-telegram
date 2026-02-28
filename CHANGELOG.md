# Changelog

All notable changes to the `nanoclaw-telegram` skill.

---

## [1.0.0] - 2026-02-28

### Added

- **Initial release** of the nanoclaw-telegram OpenClaw skill
- Persistent Telegram bot bridge running as a systemd service
- Long-polling via Telegram `getUpdates` API
- Multi-agent support: one service can bridge multiple bots to multiple agent APIs
- Three configuration methods: YAML, AWS Secrets Manager, environment variables
- AWS Secrets Manager integration (reads `nanoclaw/telegram` secret at startup)
- Standard agent API contract support:
  - Primary: `POST /api/tasks/webhook` (async)
  - Fallback: `POST /api/chat` (sync)
- Local health check endpoint: `GET http://127.0.0.1:9999/health`
- Built-in bot commands: `/start`, `/help`, `/status`
- `install.sh` — automated setup (venv, systemd, config directory)
- `config.example.yml` — reference configuration with all options documented
- Systemd service unit with auto-restart on failure

### Known Issues

- Long-polling only (no webhook mode); higher latency vs webhooks for high-volume bots
- No per-user rate limiting (relies on Telegram's built-in limits)
- Logs are unstructured text; no JSON logging for log aggregation pipelines

### Future Work

- Publish to ClawHub for `clawhub install nanoclaw-telegram`
- Webhook mode support (requires HTTPS endpoint)
- Per-user rate limiting
- Structured (JSON) logging
- Horizontal scaling support (multiple service instances with shared state)
