"""为聊天消息增加深度分析过程元数据，保留全部旧消息。"""

from alembic import op
import sqlalchemy as sa

revision = "20260904_0002"
down_revision = "20260901_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 首次迁移复用当前模型，空库可能已包含本列。
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("chat_messages")}
    if "details_json" not in columns:
        op.add_column("chat_messages", sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_column("details_json")
