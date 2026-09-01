"""为既有知识库元数据增加版本号（幂等迁移）。"""

from alembic import op
import sqlalchemy as sa

revision = "20260901_0002"
down_revision = "20260901_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("knowledge_documents")}
    if "version" not in columns:
        with op.batch_alter_table("knowledge_documents") as batch:
            batch.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("knowledge_documents")}
    if "version" in columns:
        with op.batch_alter_table("knowledge_documents") as batch:
            batch.drop_column("version")
