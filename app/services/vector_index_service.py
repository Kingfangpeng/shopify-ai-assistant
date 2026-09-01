"""向量索引服务模块"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from app.services.document_splitter_service import document_splitter_service
from app.services.vector_store_manager import vector_store_manager


class IndexingResult:
    """索引结果类"""

    def __init__(self):
        self.success = False
        self.directory_path = ""
        self.total_files = 0
        self.success_count = 0
        self.fail_count = 0
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.error_message = ""
        self.failed_files: Dict[str, str] = {}

    def increment_success_count(self):
        self.success_count += 1

    def increment_fail_count(self):
        self.fail_count += 1

    def add_failed_file(self, file_path: str, error: str):
        self.failed_files[file_path] = error

    def get_duration_ms(self) -> int:
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() * 1000)
        return 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "directory_path": self.directory_path,
            "total_files": self.total_files,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "duration_ms": self.get_duration_ms(),
            "error_message": self.error_message,
            "failed_files": self.failed_files,
        }


class VectorIndexService:
    """向量索引服务"""

    def __init__(self):
        self.upload_path = "./uploads"
        logger.info("向量索引服务初始化完成")

    def index_directory(self, directory_path: Optional[str] = None) -> IndexingResult:
        result = IndexingResult()
        result.start_time = datetime.now()

        try:
            target_path = directory_path if directory_path else self.upload_path
            dir_path = Path(target_path).resolve()

            if not dir_path.exists() or not dir_path.is_dir():
                raise ValueError(f"目录不存在或不是有效目录: {target_path}")

            result.directory_path = str(dir_path)
            files = list(dir_path.glob("*.txt")) + list(dir_path.glob("*.md"))

            if not files:
                logger.warning(f"目录中没有找到支持的文件: {target_path}")
                result.total_files = 0
                result.success = True
                result.end_time = datetime.now()
                return result

            result.total_files = len(files)
            logger.info(f"开始索引目录: {target_path}, 找到 {len(files)} 个文件")

            for file_path in files:
                try:
                    self.index_single_file(str(file_path))
                    result.increment_success_count()
                    logger.info(f"✓ 文件索引成功: {file_path.name}")
                except Exception as e:
                    result.increment_fail_count()
                    result.add_failed_file(str(file_path), str(e))
                    logger.error(f"✗ 文件索引失败: {file_path.name}, 错误: {e}")

            result.success = result.fail_count == 0
            result.end_time = datetime.now()
            logger.info(f"目录索引完成: 总数={result.total_files}, 成功={result.success_count}, 失败={result.fail_count}")
            return result

        except Exception as e:
            logger.error(f"索引目录失败: {e}")
            result.success = False
            result.error_message = str(e)
            result.end_time = datetime.now()
            return result

    def index_single_file(self, file_path: str):
        path = Path(file_path).resolve()

        if not path.exists() or not path.is_file():
            raise ValueError(f"文件不存在: {file_path}")

        logger.info(f"开始索引文件: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            logger.info(f"读取文件: {path}, 内容长度: {len(content)} 字符")

            normalized_path = path.as_posix()
            vector_store_manager.delete_by_source(normalized_path)

            documents = document_splitter_service.split_document(content, normalized_path)
            logger.info(f"文档分割完成: {file_path} -> {len(documents)} 个分片")

            if documents:
                vector_store_manager.add_documents(documents)
                logger.info(f"文件索引完成: {file_path}, 共 {len(documents)} 个分片")
            else:
                logger.warning(f"文件内容为空或无法分割: {file_path}")

        except Exception as e:
            logger.error(f"索引文件失败: {file_path}, 错误: {e}")
            raise RuntimeError(f"索引文件失败: {e}") from e


vector_index_service = VectorIndexService()
