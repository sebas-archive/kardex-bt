"""Crea (o restablece) las cuentas de prueba del PC: una por rol. Es idempotente.

Uso:  docker compose exec app python /work/desktop/scripts/crear_usuarios_prueba.py
Las cuentas del celular se crean desde la APK y llegan PENDIENTES al sincronizar (se aprueban en «Solicitudes»).
"""
from app import auth, db

CUENTAS = (
    ("admin.prueba", "Administrador de Prueba", auth.ADMIN, "Admin12345"),
    ("inventario.prueba", "Inventario de Prueba", auth.INVENTARIO, "Inventa12345"),
)

with db._conexion() as conn:
    cur = conn.cursor()
    for usuario, nombre, rol, clave in CUENTAS:
        cur.execute(f"DELETE FROM {auth.TABLA} WHERE usuario = :u", u=usuario)
        cur.execute(f"INSERT INTO {auth.TABLA} (usuario, nombre, rol, clave_hash, estado) VALUES (:u, :n, :r, :h, 'ACTIVO')",
                    u=usuario, n=nombre, r=rol, h=auth.crear_hash(clave))
        print(f"{rol:11} {usuario} / {clave}")
    conn.commit()
