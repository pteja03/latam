"""almacen clave valor

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-11 00:30:26.739555
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "almacen_clave_valor",
        sa.Column("clave", sa.String(length=200), nullable=False),
        sa.Column("valor", sa.Text(), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "creado_en", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("eliminado_en", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_almacen_clave", "almacen_clave_valor", ["clave"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_almacen_clave", table_name="almacen_clave_valor")
    op.drop_table("almacen_clave_valor")
