"""Matriz de permisos: qué puede hacer cada rol en cada módulo. Vive en Oracle (``permisos``) y la edita
el Administrador en «Roles y permisos».

Tres niveles: ``NINGUNO`` (no ve el módulo), ``CONSULTA`` (lo ve) y ``GESTION`` (además cambia datos). Las
vistas ocultan lo que el rol no puede ver (``puede``) y las funciones que cambian datos lo comprueban otra vez
(``exigir``): quitar un botón no basta.

El Administrador conserva siempre ``GESTION`` en los doce módulos y su fila está bloqueada entera: si no, un
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
    ("dashboard", "Dashboard", _G, _G, _N),
    ("inventario", "Inventario", _G, _G, _N),
    ("graficas", "Gráficas", _G, _G, _N),
    ("sync", "Sincronización", _G, _G, _G),
    ("notificaciones", "Notificaciones", _G, _G, _C),
    ("perfil", "Perfil", _G, _G, _N),
    ("solicitudes", "Solicitudes", _G, _N, _N),
    ("usuarios", "Empleados", _G, _N, _N),
    ("permisos", "Roles y permisos", _G, _N, _N),
    ("auditoria", "Auditoría", _G, _N, _N),
    ("configuracion", "Configuración", _G, _N, _N),
    ("respaldos", "Respaldos", _G, _N, _N),
)
MODULOS: tuple[tuple[str, str], ...] = tuple((clave, nombre) for clave, nombre, *_ in _MATRIZ_INICIAL)
_CLAVES = {clave for clave, _ in MODULOS}
INTOCABLES = frozenset((ADMIN, clave) for clave, _ in MODULOS)
EN_USO = tuple(clave for clave, _ in MODULOS)


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
    alcanzar ``minimo`` en el módulo. Así un administrador degradado pierde sus poderes al momento."""
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
    if rol == ADMIN:
        raise ErrorDeAcceso("La fila del Administrador está bloqueada: siempre tiene Gestión.")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT nivel FROM {TABLA} WHERE rol = :r AND modulo = :m", r=rol, m=modulo)
        fila = cur.fetchone()
        anterior = fila[0] if fila else NINGUNO
        cur.execute(f"UPDATE {TABLA} SET nivel = :n WHERE rol = :r AND modulo = :m", n=nivel_nuevo, r=rol, m=modulo)
        if cur.rowcount == 0:
            cur.execute(f"INSERT INTO {TABLA} (rol, modulo, nivel) VALUES (:r, :m, :n)", r=rol, m=modulo, n=nivel_nuevo)
        from . import auditoria
        from .auth import NOMBRE_ROL
        nombre_modulo = dict(MODULOS)[modulo]
        auditoria.registrar(cur, quien.usuario, "permisos", "Cambió permiso",
                            f"{NOMBRE_ROL[rol]} · {nombre_modulo}: {NOMBRE_NIVEL[anterior]} → {NOMBRE_NIVEL[nivel_nuevo]}")
        conn.commit()


def _existe_tabla(cur) -> bool:
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
    return cur.fetchone()[0] > 0


def _filas_existentes(cur) -> set[tuple[str, str]]:
    cur.execute(f"SELECT rol, modulo FROM {TABLA}")
    return set(cur.fetchall())


def migrar() -> None:
    """Crea la tabla si falta, borra los módulos que ya no existen y añade los valores iniciales que falten.

    Es idempotente: nunca pisa lo que el administrador ya cambió, y aguanta que otro escritorio esté haciendo lo
    mismo a la vez.
    """
    with db._conexion() as conn:
        cur = conn.cursor()
        if not _existe_tabla(cur):
            db.ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
                rol    VARCHAR2(12 CHAR) NOT NULL,
                modulo VARCHAR2(30 CHAR) NOT NULL,
                nivel  VARCHAR2(10 CHAR) NOT NULL,
                CONSTRAINT pk_{TABLA} PRIMARY KEY (rol, modulo),
                CONSTRAINT ck_{TABLA}_nivel CHECK (nivel IN ('NINGUNO', 'CONSULTA', 'GESTION')))""")
        # Los módulos retirados no deben quedar en la tabla (la pantalla solo muestra los doce actuales).
        cur.execute(f"DELETE FROM {TABLA} WHERE modulo NOT IN ({', '.join(f':m{i}' for i in range(len(_CLAVES)))})",
                    **{f"m{i}": clave for i, clave in enumerate(_CLAVES)})
        existentes = _filas_existentes(cur)
        filas = [(rol, clave, nivel_inicial)
                 for clave, _nombre, *niveles in _MATRIZ_INICIAL
                 for rol, nivel_inicial in zip((ADMIN, INVENTARIO, OPERADOR), niveles)
                 if (rol, clave) not in existentes]
        if filas:
            # Si otro escritorio insertó alguna a la vez, su ORA-00001 se ignora: la fila ya está (y no se pisa).
            cur.executemany(f"INSERT INTO {TABLA} (rol, modulo, nivel) VALUES (:1, :2, :3)", filas, batcherrors=True)
            otros = [e for e in cur.getbatcherrors() if "ORA-00001" not in e.message]
            if otros:
                raise RuntimeError(otros[0].message)
        conn.commit()
