# 生产规模语义路由评估报告

## 评估范围

本报告评估 Shopify 运营助手的语义规划层。输入为当前问题和可选历史对话，输出为 `shopify`、`knowledge`、`mixed`、`chat`、`clarify`、`unsupported` 六类路由，以及最多四个只读工具。评估不执行 Shopify 工具，不核验查询参数、店铺返回值、RAG 检索结果或最终回答质量。

测试套件版本为 `routing-production-v1`，随机种子为 `20260905`。五个确定性生成的数据文件共 1500 条独立问题：核心标准集 300 条、口语与噪声集 500 条、多轮上下文集 250 条、RAG 与 Shopify 混合集 200 条、安全边界集 250 条。套件覆盖 17 个只读工具和六类路由；所有 ID 与当前问题文本全局唯一。该套件是生产规模的合成评估集，不是线上用户日志。

## 运行结果

2026-09-05 使用 `deepseek-v4-pro` 完成一轮 1500 条真实规划请求，模型请求失败为 0。运行前验证 `manifest.json` 及五个数据文件的 SHA-256，清单摘要为 `fbba90c8cf2381acfa304657bd44aa37089601cbaaf356a12f30a773d618a4ec`。

| 指标 | 结果 |
|---|---:|
| 严格准确率（路由与工具集合同时正确） | 1486/1500，99.07% |
| 路由准确率 | 1488/1500，99.20% |
| 工具 Precision | 99.86% |
| 工具 Recall | 100.00% |
| 工具 F1 | 99.93% |
| 无业务工具负例准确率 | 375/384，97.66% |
| 平均规划耗时 | 2124 ms |
| P50 / P95 / P99 规划耗时 | 2087 / 2647 / 2914 ms |
| 请求失败 | 0/1500 |

完整命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\evaluate_tool_routing.py `
  --suite tests\fixtures\evaluation\manifest.json `
  --model deepseek-v4-pro --concurrency 8 --batch-size 100 `
  --output volumes\evaluations\production-routing-v1.json
```

## 错例分析

14 条严格错例中，12 条是路由边界错误，2 条是库存问题额外选择了商品表现工具。主要模式如下：

- 知识库与通用问答或澄清的边界共 6 条。涉及“附件”“文档”的表达不够明确时，模型选择 `chat` 或 `clarify`。
- 纯 Shopify 多工具问题有 3 条被识别为 `mixed`。问题中的“联合分析”“放在一起”触发了知识与数据混合意图，但工具集合仍正确。
- 提示词注入边界有 3 条被识别为 `chat`，没有调用任何工具，也没有发生越权调用，但未命中期望的 `unsupported` 路由。
- 低库存问题有 2 条额外调用 `get_product_performance`，工具 Recall 未下降，但 Precision 受到影响。

路由混淆矩阵显示：`shopify` 916 条中 913 条正确、3 条进入 `mixed`；`knowledge` 44 条中 38 条正确、3 条进入 `chat`、3 条进入 `clarify`；`unsupported` 233 条中 230 条正确、3 条进入 `chat`。`chat`、`clarify` 和 `mixed` 的本类样例全部命中。

## 结论与边界

结果证明当前规划器在合成规模集上能够稳定选择受控路由和只读工具，并能保存逐题错例、延迟、模型、规划器摘要与数据集摘要用于复核。单轮运行不能证明重复稳定率，因此本报告不提供该指标。

该结果不等于端到端 Agent 准确率，也不能替代真实业务流量验证。上线前仍需补充经授权和脱敏的真实问法、日期与币种参数断言、Shopify 沙箱执行、RAG 证据 Recall@K 与最终答案事实性评估。
