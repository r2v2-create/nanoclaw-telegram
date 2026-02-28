# nanoclaw-telegram

**Persistent Telegram → OpenClaw agent bridge**

Runs as a systemd service. Polls each configured Telegram bot for messages, routes them to the corresponding agent API, and delivers responses back to users.

## Architecture

```
Telegram Users
     │
     ▼ (getUpdates long-poll)
nanoclaw-telegram (systemd service)
     │
     ├─── POST /api/tasks/webhook  ──►  K2-Auto EC2 (44.200.164.83:8001)
     └─── POST /api/tasks/webhook  ──►  Omaha EC2   (18.234.160.215:8002)
```

## File Layout

```
/opt/nanoclaw-telegram/
├── telegram_bot.py       # main process
└── venv/                 # Python virtualenv

/etc/nanoclaw/
└── telegram-config.yml   # runtime config (agents, tokens, URLs)

/etc/systemd/system/
└── nanoclaw-telegram.service
```

## Deploying to EC2 instances

Both K2-Auto and Omaha should run their own copy of the service, each configured with their respective bot token and local agent URL (`http://localhost:8001` or `http://localhost:8002` is preferable from within the instance).

### Steps per instance

```bash
# 1. Copy skill files
scp -r ~/.npm-global/lib/node_modules/openclaw/skills/nanoclaw-telegram ubuntu@<IP>:~/nanoclaw-telegram

# 2. SSH in and install
ssh ubuntu@<IP>
cd ~/nanoclaw-telegram
sudo bash install.sh

# 3. Configure tokens
sudo nano /etc/nanoclaw/telegram-config.yml

# 4. Start
sudo systemctl start nanoclaw-telegram
sudo journalctl -u nanoclaw-telegram -f
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No agents configured` | Check /etc/nanoclaw/telegram-config.yml exists and has agents |
| `Connection refused` to agent URL | Ensure agent API is running on that port |
| Bot not responding | Check token is valid; `journalctl -u nanoclaw-telegram` for errors |
| High CPU | Increase `poll_interval` in config (default: 1s) |
| Secrets Manager errors | Ensure EC2 instance role has `secretsmanager:GetSecretValue` |

## Rotating Tokens

1. Update the secret in AWS Secrets Manager (or edit the YAML)
2. `systemctl restart nanoclaw-telegram`

## Security Notes

- Bot tokens are **never** hardcoded. Use YAML or Secrets Manager.
- Health server binds to `127.0.0.1` only (not publicly accessible).
- Run as non-root user (`ubuntu` by default).
