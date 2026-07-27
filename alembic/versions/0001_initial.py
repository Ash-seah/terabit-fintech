"""Create financial data tables.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "historical_bars",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("interval", sa.String(length=16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 10), nullable=False),
        sa.Column("high", sa.Numeric(24, 10), nullable=False),
        sa.Column("low", sa.Numeric(24, 10), nullable=False),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "interval", "timestamp", name="uq_historical_bar"),
    )
    op.create_index(
        "ix_historical_symbol_interval_time",
        "historical_bars",
        ["symbol", "interval", "timestamp"],
    )
    op.create_table(
        "realtime_trades",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(24, 10), nullable=False),
        sa.Column("conditions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_symbol_time", "realtime_trades", ["symbol", "timestamp"])
    op.create_table(
        "minute_bars",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(24, 10), nullable=False),
        sa.Column("high", sa.Numeric(24, 10), nullable=False),
        sa.Column("low", sa.Numeric(24, 10), nullable=False),
        sa.Column("close", sa.Numeric(24, 10), nullable=False),
        sa.Column("volume", sa.Numeric(24, 10), nullable=False),
        sa.Column("trade_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "timestamp", name="uq_minute_bar"),
    )
    op.create_index("ix_minute_symbol_time", "minute_bars", ["symbol", "timestamp"])
    op.create_table(
        "provider_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resource_key", sa.String(length=512), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "resource_key", name="uq_provider_resource"),
    )


def downgrade() -> None:
    op.drop_table("provider_snapshots")
    op.drop_index("ix_minute_symbol_time", table_name="minute_bars")
    op.drop_table("minute_bars")
    op.drop_index("ix_trade_symbol_time", table_name="realtime_trades")
    op.drop_table("realtime_trades")
    op.drop_index("ix_historical_symbol_interval_time", table_name="historical_bars")
    op.drop_table("historical_bars")
