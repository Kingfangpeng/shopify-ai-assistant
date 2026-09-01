"""创建本地认证、聊天、知识库和审计数据表。"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 模型是迁移的唯一事实来源；首次迁移由 Alembic 在空库中创建完整结构。
    from app.db.engine import Base
    from app.db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from app.db.engine import Base
    from app.db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
