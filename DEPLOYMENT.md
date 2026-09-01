# 本地部署说明

本应用只支持单机部署，不应绑定局域网或公网地址。

## 配置边界

- `HOST` 只能是 `127.0.0.1` 或 `localhost`。
- `SHOPIFY_API_VERSION` 必须是 `2026-07`。
- 生产模式 `DEBUG=false`，API 文档和详细异常默认关闭。
- MinIO 凭据必须在 `.env` 中使用随机值；Attu 只有显式启用 `debug-tools` profile 才启动。
- `.env`、`uploads/`、`volumes/`、数据库、日志和构建产物均被 Git 忽略。

## 更新与启动

```powershell
py -m uv sync --group dev
Set-Location frontend
npm ci
npm run build
Set-Location ..
docker compose -f vector-database.yml up -d
.\start-windows.bat
```

启动脚本会先执行 Alembic 迁移，然后仅在 `127.0.0.1:9901` 启动主应用；不会启动 Shopify MCP、Ads MCP 或 Attu。

管理员创建与密码重置：

```powershell
.\.venv\Scripts\python.exe -m app.cli create-admin --username king
.\.venv\Scripts\python.exe -m app.cli reset-password --username king
```

密码通过终端隐藏输入，不应写入 `.env`、命令行参数或脚本。
