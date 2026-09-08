"""增加会话摘要与需确认的长期记忆。"""

from alembic import op
import sqlalchemy as sa

revision = "20260908_0003"
down_revision = "20260904_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    chat_columns = {column["name"] for column in inspector.get_columns("chat_sessions")}
    additions = (
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_through_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_prompt_version", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("summary_updated_at", sa.DateTime(), nullable=True),
    )
    for column in additions:
        if column.name not in chat_columns:
            op.add_column("chat_sessions", column)

    if "memory_facts" not in set(inspector.get_table_names()):
        op.create_table(
            "memory_facts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("memory_key", sa.String(length=80), nullable=False),
            sa.Column("kind", sa.String(length=30), nullable=False, server_default="preference"),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("sensitivity", sa.String(length=20), nullable=False, server_default="normal"),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("source_session_id", sa.String(length=36), nullable=True),
            sa.Column("source_message_id", sa.Integer(), nullable=True),
            sa.Column("supersedes_id", sa.String(length=36), nullable=True),
            sa.Column("conflicts_with_id", sa.String(length=36), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_memory_facts_user_id", "memory_facts", ["user_id"])
        op.create_index("ix_memory_user_status_updated", "memory_facts", ["user_id", "status", "updated_at"])
        op.create_index("ix_memory_user_key_version", "memory_facts", ["user_id", "memory_key", "version"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "memory_facts" in set(inspector.get_table_names()):
        op.drop_table("memory_facts")
    columns = {column["name"] for column in sa.inspect(bind).get_columns("chat_sessions")}
    for name in (
        "summary_updated_at",
        "summary_prompt_version",
        "summary_through_sequence",
        "summary_version",
        "summary",
    ):
        if name in columns:
            with op.batch_alter_table("chat_sessions") as batch:
                batch.drop_column(name)
