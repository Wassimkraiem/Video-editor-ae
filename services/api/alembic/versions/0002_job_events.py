"""Add job_events so separate worker processes can report progress."""

from alembic import op
import sqlalchemy as sa

revision = "0002_job_events"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("stream_id", sa.String(64), nullable=False),
        sa.Column("event", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_job_events_stream_id", "job_events", ["stream_id"])


def downgrade():
    op.drop_index("ix_job_events_stream_id", table_name="job_events")
    op.drop_table("job_events")
