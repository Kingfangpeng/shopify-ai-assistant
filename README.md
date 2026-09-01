# Shopify AI Assistant

本项目是一个仅供本机使用的 Shopify 商家运营台，提供只读 Shopify GraphQL 数据工具、本地知识库 RAG、服务端聊天历史和单管理员登录。

## 当前能力

- Shopify Admin GraphQL API 固定为 `2026-07`，包含订单汇总、弃购、库存、产品表现、客户分层、退款、折扣和订单列表八项只读查询。
- 未配置真实 Shopify 凭据时不会返回伪造数据；只有显式设置 `SHOPIFY_DEMO_MODE=true` 才返回带 `source=demo` 的演示数据。
- SQLite 保存管理员、令牌哈希、聊天、知识文档元数据和审计事件；Milvus 只保存向量。
- 登录使用 Argon2id、HttpOnly/SameSite=Strict Cookie、服务端会话、CSRF、Origin/Host 校验和登录限流。
- 知识库只接受 UTF-8 `.txt`/`.md`，支持 SHA-256 去重、安全更新、七天回收站和恢复。
- Facebook/Google Ads 本轮默认关闭，启动脚本不启动 MCP 服务，Agent 只注册知识库、时间和 Shopify 只读工具。

## 本地启动

```powershell
Copy-Item .env.example .env
py -m pip install --user uv
py -m uv sync --group dev
docker compose -f vector-database.yml up -d
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe -m app.cli create-admin --username king
.\start-windows.bat
```

浏览器访问 `http://127.0.0.1:9901`。Linux/macOS 可使用 `./start.sh`。

Shopify Custom App 最小权限：`read_orders`、`read_products`、`read_inventory`、`read_customers`、`read_discounts`。查询超过 60 天的订单还需要 `read_all_orders`。弃购查询需要 `read_orders` 及店铺侧弃购管理权限。

## 验证

```powershell
.\.venv\Scripts\pytest.exe tests\backend -q
.\.venv\Scripts\pip-audit.exe
Set-Location frontend
npm test
npm run build
npm run test:e2e
npm audit --audit-level=moderate
```

真实 Shopify 烟雾测试需在本地 `.env` 配置只读 Custom App token。自动化测试不会访问真实店铺、Milvus 或外部大模型。

## 剩余风险

Milvus 本轮未启用自身用户鉴权，但 Docker 端口只绑定 `127.0.0.1`；本机其他进程仍可能访问。SQLite、源文件和向量不做应用层静态加密，应启用 BitLocker 或其他全盘加密，并保护 Windows 用户账号。
