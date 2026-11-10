"""Utilidades de linea de comandos.

python -m app.cli crear-admin --nombre "Admin" --correo admin@cree.mx
"""

import argparse
import asyncio
import getpass

from app.core.seguridad import hash_password
from app.db.sesion import obtener_fabrica_sesiones
from app.modelos.enums import RolUsuario
from app.modelos.usuario_recepcion import UsuarioRecepcion
from app.repositorios import auditoria
from app.repositorios import usuarios as repo


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


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)
    admin = sub.add_parser("crear-admin", help="Crea el primer usuario administrador")
    admin.add_argument("--nombre", required=True)
    admin.add_argument("--correo", required=True)
    admin.add_argument("--password", help="Si se omite, se pide por teclado")
    args = parser.parse_args()
    password = args.password or getpass.getpass("Password (min. 8 caracteres): ")
    if len(password) < 8:
        raise SystemExit("El password debe tener al menos 8 caracteres")
    asyncio.run(crear_admin(args.nombre, args.correo, password))


if __name__ == "__main__":
    main()
