"""Matriz de permisos: qué puede hacer cada rol en cada módulo. Vive en Oracle (tabla ``permisos``) y la edita
el administrador en «Roles y permisos».

Tres niveles: ``NINGUNO`` (no ve el módulo), ``CONSULTA`` (lo ve) y ``GESTION`` (además cambia datos). Las
vistas ocultan lo que el rol no puede ver (``puede``) y las funciones que cambian datos lo comprueban otra vez
(``exigir``): quitar un botón no basta.

El administrador conserva siempre ``GESTION`` en Usuarios, Solicitudes y Permisos (``INTOCABLES``): si no, un
cambio en la matriz podría dejar el sistema sin nadie que lo administre.
"""

from __future__ import annotations

from . import db
from .auth import ADMIN, INVENTARIO, OPERADOR, ROLES, ErrorDeAcceso, Sesion

NINGUNO, CONSULTA, GESTION = "NINGUNO", "CONSULTA", "GESTION"
NIVELES = (NINGUNO, CONSULTA, GESTION)
_ORDEN = {NINGUNO: 0, CONSULTA: 1, GESTION: 2}
NOMBRE_NIVEL = {NINGUNO: "Sin acceso", CONSULTA: "Consulta", GESTION: "Gestión"}

TABLA = "permisos"   # las pruebas apuntan a ``permisos_tst``

_N, _C, _G = NINGUNO, CONSULTA, GESTION
# (clave, nombre en pantalla, nivel inicial para ADMIN, INVENTARIO, OPERADOR): la matriz de la especificación.
_MATRIZ_INICIAL = (
    ("dashboard", "Dashboard", _G, _G, _C),
    ("usuarios", "Gestión de usuarios", _G, _N, _N),
    ("roles", "Asignación de roles", _G, _N, _N),
    ("permisos", "Gestión de permisos", _G, _N, _N),
    ("solicitudes", "Solicitudes pendientes", _G, _N, _N),
    ("productos_consulta", "Consulta global de productos", _C, _C, _C),
    ("productos", "Gestión operativa de productos", _N, _G, _N),
    ("categorias", "Categorías y almacenes", _C, _G, _C),
    ("existencias", "Existencias", _C, _G, _C),
    ("entradas_salidas", "Entradas y salidas", _C, _G, _N),
    ("movimientos", "Movimientos", _C, _G, _C),
    ("tareas", "Tareas de conteo", _C, _G, _G),
    ("conteos", "Conteos físicos", _C, _C, _G),
    ("diferencias", "Reportar diferencias", _C, _G, _G),
    ("ajustes", "Ajustes de inventario", _G, _G, _N),
    ("bluetooth", "Bluetooth", _G, _G, _G),
    ("reportes", "Analítica y reportes", _C, _C, _N),
    ("historial", "Historial", _C, _C, _C),
    ("configuracion", "Configuración general", _G, _N, _N),
    ("respaldos", "Respaldos", _G, _N, _N),
    ("perfil", "Perfil", _G, _G, _G),
)
MODULOS: tuple[tuple[str, str], ...] = tuple((clave, nombre) for clave, nombre, *_ in _MATRIZ_INICIAL)
_CLAVES = {clave for clave, _ in MODULOS}
INTOCABLES = frozenset({(ADMIN, "usuarios"), (ADMIN, "solicitudes"), (ADMIN, "permisos")})
# Módulos que ya existen en las aplicaciones (los demás llegan en fases siguientes: su nivel se guarda pero aún no rige).
EN_USO = ("dashboard", "usuarios", "roles", "permisos", "solicitudes", "existencias", "bluetooth", "reportes", "perfil",
          "categorias", "conteos")


def inicial(rol: str) -> dict[str, str]:
    """Los niveles de la matriz inicial para un rol (lo que la especificación pide)."""
    i = (ADMIN, INVENTARIO, OPERADOR).index(rol) if rol in (ADMIN, INVENTARIO, OPERADOR) else None
    return {} if i is None else {clave: niveles[i] for clave, _nombre, *niveles in _MATRIZ_INICIAL}


def alcanza(nivel_actual: str, minimo: str) -> bool:
    return _ORDEN.get(nivel_actual, 0) >= _ORDEN[minimo]


