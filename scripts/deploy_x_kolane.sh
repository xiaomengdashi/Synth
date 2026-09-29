#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

HOST="${HOST:?请通过环境变量指定服务器地址，例如 HOST=203.0.113.10 DOMAIN=x.kolane.top bash scripts/deploy_x_kolane.sh}"
SSH_USER="${SSH_USER:-root}"
DOMAIN="${DOMAIN:-x.kolane.top}"
APP_NAME="${APP_NAME:-synthai-x}"
NGINX_SITE_NAME="${NGINX_SITE_NAME:-x-kolane}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/synthai}"
REMOTE_WEB_DIR="${REMOTE_WEB_DIR:-/var/www/${DOMAIN}/current}"
BACKEND_PORT="${BACKEND_PORT:-8010}"
ENABLE_CERTBOT="${ENABLE_CERTBOT:-0}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

REMOTE="${SSH_USER}@${HOST}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "缺少命令: $1" >&2
    exit 1
  }
}

require_cmd ssh
require_cmd tar
require_cmd npm

if [[ ! -f "${ROOT_DIR}/frontend/package.json" ]]; then
  echo "未找到 frontend/package.json，请在项目目录中运行。" >&2
  exit 1
fi

if [[ ! -f "${ROOT_DIR}/backend/requirements.txt" ]]; then
  echo "未找到 backend/requirements.txt，请在项目目录中运行。" >&2
  exit 1
fi

echo "==> 构建前端"
npm --prefix "${ROOT_DIR}/frontend" run build

echo "==> 创建远端目录"
ssh -o StrictHostKeyChecking=no "${REMOTE}" "mkdir -p \
  '${REMOTE_APP_DIR}/backend' \
  '${REMOTE_APP_DIR}/data/media' \
  '${REMOTE_APP_DIR}/data/articles' \
  '${REMOTE_WEB_DIR}'"

echo "==> 上传前端产物"
tar -C "${ROOT_DIR}/frontend/dist" -czf - . | \
  ssh -o StrictHostKeyChecking=no "${REMOTE}" \
  "bash -lc 'rm -rf \"${REMOTE_WEB_DIR}\"/{*,.[!.]*,..?*} 2>/dev/null || true; tar -xzf - -C \"${REMOTE_WEB_DIR}\"'"

echo "==> 上传后端代码"
tar -C "${ROOT_DIR}/backend" -czf - app main.py requirements.txt | \
  ssh -o StrictHostKeyChecking=no "${REMOTE}" \
  "bash -lc 'rm -rf \"${REMOTE_APP_DIR}/backend\"/{*,.[!.]*,..?*} 2>/dev/null || true; tar -xzf - -C \"${REMOTE_APP_DIR}/backend\"'"

echo "==> 写入远端环境与服务配置"
ssh -o StrictHostKeyChecking=no "${REMOTE}" "DOMAIN='${DOMAIN}' APP_NAME='${APP_NAME}' NGINX_SITE_NAME='${NGINX_SITE_NAME}' REMOTE_APP_DIR='${REMOTE_APP_DIR}' REMOTE_WEB_DIR='${REMOTE_WEB_DIR}' BACKEND_PORT='${BACKEND_PORT}' python3 - <<'PY'
from pathlib import Path
import os

domain = os.environ['DOMAIN']
app_name = os.environ['APP_NAME']
nginx_site_name = os.environ['NGINX_SITE_NAME']
remote_app_dir = os.environ['REMOTE_APP_DIR']
remote_web_dir = os.environ['REMOTE_WEB_DIR']
backend_port = os.environ['BACKEND_PORT']
cert_dir = Path(f'/etc/letsencrypt/live/{domain}')
fullchain = cert_dir / 'fullchain.pem'
privkey = cert_dir / 'privkey.pem'

common_locations = f'''    client_max_body_size 64m;
    root {remote_web_dir};
    index index.html;

    location /assets/ {{
        try_files \$uri =404;
        expires 7d;
        add_header Cache-Control 'public, immutable';
    }}

    location /api/ {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_buffering off;
    }}

    location /media/ {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }}

    location = /health {{
        proxy_pass http://127.0.0.1:{backend_port}/health;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }}

    location / {{
        try_files \$uri \$uri/ /index.html;
    }}
'''

env_lines = [
    f'DATABASE_URL=sqlite+aiosqlite:///{remote_app_dir}/data/synthai.db',
    f'MEDIA_DIR={remote_app_dir}/data/media',
    f'ARTICLES_DIR={remote_app_dir}/data/articles',
    f'FRONTEND_URL=https://{domain}',
    'DEBUG=false',
    'APP_HOST=127.0.0.1',
    f'APP_PORT={backend_port}',
]

Path(f'/etc/{app_name}.env').write_text(
    chr(10).join(env_lines) + chr(10),
    encoding='utf-8',
)

Path(f'/etc/systemd/system/{app_name}.service').write_text(
    f'''[Unit]
Description=SynthAI FastAPI for {domain}
After=network.target

[Service]
User=root
WorkingDirectory={remote_app_dir}/backend
EnvironmentFile=/etc/{app_name}.env
Environment=PYTHONUNBUFFERED=1
ExecStart={remote_app_dir}/venv/bin/uvicorn main:app --host 127.0.0.1 --port {backend_port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
''',
    encoding='utf-8',
)

if fullchain.exists() and privkey.exists():
    nginx_conf = f'''server {{
    listen 80;
    server_name {domain};
    return 301 https://\$host\$request_uri;
}}

server {{
    listen 443 ssl;
    server_name {domain};

{common_locations}
    ssl_certificate {fullchain};
    ssl_certificate_key {privkey};
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
}}
'''
else:
    nginx_conf = f'''server {{
    listen 80;
    server_name {domain};

{common_locations}}}
'''

Path(f'/etc/nginx/sites-available/{nginx_site_name}').write_text(nginx_conf, encoding='utf-8')
PY
ln -sfn '/etc/nginx/sites-available/${NGINX_SITE_NAME}' '/etc/nginx/sites-enabled/${NGINX_SITE_NAME}'
if [ '${NGINX_SITE_NAME}' != '${APP_NAME}' ]; then
  rm -f '/etc/nginx/sites-enabled/${APP_NAME}' '/etc/nginx/sites-available/${APP_NAME}'
fi
python3 -m venv '${REMOTE_APP_DIR}/venv'
'${REMOTE_APP_DIR}/venv/bin/pip' install --upgrade pip
'${REMOTE_APP_DIR}/venv/bin/pip' install -r '${REMOTE_APP_DIR}/backend/requirements.txt'
systemctl daemon-reload
systemctl enable --now '${APP_NAME}.service'
nginx -t
systemctl reload nginx"

if [[ "${ENABLE_CERTBOT}" == "1" ]]; then
  echo "==> 签发 HTTPS 证书"
  if [[ -n "${CERTBOT_EMAIL}" ]]; then
    ssh -o StrictHostKeyChecking=no "${REMOTE}" \
      "certbot --nginx -d '${DOMAIN}' --non-interactive --agree-tos -m '${CERTBOT_EMAIL}' --redirect"
  else
    ssh -o StrictHostKeyChecking=no "${REMOTE}" \
      "certbot --nginx -d '${DOMAIN}' --non-interactive --agree-tos --register-unsafely-without-email --redirect"
  fi
fi

echo "==> 健康检查"
curl -fsSL --max-time 15 "http://${DOMAIN}/health" || true
curl -fsSL --max-time 15 "https://${DOMAIN}/health" || true

echo
echo "部署完成。"
echo "站点: https://${DOMAIN}/"
echo "服务: ${APP_NAME}.service"
