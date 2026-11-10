"""esquema inicial

Revision ID: 0001
Revises:
Create Date: 2026-11-10 18:04:36.995111
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # btree_gist: necesario para el constraint de exclusion DAT-05 (igualdad de UUID en gist).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "doctor",
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("telefono_whatsapp", sa.String(length=20), nullable=False),
        sa.Column("zona_horaria", sa.String(length=64), nullable=False),
        sa.Column("hora_cierre_diario", sa.Time(), nullable=False),
        sa.Column("duracion_cita_default_min", sa.Integer(), nullable=False),
        sa.Column("credenciales_google_calendar", sa.Text(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
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
    op.create_index(
        "uq_doctor_telefono_whatsapp",
        "doctor",
        ["telefono_whatsapp"],
        unique=True,
        postgresql_where="eliminado_en IS NULL",
    )
    op.create_table(
        "log_auditoria",
        sa.Column("entidad", sa.String(length=50), nullable=False),
        sa.Column("id_entidad", sa.UUID(), nullable=False),
        sa.Column("accion", sa.String(length=50), nullable=False),
        sa.Column("actor", sa.String(length=100), nullable=False),
        sa.Column("cambios", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "fecha", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
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
    op.create_index(
        "ix_log_auditoria_entidad", "log_auditoria", ["entidad", "id_entidad"], unique=False
    )
    op.create_table(
        "paciente",
        sa.Column("nombre_completo", sa.String(length=200), nullable=False),
        sa.Column("nombre_normalizado", sa.String(length=200), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=True),
        sa.Column("correo", sa.String(length=200), nullable=True),
        sa.Column("notas_clinicas_breves", sa.Text(), nullable=True),
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
    op.create_index(
        op.f("ix_paciente_nombre_normalizado"), "paciente", ["nombre_normalizado"], unique=False
    )
    op.create_table(
        "usuario_recepcion",
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("correo", sa.String(length=200), nullable=False),
        sa.Column("hash_password", sa.String(length=255), nullable=False),
        sa.Column(
            "rol",
            sa.Enum("recepcion", "admin", name="rolusuario", native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column("doctores_asignados", postgresql.ARRAY(sa.UUID()), nullable=False),
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
    op.create_index(
        "uq_usuario_recepcion_correo",
        "usuario_recepcion",
        ["correo"],
        unique=True,
        postgresql_where="eliminado_en IS NULL",
    )
    op.create_table(
        "alerta_recepcion",
        sa.Column("id_doctor", sa.UUID(), nullable=False),
        sa.Column("mensaje_ia", sa.Text(), nullable=False),
        sa.Column("instruccion_original", sa.Text(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente",
                "en_proceso",
                "resuelta",
                name="estadoalerta",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("resuelta_por", sa.UUID(), nullable=True),
        sa.Column("resuelta_en", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["id_doctor"],
            ["doctor.id"],
        ),
        sa.ForeignKeyConstraint(
            ["resuelta_por"],
            ["usuario_recepcion.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alerta_doctor_estado", "alerta_recepcion", ["id_doctor", "estado"], unique=False
    )
    op.create_table(
        "cita",
        sa.Column("id_doctor", sa.UUID(), nullable=False),
        sa.Column("id_paciente", sa.UUID(), nullable=False),
        sa.Column("fecha_hora_inicio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_hora_fin", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo_consulta", sa.Text(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "programada",
                "confirmada",
                "en_espera",
                "en_consulta",
                "atendida",
                "cancelada",
                "no_asistio",
                name="estadocita",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "estado_seguimiento",
            sa.Enum(
                "ninguno",
                "requiere_seguimiento",
                "seguimiento_agendado",
                name="estadoseguimiento",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column(
            "origen",
            sa.Enum("ia", "recepcion", name="origencita", native_enum=False, length=30),
            nullable=False,
        ),
        sa.Column("id_evento_google", sa.String(length=255), nullable=True),
        sa.Column(
            "estado_sync_google",
            sa.Enum(
                "pendiente",
                "sincronizado",
                "error",
                name="estadosyncgoogle",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
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
        postgresql.ExcludeConstraint(
            (sa.column("id_doctor"), "="),
            (sa.text("tstzrange(fecha_hora_inicio, fecha_hora_fin)"), "&&"),
            where=sa.text("estado <> 'cancelada' AND eliminado_en IS NULL"),
            using="gist",
            name="excl_cita_solapada",
        ),
        sa.CheckConstraint("fecha_hora_fin > fecha_hora_inicio", name="ck_cita_rango_valido"),
        sa.ForeignKeyConstraint(
            ["id_doctor"],
            ["doctor.id"],
        ),
        sa.ForeignKeyConstraint(
            ["id_paciente"],
            ["paciente.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cita_doctor_inicio", "cita", ["id_doctor", "fecha_hora_inicio"], unique=False
    )
    op.create_index(op.f("ix_cita_id_paciente"), "cita", ["id_paciente"], unique=False)
    op.create_table(
        "recordatorio",
        sa.Column("id_doctor", sa.UUID(), nullable=False),
        sa.Column("fecha_hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente",
                "enviado",
                "cancelado",
                name="estadorecordatorio",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["id_doctor"],
            ["doctor.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recordatorio_estado_fecha", "recordatorio", ["estado", "fecha_hora"], unique=False
    )


def downgrade() -> None:
    # btree_gist: necesario para el constraint de exclusion DAT-05 (igualdad de UUID en gist).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.drop_index("ix_recordatorio_estado_fecha", table_name="recordatorio")
    op.drop_table("recordatorio")
    op.drop_index(op.f("ix_cita_id_paciente"), table_name="cita")
    op.drop_index("ix_cita_doctor_inicio", table_name="cita")
    op.drop_table("cita")
    op.drop_index("ix_alerta_doctor_estado", table_name="alerta_recepcion")
    op.drop_table("alerta_recepcion")
    op.drop_index(
        "uq_usuario_recepcion_correo",
        table_name="usuario_recepcion",
        postgresql_where="eliminado_en IS NULL",
    )
    op.drop_table("usuario_recepcion")
    op.drop_index(op.f("ix_paciente_nombre_normalizado"), table_name="paciente")
    op.drop_table("paciente")
    op.drop_index("ix_log_auditoria_entidad", table_name="log_auditoria")
    op.drop_table("log_auditoria")
    op.drop_index(
        "uq_doctor_telefono_whatsapp", table_name="doctor", postgresql_where="eliminado_en IS NULL"
    )
    op.drop_table("doctor")
