"""Utilidades de linea de comandos.

python -m app.cli crear-admin --nombre "Admin" --correo admin@cree.mx
"""

import argparse
import asyncio
import getpass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import obtener_config
from app.core.seguridad import hash_password
from app.db.sesion import obtener_fabrica_sesiones
from app.integraciones.gemini.ejecutor import MENSAJE_DELEGACION
from app.modelos.doctor import Doctor
from app.modelos.enums import EstadoCita, OrigenCita, RolUsuario
from app.modelos.usuario_recepcion import UsuarioRecepcion
from app.repositorios import auditoria
from app.repositorios import usuarios as repo
from app.servicios import agenda, alertas
from app.servicios import pacientes as servicio_pacientes


async def crear_admin(nombre: str, correo: str, password: str) -> None:
    async with obtener_fabrica_sesiones()() as sesion:
        if await repo.obtener_por_correo(sesion, correo):
            raise SystemExit("Ya existe un usuario con ese correo")
        usuario = UsuarioRecepcion(
            nombre=nombre,
            correo=correo.strip().lower(),
            hash_password=hash_password(password),
            rol=RolUsuario.ADMIN,
        )
        sesion.add(usuario)
        await sesion.flush()
        await auditoria.registrar(
            sesion,
            entidad="usuario_recepcion",
            id_entidad=usuario.id,
            accion="crear",
            actor=auditoria.ACTOR_SISTEMA,
            cambios={"rol": RolUsuario.ADMIN},
        )
        await sesion.commit()
    print("Usuario admin creado")


_DEMO_PACIENTES = [
    ("Ana López Herrera", "Control posoperatorio", "Alergia a penicilina."),
    ("Carlos Peña Ruiz", "Dolor lumbar", None),
    ("María Fernanda Soto", "Revisión de estudios", "Hipertensión controlada."),
    ("Jorge Luis Medina", "Primera consulta", None),
    ("Lucía Navarro Vega", "Seguimiento", "Diabetes tipo 2."),
    ("Roberto Díaz Campos", "Valoración", None),
]
_DEMO_ESTADOS = [
    EstadoCita.ATENDIDA,
    EstadoCita.ATENDIDA,
    EstadoCita.EN_CONSULTA,
    EstadoCita.EN_ESPERA,
    EstadoCita.CONFIRMADA,
    EstadoCita.PROGRAMADA,
]


async def datos_demo() -> None:
    """Carga datos ficticios para revisar la UI. Nunca en produccion."""
    if obtener_config().entorno == "produccion":
        raise SystemExit("datos-demo no se ejecuta en produccion")
    actor = auditoria.ACTOR_SISTEMA
    async with obtener_fabrica_sesiones()() as sesion:
        if await repo.obtener_por_correo(sesion, "recepcion@cree.demo"):
            raise SystemExit("Los datos de demostracion ya existen")
        sesion.add(
            UsuarioRecepcion(
                nombre="Laura Méndez",
                correo="recepcion@cree.demo",
                hash_password=hash_password("demo-cree-2026"),
                rol=RolUsuario.ADMIN,
            )
        )
        doctores = [
            Doctor(nombre="Dra. Elena Ruiz", telefono_whatsapp="+525500000001"),
            Doctor(nombre="Dr. Luis Vega", telefono_whatsapp="+525500000002"),
            Doctor(
                nombre="Dra. Sofía Marín",
                telefono_whatsapp="+526640000003",
                zona_horaria="America/Tijuana",
            ),
        ]
        sesion.add_all(doctores)
        await sesion.flush()
        pacientes = [
            await servicio_pacientes.crear(
                sesion,
                {
                    "nombre_completo": n,
                    "telefono": f"+52551000{i:04d}",
                    "notas_clinicas_breves": notas,
                },
                actor,
            )
            for i, (n, _, notas) in enumerate(_DEMO_PACIENTES)
        ]
        for d, doctor in enumerate(doctores):
            tz = ZoneInfo(doctor.zona_horaria)
            hoy = datetime.now(tz).date()
            for i in range(len(pacientes)):
                indice = (i + d * 2) % len(pacientes)
                inicio = datetime.combine(hoy, time(9 + i + (i > 2), 30 * (d % 2)), tzinfo=tz)
                cita = await agenda.crear_cita(
                    sesion,
                    doctor=doctor,
                    id_paciente=pacientes[indice].id,
                    inicio=inicio,
                    fin=inicio + timedelta(minutes=30 if i % 3 else 45),
                    motivo=_DEMO_PACIENTES[indice][1],
                    origen=OrigenCita.IA if i % 2 else OrigenCita.RECEPCION,
                    actor=actor,
                )
                cita.estado = _DEMO_ESTADOS[i]
        for doctor, instruccion in (
            (doctores[0], "Cancela la cita de Carlos Peña del jueves y avísale por teléfono"),
            (
                doctores[1],
                "Mueve a Lucía Navarro para la próxima semana, cualquier día en la tarde",
            ),
            (doctores[2], "Agenda a Ana mañana a las 10"),
        ):
            await alertas.crear(
                sesion,
                id_doctor=doctor.id,
                mensaje_ia=MENSAJE_DELEGACION,
                instruccion_original=instruccion,
                actor=auditoria.actor_ia(doctor.id),
            )
        await sesion.commit()
    print("Datos de demostracion cargados. Usuario: recepcion@cree.demo / demo-cree-2026")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)
    admin = sub.add_parser("crear-admin", help="Crea el primer usuario administrador")
    admin.add_argument("--nombre", required=True)
    admin.add_argument("--correo", required=True)
    admin.add_argument("--password", help="Si se omite, se pide por teclado")
    sub.add_parser("datos-demo", help="Carga datos ficticios (solo desarrollo)")
    args = parser.parse_args()
    if args.comando == "datos-demo":
        asyncio.run(datos_demo())
        return
    password = args.password or getpass.getpass("Password (min. 8 caracteres): ")
    if len(password) < 8:
        raise SystemExit("El password debe tener al menos 8 caracteres")
    asyncio.run(crear_admin(args.nombre, args.correo, password))


if __name__ == "__main__":
    main()
