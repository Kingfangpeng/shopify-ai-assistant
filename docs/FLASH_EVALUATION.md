# DeepSeek V4 Flash 语义调度评估

测试日期：2026-09-04。模型：官方 API 返回的 `deepseek-v4-flash`，规划阶段关闭思考，`temperature=0`。本地默认模型没有更改，`.env` 没有改写。

## 本轮改动与边界

聊天入口改为“模型理解意图 → 严格校验完整计划 → 服务端调用允许列表中的只读工具”。不再用正则决定聊天是否查询 Shopify，也不再合并正则猜测与模型决定。

- 意图规划在 `app/agent/semantic_planner.py`：区分实时业务、知识资料、混合分析、普通问答、澄清、能力不足六种路由。
- 编排在 `app/services/chat/agent_service.py`：只有需要资料时才访问知识库，普通问答及纯 Shopify 查询不依赖 Milvus。
- 执行在 `app/agent/dispatcher.py`：保留只读工具允许列表、严格类型和最多四个工具的限制；非法或失败计划不执行。
- 原生工具调用不可用时，尝试同样受严格校验的 JSON 计划；规划仍失败则明确报错，不静默退回关键词猜测。
- 历史运营模块仍保留旧规则。本轮没有开放任意 GraphQL，也没有实现动态参数、多轮调用后再规划的完整工具循环。日期和筛选参数仍由已有服务端实现生成。

## 实际结果

| 问题集与阶段 | 独立题数 × 重复次数 | 严格通过 | 平均规划耗时 |
|---|---:|---:|---:|
| 旧问题集，最终回归 | 48 × 1 | 48/48，100% | 1.156 秒 |
| 新问题集 A，首次测试 | 24 × 2 | 42/48，87.50% | 1.324 秒 |
| 新问题集 A，能力说明修正后复测 | 24 × 2 | 44/48，91.67% | 1.800 秒 |
| 新增问题集 B，最终提示词未再调优 | 12 × 2 | 23/24，95.83% | 1.569 秒 |

四组均没有请求失败。并发为每个评估进程最多三个请求，耗时不含等待并发槽位的时间；个别评估进程同时运行，耗时不是严格受控性能对比。

旧问题集仅校验工具集合，是回归而不是盲测。A/B 同时校验路由和工具集合；多选一个工具也判错。A 首测发现问题后修改了能力说明，因此之后只能称复测，不能再称独立盲测。B 在修正后新增并预先固定答案，评估之后未据其错题继续调优。

重复两遍不等于增加一倍独立问题。测试集由项目开发方编写，规模小、业务范围有限，95.83% 不能代表所有中文问题的真实准确率。

## 代表问题与真实错题

| 问题 | 期望行为 | B 两轮结果 |
|---|---|---|
| 最近哪几个品撑起了店里的销量？ | 查询产品表现 | 2/2 正确 |
| 昨天进站的人用手机多还是用电脑多？ | 查询设备流量 | 2/2 正确 |
| 把我们的售后文档和实际退款统计放在一起分析。 | 知识库 + 退款统计 | 2/2 正确 |
| 那换成新客和回头客的占比吧。（前文讨论订单） | 改为客户分层，不沿用订单工具 | 2/2 正确 |
| 想知道 Google 投放昨天的点击成本。 | 明确广告源未接入，不替代成折扣指标 | 2/2 正确 |
| 把全部商品价格降低百分之十并保存到后台。 | 不执行店铺写操作 | 2/2 正确 |
| 把附件里的商品介绍改得更适合新手阅读，只给我文字草稿。 | 检索资料后起草文字 | 1/2；另一次误分为普通问答 |

A 首测还出现过广告 ROAS 错选折扣工具，以及把文案润色误当成修改店铺。修正系统能力说明后，这两类在本次 A 复测和 B 中没有再出现；不能据此保证未来不会发生。

A 复测的四次错误来自两道题：促销说明结合折扣表现、访客到付款的转化比例。都选到了专项工具，但额外选择了订单汇总。这属于查询不够精简，不等于返回数字必然错误。

## 测到了什么，没测什么

- 测到：真实调用 Flash 的意图理解、只读工具选择、否定表达、部分多轮指代、混合资料问题和能力边界。
- 未测：实际 Shopify 返回数字的准确性、日期区间、国家/SKU 等筛选参数、店铺授权、检索命中质量和最终文字答案。
- 测评只走真实聊天使用的 `resolve_plan`，不执行 Shopify 业务工具，不读取或修改订单。
- 不能用本报告声称“完整 Agent 准确率 95.83%”或“已经完全不使用正则”。

## 本地验证

- 后端自动化测试 90 项通过，覆盖合法空工具计划、非法计划、规划超时/失败、混合资料故障、普通聊天不访问 Milvus、HTTP/SSE 路由和评估计分。
- 前端单元测试 8 项通过；Vite 构建通过；端到端登录、知识库、聊天、回收站和登出流程 1 项通过。
- 端到端测试使用隔离的模型和业务服务替身，不代表真实 Shopify 店铺烟雾测试。
- `npm audit` 未发现漏洞；`pip-audit` 未发现已知漏洞，本项目自身的本地包不在 PyPI，扫描器跳过该包。
- 本轮没有执行云端 CI，也没有提交、合并或推送。

## 复现

在项目根目录运行；会调用 `.env` 配置的模型服务并可能产生 API 费用，不执行 Shopify 工具：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_tool_routing.py --model deepseek-v4-flash --cases tests/fixtures/semantic_flash_holdout_b.json --repeat 2 --output volumes/evaluations/flash-recheck.json
```

输入问题集：

- `tests/fixtures/tool_routing_cases.json`
- `tests/fixtures/semantic_flash_holdout.json`
- `tests/fixtures/semantic_flash_holdout_b.json`

原始记录保存在 Git 忽略的 `volumes/evaluations/`，包括逐题结果、模型、时间、提示词代码与问题集的 SHA-256：

- `flash-semantic-final-regression.json`
- `flash-semantic-holdout.json`
- `flash-semantic-corrected-retest.json`
- `flash-semantic-holdout-b.json`

## 参考依据

- [DeepSeek 官方模型列表与参数](https://api-docs.deepseek.com/quick_start/pricing)
- [DeepSeek 官方思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)
- [DeepSeek 官方开源工具机制](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/tools/README.md)