def de_rol(rol: str) -> tuple[tuple[str, str], ...]:
    """Los niveles guardados en Oracle para un rol, para llevarlos en la sesión."""
    m = matriz()
    return tuple((clave, m[(rol, clave)]) for clave, _ in MODULOS if (rol, clave) in m)


def nivel(rol: str, modulo: str) -> str:
    if (rol, modulo) in INTOCABLES:
        return GESTION
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT nivel FROM {TABLA} WHERE rol = :r AND modulo = :m", r=rol, m=modulo)
        fila = cur.fetchone()
    return fila[0] if fila else NINGUNO


def puede(rol: str, modulo: str, minimo: str = CONSULTA) -> bool:
    return alcanza(nivel(rol, modulo), minimo)


def matriz() -> dict[tuple[str, str], str]:
    """Toda la matriz: ``{(rol, modulo): nivel}`` para cada rol y cada módulo conocido."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol, modulo, nivel FROM {TABLA}")
        guardado = {(r, m): n for r, m, n in cur}
    return {(rol, clave): GESTION if (rol, clave) in INTOCABLES else guardado.get((rol, clave), NINGUNO)
            for rol in ROLES for clave, _ in MODULOS}


def exigir(quien: Sesion, modulo: str, minimo: str = GESTION) -> None:
    """Comprueba en vivo: la cuenta de ``quien`` debe seguir ACTIVO y su rol **actual** (no el de la sesión) debe
    alcanzar ``minimo`` en el módulo. Así un administrador suspendido o degradado pierde sus poderes al momento."""
    from . import auth
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol, estado FROM {auth.TABLA} WHERE usuario = :u", u=quien.usuario)
        fila = cur.fetchone()
    if fila is None or fila[1] != auth.ACTIVO or fila[0] is None or not puede(fila[0], modulo, minimo):
        raise ErrorDeAcceso("No tienes permiso para esto.")


def guardar(quien: Sesion, rol: str, modulo: str, nivel_nuevo: str) -> None:
    exigir(quien, "permisos")
    if rol not in ROLES or modulo not in _CLAVES or nivel_nuevo not in NIVELES:
        raise ErrorDeAcceso("Ese rol, módulo o nivel no existe.")
    if (rol, modulo) in INTOCABLES and nivel_nuevo != GESTION:
        raise ErrorDeAcceso("El administrador siempre gestiona usuarios, solicitudes y permisos.")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {TABLA} SET nivel = :n WHERE rol = :r AND modulo = :m", n=nivel_nuevo, r=rol, m=modulo)
        if cur.rowcount == 0:
            cur.execute(f"INSERT INTO {TABLA} (rol, modulo, nivel) VALUES (:r, :m, :n)", r=rol, m=modulo, n=nivel_nuevo)
        conn.commit()


def migrar() -> None:
    """Crea la tabla si falta y añade los valores iniciales de los módulos que no tengan fila. Es idempotente:
    nunca pisa lo que el administrador ya cambió."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
        if cur.fetchone()[0] == 0:
            cur.execute(f"""CREATE TABLE {TABLA} (
                rol    VARCHAR2(12 CHAR) NOT NULL,
                modulo VARCHAR2(30 CHAR) NOT NULL,
                nivel  VARCHAR2(10 CHAR) NOT NULL,
                CONSTRAINT pk_{TABLA} PRIMARY KEY (rol, modulo),
                CONSTRAINT ck_{TABLA}_nivel CHECK (nivel IN ('NINGUNO', 'CONSULTA', 'GESTION')))""")
        cur.execute(f"SELECT rol, modulo FROM {TABLA}")
        existentes = set(cur.fetchall())
        filas = [(rol, clave, nivel_inicial)
                 for clave, _nombre, *niveles in _MATRIZ_INICIAL
                 for rol, nivel_inicial in zip((ADMIN, INVENTARIO, OPERADOR), niveles)
                 if (rol, clave) not in existentes]
        if filas:
            cur.executemany(f"INSERT INTO {TABLA} (rol, modulo, nivel) VALUES (:1, :2, :3)", filas)
        conn.commit()
