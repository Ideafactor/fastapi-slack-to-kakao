"""init

Revision ID: 0001
Revises:
Create Date: 2026-04-14

"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── channel_mapping ──────────────────────────────────────────────────────
    op.create_table(
        "channel_mapping",
        sa.Column("kakao_user_key", sa.String(255), primary_key=True, nullable=False),
        sa.Column("slack_channel_id", sa.String(50), nullable=False),
        sa.Column("channel_name", sa.String(80), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "ARCHIVED", name="channelstatus"),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_channel_mapping_slack_channel_id", "channel_mapping", ["slack_channel_id"])
    op.create_index("ix_channel_mapping_status", "channel_mapping", ["status"])

    # ── user_session ─────────────────────────────────────────────────────────
    op.create_table(
        "user_session",
        sa.Column("kakao_user_key", sa.String(255), primary_key=True, nullable=False),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_user_session_is_blocked", "user_session", ["is_blocked"])

    # ── message_log ───────────────────────────────────────────────────────────
    op.create_table(
        "message_log",
        sa.Column("message_id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("kakao_user_key", sa.String(255), nullable=True),
        sa.Column("kakao_message_id", sa.String(255), nullable=True),
        sa.Column("slack_channel_id", sa.String(50), nullable=True),
        sa.Column("slack_ts", sa.String(50), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("KAKAO_TO_SLACK", "SLACK_TO_KAKAO", name="messagedirection"),
            nullable=False,
        ),
        sa.Column(
            "payload_type",
            sa.Enum("TEXT", "IMAGE", "FILE", "VIDEO", name="payloadtype"),
            nullable=False,
            server_default="TEXT",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_message_log_kakao_user_key", "message_log", ["kakao_user_key"])
    op.create_index("ix_message_log_slack_channel_id", "message_log", ["slack_channel_id"])
    op.create_index("ix_message_log_created_at", "message_log", ["created_at"])

    # ── dead_letter ───────────────────────────────────────────────────────────
    op.create_table(
        "dead_letter",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("task_kwargs", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "status",
            sa.Enum("PENDING", "REPLAYED", "DISCARDED", name="dlqstatus"),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dead_letter_status", "dead_letter", ["status"])
    op.create_index("ix_dead_letter_task_name", "dead_letter", ["task_name"])
    op.create_index("ix_dead_letter_created_at", "dead_letter", ["created_at"])


def downgrade() -> None:
    op.drop_table("dead_letter")
    op.drop_table("message_log")
    op.drop_table("user_session")
    op.drop_table("channel_mapping")

    op.execute("DROP TYPE IF EXISTS dlqstatus")
    op.execute("DROP TYPE IF EXISTS payloadtype")
    op.execute("DROP TYPE IF EXISTS messagedirection")
    op.execute("DROP TYPE IF EXISTS channelstatus")
