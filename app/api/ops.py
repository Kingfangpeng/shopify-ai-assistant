"""运营 Agent 接口 - SSE 流式输出"""

import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.models.ops import OpsRequest
from app.services.ops_agent_service import ops_agent_service

router = APIRouter()


@router.post("/ops")
async def run_ops_analysis(request: OpsRequest):
    """
    运营诊断 Agent 接口（Plan-Execute-Replan，SSE 流式）

    **功能：**
    - 自动制定分析计划
    - 逐步调用 Shopify / 广告数据工具获取真实数据
    - 流式返回每个步骤结果和最终报告

    **SSE 事件类型：**

    `status` - 状态更新
    ```json
    {"type": "status", "stage": "starting", "message": "..."}
    ```

    `plan` - 分析计划制定完成
    ```json
    {"type": "plan", "stage": "plan_created", "plan": ["步骤1", "步骤2", ...]}
    ```

    `step_complete` - 单步执行完成
    ```json
    {"type": "step_complete", "current_step": "...", "result_preview": "..."}
    ```

    `report` - 最终报告
    ```json
    {"type": "report", "stage": "final_report", "report": "# 运营分析报告\\n..."}
    ```

    `complete` - 分析完成
    ```json
    {"type": "complete", "stage": "analysis_complete"}
    ```

    **示例请求：**
    ```bash
    curl -X POST "http://localhost:9901/api/ops" \\
      -H "Content-Type: application/json" \\
      -d '{"question": "最近7天ROAS为何下跌？", "date_from": "2024-10-01", "date_to": "2024-10-07"}' \\
      --no-buffer
    ```
    """
    logger.info(f"[{request.session_id}] 收到运营分析请求: {request.question}")

    async def event_generator():
        try:
            async for event in ops_agent_service.diagnose(request):
                yield {
                    "event": "message",
                    "data": json.dumps(event, ensure_ascii=False)
                }
                if event.get("type") in ["complete", "error"]:
                    break

            logger.info(f"[{request.session_id}] 运营分析流式响应完成")

        except Exception as e:
            logger.error(f"[{request.session_id}] 运营分析流式响应异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "error",
                    "stage": "exception",
                    "message": f"分析异常: {str(e)}"
                }, ensure_ascii=False)
            }

    return EventSourceResponse(event_generator())
