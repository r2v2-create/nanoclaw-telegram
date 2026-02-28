# nanoclaw-telegram

Telegram bot bridge for OpenClaw agents. Polls Telegram and forwards messages to agent APIs, returning responses to users.

## Quick Install (on EC2)

```bash
# Copy skill dir to instance, then:
sudo bash install.sh
sudo nano /etc/nanoclaw/telegram-config.yml   # fill in tokens or use Secrets Manager
sudo systemctl start nanoclaw-telegram
sudo systemctl status nanoclaw-telegram
```

## Configuration

Primary config: `/etc/nanoclaw/telegram-config.yml`

### Option A — YAML (tokens in file)
```yaml
agents:
  - name: K2-Auto
    token: "8639774846:AAF3Q-..."
    url: "http://44.200.164.83:8001"
  - name: Omaha
    token: "8657042759:AAGu..."
    url: "http://18.234.160.215:8002"
```

### Option B — AWS Secrets Manager (recommended)
Store a secret at `nanoclaw/telegram`:
```json
{
  "k2-auto_token": "...",
  "omaha_token": "..."
}
```
Leave `token: ""` in the YAML. The secret is loaded at startup.

### Option C — Environment variables
```bash
AGENT_0_NAME=K2-Auto AGENT_0_TOKEN=... AGENT_0_URL=http://44.200.164.83:8001 \
AGENT_1_NAME=Omaha   AGENT_1_TOKEN=... AGENT_1_URL=http://18.234.160.215:8002 \
python telegram_bot.py
```

## Service Management

```bash
systemctl start   nanoclaw-telegram
systemctl stop    nanoclaw-telegram
systemctl restart nanoclaw-telegram
systemctl status  nanoclaw-telegram
journalctl -u nanoclaw-telegram -f   # live logs
```

## Health Check

```bash
curl http://localhost:9999/health
# {"status":"ok","uptime_s":123,"agents":["K2-Auto","Omaha"],"ts":"..."}
```

## Adding New Agents

Add entries to the `agents` list in the config YAML and restart the service — no code changes needed.

## Supported Bot Commands

- `/start` — greeting
- `/help` — usage info  
- `/status` — liveness check

Any other text is forwarded to the agent API.

## Agent API Contract

The bot tries two endpoints in order:

1. `POST /api/tasks/webhook` — async (task queued response)
2. `POST /api/chat` — sync fallback (returns `response` or `message` field)
