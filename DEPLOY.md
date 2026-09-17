# 部署速查

推荐使用 Docker Compose：

```bash
git clone https://github.com/umud66/aicg_check.git
cd aicg_check
docker compose up -d --build
```

默认访问地址：`http://服务器IP:8000`

建议生产环境在前面配置 Nginx / Caddy，并启用 HTTPS。若使用 Nginx，请把 `client_max_body_size` 设置为不低于应用的 `MAX_UPLOAD_MB`。

健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```
