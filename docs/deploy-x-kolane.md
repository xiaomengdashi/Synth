# `x.kolane.top` 部署说明

这套部署对应当前线上结构：

- 前端：`Vite` 构建后的静态文件
- 后端：`FastAPI + uvicorn`
- 反向代理：`Nginx`
- 进程管理：`systemd`
- HTTPS：`Certbot + Let's Encrypt`

## 路径约定

- 前端静态文件：`/var/www/x.kolane.top/current`
- 后端代码：`/opt/synthai/backend`
- 后端虚拟环境：`/opt/synthai/venv`
- 后端数据：`/opt/synthai/data`
- 环境变量：`/etc/synthai-x.env`
- systemd 服务：`synthai-x.service`
- Nginx 站点：`/etc/nginx/sites-available/x-kolane`

## 一键部署

在项目根目录运行：

```bash
bash scripts/deploy_x_kolane.sh
```

默认参数：

- 服务器：`root@<服务器IP>`
- 域名：`x.kolane.top`
- 后端端口：`8010`

也可以临时覆盖：

```bash
HOST=<服务器IP> DOMAIN=x.kolane.top BACKEND_PORT=8010 bash scripts/deploy_x_kolane.sh
```

## 首次签发 HTTPS

确认 DNS 已指向目标服务器后运行：

```bash
ENABLE_CERTBOT=1 bash scripts/deploy_x_kolane.sh
```

如果想带邮箱：

```bash
ENABLE_CERTBOT=1 CERTBOT_EMAIL=you@example.com bash scripts/deploy_x_kolane.sh
```

## 这个脚本会做什么

1. 本地执行 `frontend` 生产构建
2. 上传前端 `dist`
3. 上传后端 `app`、`main.py`、`requirements.txt`
4. 在服务器创建或更新 `venv`
5. 安装 Python 依赖
6. 写入 `systemd` 和 `Nginx` 配置
7. 重启后端服务并重载 `Nginx`
8. 可选申请 HTTPS 证书

## 不会做什么

这个脚本默认**不会覆盖**线上数据目录：

- 不同步本地 `backend/data`
- 不删除线上 `synthai.db`
- 不覆盖线上 `config.json`

这样做是为了避免发布代码时误清空线上文章、配置和媒体文件。

## 如果要同步数据

请单独执行，避免和日常代码发布混在一起：

```bash
tar -C backend -czf - data | \
ssh root@<服务器IP> "rm -rf /opt/synthai/data.bak && cp -a /opt/synthai/data /opt/synthai/data.bak 2>/dev/null || true; tar -xzf - -C /opt/synthai"
```

建议只在你明确需要迁移本地数据库、媒体文件和配置时再做。

## 常用检查

查看后端服务：

```bash
ssh root@<服务器IP> "systemctl status synthai-x.service --no-pager -n 50"
```

查看后端日志：

```bash
ssh root@<服务器IP> "journalctl -u synthai-x.service -n 100 --no-pager"
```

检查 Nginx：

```bash
ssh root@<服务器IP> "nginx -t && systemctl reload nginx"
```

检查 HTTPS：

```bash
curl -I https://x.kolane.top/
curl https://x.kolane.top/health
```

## 续期方式

服务器当前使用系统里的 `certbot.timer` 自动续期，证书续期配置在：

- `/etc/letsencrypt/renewal/x.kolane.top.conf`

Nginx 中的证书路径为：

- `/etc/letsencrypt/live/x.kolane.top/fullchain.pem`
- `/etc/letsencrypt/live/x.kolane.top/privkey.pem`
