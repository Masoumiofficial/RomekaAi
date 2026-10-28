"""Optional private feedback on assistant messages.

Revision ID: ab73f831b214
Revises: 66c743d0c078
"""
from alembic import op
import sqlalchemy as sa

revision = "ab73f831b214"
down_revision = "66c743d0c078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rating", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "message_id", name="uq_feedback_user_message"),
        sa.CheckConstraint("rating IN ('helpful', 'not_helpful')", name="ck_feedback_rating"),
    )
    op.create_index("ix_message_feedback_user_id", "message_feedback", ["user_id"])


def downgrade() -> None:
    # Downgrading removes this table and its feedback. Back up before downgrade.
    op.drop_index("ix_message_feedback_user_id", table_name="message_feedback")
    op.drop_table("message_feedback")
