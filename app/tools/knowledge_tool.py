"""知识检索工具"""

from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.tools import tool
from loguru import logger

from app.config import config
from app.services.vector_store_manager import vector_store_manager


@tool(response_format="content_and_artifact")
def retrieve_knowledge(query: str) -> Tuple[str, List[Document]]:
    """从知识库检索相关信息（产品手册、运营策略、广告话术、竞品分析）

    Args:
        query: 查询问题
    """
    try:
        logger.info(f"知识检索: query='{query}'")
        vector_store = vector_store_manager.get_vector_store()
        retriever = vector_store.as_retriever(search_kwargs={"k": config.rag_top_k})
        docs = retriever.invoke(query)
        if not docs:
            return "没有找到相关信息。", []
        context = format_docs(docs)
        logger.info(f"检索到 {len(docs)} 个文档")
        return context, docs
    except Exception as e:
        logger.error(f"知识检索失败: {e}")
        return "知识库依赖当前不可用，无法完成检索。", []


def format_docs(docs: List[Document]) -> str:
    parts = []
    for i, doc in enumerate(docs, 1):
        metadata = doc.metadata
        source = metadata.get("file_name", metadata.get("_file_name", "未知来源"))
        headers = [metadata[k] for k in ["h1", "h2", "h3"] if metadata.get(k)]
        header_str = " > ".join(headers)
        text = f"【参考资料 {i}】"
        if header_str:
            text += f"\n标题: {header_str}"
        text += f"\n来源: {source}\n内容:\n{doc.page_content}\n"
        parts.append(text)
    return "\n".join(parts)
