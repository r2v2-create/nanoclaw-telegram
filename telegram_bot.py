#!/usr/bin/env python3
"""
nanoclaw-telegram — Production Telegram bot bridge for OpenClaw agents.

Polls Telegram for updates and forwards messages to configured agent APIs.
Config priority: /etc/nanoclaw/telegram-config.yml → ENV vars → AWS Secrets Manager
"""

import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

import requests
import yaml

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("nanoclaw-telegram")

CONFIG_PATH = os.environ.get("NANOCLAW_CONFIG", "/etc/nanoclaw/telegram-config.yml")
TELEGRAM_API = "https://api.telegram.org"
_shutdown = threading.Event()
_start_time = time.time()
_config: dict = {}


def load_secret(secret_name: str, region: str = "us-east-1") -> Optional[dict]:
    try:
        import boto3
        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_name)
        return json.loads(resp["SecretString"])
    except Exception as e:
        log.debug(f"AWS Secrets Manager unavailable ({secret_name}): {e}")
        return None


def load_config() -> dict:
    cfg: dict = {
        "agents": [],
        "health_port": int(os.environ.get("HEALTH_PORT", 9999)),
        "poll_interval": float(os.environ.get("POLL_INTERVAL", 1)),
        "aws_region": os.environ.get("AWS_REGION", "us-east-1"),
    }

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            file_cfg = yaml.safe_load(f) or {}
        cfg.update({k: v for k, v in file_cfg.items() if v is not None})
        log.info(f"Loaded config from {CONFIG_PATH}")
    else:
        log.warning(f"Config file not found: {CONFIG_PATH} — falling back to env/secrets")

    sm_path = cfg.get("secrets_manager_path") or os.environ.get("SECRETS_MANAGER_PATH")
    if sm_path:
        secrets = load_secret(sm_path, cfg["aws_region"])
        if secrets:
            log.info(f"Loaded secrets from AWS Secrets Manager: {sm_path}")
            for agent in cfg.get("agents", []):
                key = f"{agent['name'].lower().replace(' ', '_')}_token"
                if key in secrets:
                    agent["token"] = secrets[key]

    i = 0
    while True:
        name = os.environ.get(f"AGENT_{i}_NAME")
        if not name:
            break
        token = os.environ.get(f"AGENT_{i}_TOKEN", "")
        url = os.environ.get(f"AGENT_{i}_URL", "")
        if token and url:
            existing = next((a for a in cfg["agents"] if a["name"] == name), None)
            if existing:
                existing["token"] = token
                existing["url"] = url
            else:
                cfg["agents"].append({"name": name, "token": token, "url": url})
        i += 1

    if not cfg["agents"]:
        log.error("No agents configured.")
        sys.exit(1)

    return cfg


def tg_request(method: str, token: str, **kwargs) -> Optional[dict]:
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    for attempt in range(3):
        try:
            resp = requests.post(url, timeout=15, **kwargs)
            data = resp.json()
            if data.get("ok"):
                return data
            log.warning(f"Telegram {method} not ok: {data.get('description')}")
            return None
        except requests.Timeout:
            time.sleep(2 ** attempt)
        except Exception as e:
            log.error(f"Telegram {method} error: {e}")
            return None
    return None


def send_message(token, chat_id, text, parse_mode="Markdown"):
    return tg_request("sendMessage", token, json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}) is not None


def send_typing(token, chat_id):
    tg_request("sendChatAction", token, json={"chat_id": chat_id, "action": "typing"})


def query_agent(agent_url: str, agent_name: str, prompt: str, user_id: str = "") -> str:
    try:
        resp = requests.post(f"{agent_url}/api/chat",
            json={"message": prompt, "user_id": user_id}, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("response") or data.get("message") or str(data)
        return f"❌ Agent returned HTTP {resp.status_code}: {resp.text[:200]}"
    except requests.Timeout:
        return f"⏱️ {agent_name} timed out. It may still be processing."
    except Exception as e:
        return f"❌ Could not reach {agent_name}: {e}"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/health", "/"):
            body = json.dumps({
                "status": "ok",
                "uptime_s": int(time.time() - _start_time),
                "agents": [a["name"] for a in _config.get("agents", [])],
                "ts": datetime.utcnow().isoformat() + "Z",
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def run_health_server(port: int):
    server = HTTPServer(("127.0.0.1", port), HealthHandler)
    log.info(f"Health endpoint → http://127.0.0.1:{port}/health")
    while not _shutdown.is_set():
        server.handle_request()


def poll_agent(agent: dict, poll_interval: float):
    name, token, url = agent["name"], agent["token"], agent["url"]
    offset = 0
    log.info(f"[{name}] Polling Telegram → {url}")

    while not _shutdown.is_set():
        try:
            resp = requests.get(f"{TELEGRAM_API}/bot{token}/getUpdates",
                params={"offset": offset, "timeout": 20}, timeout=30)
            data = resp.json()
            if not data.get("ok"):
                log.warning(f"[{name}] getUpdates not ok: {data.get('description')}")
                time.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue

                chat_id = msg["chat"]["id"]
                username = msg.get("from", {}).get("first_name", "User")
                text = msg.get("text", "").strip()

                if not text:
                    continue

                if text.startswith("/"):
                    cmds = {
                        "/start": f"👋 Hi {username}! I'm *{name}*. Send me a message and I'll get right on it.",
                        "/help": f"*{name}* — powered by OpenClaw\n\nJust type your request and I'll handle it!",
                        "/status": f"✅ {name} is online and ready.",
                    }
                    reply = cmds.get(text.split()[0])
                    if reply:
                        send_message(token, chat_id, reply)
                    continue

                log.info(f"[{name}] {username} ({chat_id}): {text[:80]}")
                send_typing(token, chat_id)
                reply = query_agent(url, name, text, user_id=str(chat_id))
                send_message(token, chat_id, f"🤖 *{name}*:\n\n{reply}")

        except requests.Timeout:
            pass
        except Exception as e:
            log.error(f"[{name}] Poll error: {e}")
            time.sleep(5)

        time.sleep(poll_interval)


def handle_signal(sig, frame):
    log.info(f"Signal {sig} — shutting down…")
    _shutdown.set()


def main():
    global _config
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    _config = load_config()
    log.info(f"nanoclaw-telegram starting — {len(_config['agents'])} agent(s)")

    threading.Thread(target=run_health_server, args=(_config.get("health_port", 9999),), daemon=True, name="health").start()

    for agent in _config["agents"]:
        threading.Thread(target=poll_agent, args=(agent, _config.get("poll_interval", 1)),
            daemon=True, name=f"poll-{agent['name']}").start()

    log.info("All threads running. Ctrl+C to stop.")
    _shutdown.wait()
    log.info("Done.")


if __name__ == "__main__":
    main()
