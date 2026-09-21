# Deploying Ask La Trobe Policy DB Chatbot

This guide covers running the backend + frontend on a single Linux server
(Ubuntu/Debian) with Docker + Nginx.

---

## Prerequisites

- A Linux server (Ubuntu 22.04+ recommended)
- Docker Engine 24+
- Docker Compose v2
- Nginx (for reverse proxy)
- A domain name pointing at the server
- TLS certificate (Let's Encrypt via `certbot`)

---

## 1. Clone and configure

```bash
git clone <your-repo> /opt/ask-latrobe-policy-db-chatbot
cd /opt/ask-latrobe-policy-db-chatbot/backend

# Create a production .env
cp .env.example .env
$EDITOR .env