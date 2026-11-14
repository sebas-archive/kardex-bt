"""Cuentas de la aplicación de escritorio: registro, inicio de sesión y roles.

Dos roles en el PC: ``ADMIN`` (todo: además cierra conteos, reprocesa y administra cuentas) e ``INVENTARIO``
(consulta, sincroniza y ve gráficas). Los clasificadores usan el celular y sus cuentas viven en el teléfono.

- La **primera cuenta** que se crea queda como ``ADMIN``. Las siguientes quedan **pendientes** (sin rol) hasta que
  un administrador les asigne uno en «Solicitudes»: nadie elige su propio rol.
- Quien olvidó su contraseña deja una **solicitud** (la nueva, ya con hash); el administrador la aprueba o la rechaza.
- La contraseña nunca se guarda en claro: PBKDF2-HMAC-SHA256 con sal por usuario
  (``pbkdf2-sha256$<vueltas>$<sal>$<derivada>``).
- Cinco fallos seguidos bloquean la cuenta 30 segundos.

Como todo lo que toca Oracle, estas funciones se llaman fuera del hilo de la interfaz. Los errores que debe ver
la persona llegan como ``ErrorDeAcceso`` con el mensaje listo para mostrar.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from . import db

ADMIN, INVENTARIO, OPERADOR = "ADMIN", "INVENTARIO", "OPERADOR"
ROLES = (ADMIN, INVENTARIO, OPERADOR)
NOMBRE_ROL = {ADMIN: "Administrador", INVENTARIO: "Inventario", OPERADOR: "Operador de Inventario", None: "Sin rol"}

PENDIENTE, ACTIVO, RECHAZADO, SUSPENDIDO = "PENDIENTE", "ACTIVO", "RECHAZADO", "SUSPENDIDO"
ESTADOS = (PENDIENTE, ACTIVO, RECHAZADO, SUSPENDIDO)
MAX_MOTIVO = 300

TABLA = "usuarios"          # las pruebas apuntan a una tabla aparte para no tocar las cuentas reales
ITERACIONES = 200_000
MAX_INTENTOS, BLOQUEO_S = 5, 30
_USUARIO = re.compile(r"[a-z0-9._-]{3,30}")


class ErrorDeAcceso(Exception):
    """Algo que la persona debe corregir o saber; el mensaje se muestra tal cual."""


class CuentaSinAcceso(ErrorDeAcceso):
    """La contraseña es correcta pero la cuenta no está ACTIVO: la interfaz muestra la pantalla de su estado."""

    def __init__(self, usuario: str, nombre: str, estado: str, motivo: str | None, registrado: datetime) -> None:
        super().__init__(f"Cuenta en estado {estado}.")
        self.usuario, self.nombre, self.estado, self.motivo, self.registrado = usuario, nombre, estado, motivo, registrado


@dataclass(frozen=True)
class Sesion:
    usuario: str
    nombre: str
    rol: str  # nunca None: quien no tiene rol no abre sesión
    # Niveles del rol al abrir la sesión ((modulo, nivel), ...), leídos de Oracle fuera del hilo de la interfaz:
    # la barra lateral los consulta sin tocar la base. None = la matriz inicial del rol (sesiones creadas a mano).
    permisos: tuple[tuple[str, str], ...] | None = field(default=None, compare=False, repr=False)

    @property
    def es_admin(self) -> bool:
        return self.rol == ADMIN

    def nivel(self, modulo: str) -> str:
        from . import permisos
        niveles = dict(self.permisos) if self.permisos is not None else permisos.inicial(self.rol)
        return permisos.GESTION if (self.rol, modulo) in permisos.INTOCABLES else niveles.get(modulo, permisos.NINGUNO)

    def puede(self, modulo: str, minimo: str = "CONSULTA") -> bool:
        from . import permisos
        return permisos.alcanza(self.nivel(modulo), minimo)


@dataclass(frozen=True)
class Usuario:
    usuario: str
    nombre: str
    rol: str | None            # None: cuenta nueva esperando que un administrador le asigne el rol
    estado: str
    motivo: str | None = None
    origen: str = "ESCRITORIO"
    clave_solicitada: bool = False   # pidió una contraseña nueva y el administrador no ha respondido
    registrado: datetime | None = None
    telefono: bool = False           # cuenta del celular ya vinculada a un teléfono


@dataclass(frozen=True)
class Solicitud:
    """Una solicitud de cuenta ya resuelta (aprobada o rechazada), para el historial."""
    usuario: str
    nombre: str
    estado: str
    rol: str | None
    motivo: str | None
    resuelto_por: str | None
    resuelto: datetime


# ------------------------------------------------------------------ contraseñas
def crear_hash(clave: str, iteraciones: int | None = None) -> str:
    iteraciones = iteraciones or ITERACIONES
    sal = os.urandom(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones)
    return "$".join(("pbkdf2-sha256", str(iteraciones), base64.b64encode(sal).decode(), base64.b64encode(derivada).decode()))


def verificar_hash(clave: str, guardado: str) -> bool:
    try:
        prefijo, iteraciones, sal, esperado = guardado.split("$")
        if prefijo != "pbkdf2-sha256":
            return False
        derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), base64.b64decode(sal), int(iteraciones))
        return hmac.compare_digest(derivada, base64.b64decode(esperado))  # comparación en tiempo constante
    except (ValueError, TypeError):
        return False


def fuerza(clave: str) -> int:
    """Qué tan fuerte es una contraseña, de 0 (vacía) a 4: largo y variedad de caracteres."""
    if not clave:
        return 0
    puntos = (len(clave) >= 8) + (len(clave) >= 12) + (any(c.islower() for c in clave) and any(c.isupper() for c in clave)) \
        + (any(c.isdigit() for c in clave) and any(c.isalpha() for c in clave)) + any(not c.isalnum() for c in clave)
    return min(4, puntos)


def _validar_clave(clave: str, confirmacion: str) -> None:
    if len(clave) < 8:
        raise ErrorDeAcceso("La contraseña necesita mínimo 8 caracteres.")
    if not (any(c.isalpha() for c in clave) and any(c.isdigit() for c in clave)):
        raise ErrorDeAcceso("La contraseña debe tener letras y números.")
    if clave != confirmacion:
        raise ErrorDeAcceso("Las dos contraseñas no coinciden.")


def _normalizar(usuario: str) -> str:
    return usuario.strip().lower()


# ------------------------------------------------------------------ registro e inicio de sesión
def registrar(usuario: str, nombre: str, clave: str, confirmacion: str) -> Sesion | None:
    """Crea la cuenta. La primera es ``ADMIN`` y devuelve su sesión; las demás quedan pendientes y devuelve ``None``."""
    alias, nombre = _normalizar(usuario), nombre.strip()
    if not _USUARIO.fullmatch(alias):
        raise ErrorDeAcceso("El usuario debe tener de 3 a 30 caracteres: letras, números, punto o guion.")
    if not nombre or len(nombre) > 60:
        raise ErrorDeAcceso("Escribe tu nombre completo (máximo 60 caracteres).")
    _validar_clave(clave, confirmacion)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"LOCK TABLE {TABLA} IN EXCLUSIVE MODE")  # dos registros a la vez no pueden quedar ambos como primeros
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE usuario = :u", u=alias)
        if cur.fetchone()[0]:
            conn.rollback()
            raise ErrorDeAcceso("Ese usuario ya existe.")
        # Primera cuenta = la primera del PC con rol ADMIN: las que llegan del celular (o de pruebas) no cuentan.
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE rol = :r AND origen = 'ESCRITORIO'", r=ADMIN)
        rol = ADMIN if cur.fetchone()[0] == 0 else None
        cur.execute(f"INSERT INTO {TABLA} (usuario, nombre, rol, clave_hash, estado) VALUES (:u, :n, :r, :h, :e)",
                    u=alias, n=nombre, r=rol, h=crear_hash(clave), e=ACTIVO if rol else PENDIENTE)
        conn.commit()
    return _sesion(alias, nombre, rol) if rol else None


def _sesion(usuario: str, nombre: str, rol: str) -> Sesion:
    """Abre la sesión con los permisos actuales de su rol (se llama fuera del hilo de la interfaz)."""
    from . import permisos
    return Sesion(usuario, nombre, rol, permisos.de_rol(rol))


def iniciar_sesion(usuario: str, clave: str) -> Sesion:
    alias = _normalizar(usuario)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT nombre, rol, clave_hash, estado, intentos, "
            f"CASE WHEN bloqueado_hasta > SYSTIMESTAMP THEN 1 ELSE 0 END, motivo, creado FROM {TABLA} WHERE usuario = :u", u=alias)
        fila = cur.fetchone()
        if fila is None:
            raise ErrorDeAcceso("Usuario o contraseña incorrectos.")  # el mismo mensaje: no revela qué cuentas existen
        nombre, rol, guardado, estado, intentos, bloqueada, motivo, creado = fila
        if bloqueada:
            raise ErrorDeAcceso(f"Demasiados intentos. Espera {BLOQUEO_S} segundos y vuelve a probar.")
        if not verificar_hash(clave, guardado):
            if intentos + 1 >= MAX_INTENTOS:
                cur.execute(f"UPDATE {TABLA} SET intentos = 0, bloqueado_hasta = SYSTIMESTAMP + NUMTODSINTERVAL(:s, 'SECOND') "
                            "WHERE usuario = :u", s=BLOQUEO_S, u=alias)
                conn.commit()
                raise ErrorDeAcceso(f"Demasiados intentos. Espera {BLOQUEO_S} segundos y vuelve a probar.")
            cur.execute(f"UPDATE {TABLA} SET intentos = intentos + 1 WHERE usuario = :u", u=alias)
            conn.commit()
            raise ErrorDeAcceso("Usuario o contraseña incorrectos.")
        cur.execute(f"UPDATE {TABLA} SET intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u", u=alias)
        conn.commit()
    if estado != ACTIVO or rol is None:
        raise CuentaSinAcceso(alias, nombre, estado, motivo, creado)
    if rol == OPERADOR:
        raise ErrorDeAcceso("Los operadores usan la app móvil.")
    return _sesion(alias, nombre, rol)


def consultar_cuenta(usuario: str) -> CuentaSinAcceso | None:
    """El estado de una cuenta, para mostrar su pantalla (p. ej. tras registrarse). ``None`` si no existe."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, estado, motivo, creado FROM {TABLA} WHERE usuario = :u", u=_normalizar(usuario))
        fila = cur.fetchone()
    return None if fila is None else CuentaSinAcceso(*fila)


def cambiar_clave(usuario: str, actual: str, nueva: str, confirmacion: str) -> None:
    alias = _normalizar(usuario)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT clave_hash FROM {TABLA} WHERE usuario = :u", u=alias)
        fila = cur.fetchone()
        if fila is None or not verificar_hash(actual, fila[0]):
            raise ErrorDeAcceso("La contraseña actual no es correcta.")
        _validar_clave(nueva, confirmacion)
        cur.execute(f"UPDATE {TABLA} SET clave_hash = :h WHERE usuario = :u", h=crear_hash(nueva), u=alias)
        conn.commit()


# ------------------------------------------------------------------ administración (solo ADMIN)
def listar() -> list[Usuario]:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, rol, estado, motivo, origen, clave_pendiente, creado, uuid_dispositivo "
                    f"FROM {TABLA} ORDER BY usuario")
        return [Usuario(r[0], r[1], r[2], r[3], r[4], r[5], r[6] is not None, r[7], r[8] is not None) for r in cur]


def _exigir(quien: Sesion, modulo: str) -> None:
    """Comprueba la matriz de permisos en Oracle (no solo el botón visible). Import tardío: permisos importa auth."""
    from . import permisos
    permisos.exigir(quien, modulo)


def _otros_admins_activos(cur, usuario: str) -> int:
    """Administradores que pueden entrar al PC (origen ESCRITORIO, ACTIVO), sin contar a ``usuario``."""
    cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE rol = :r AND estado = :e AND origen = 'ESCRITORIO' AND usuario <> :u",
                r=ADMIN, e=ACTIVO, u=usuario)
    return cur.fetchone()[0]


def _validar_rol(rol: str) -> None:
    if rol not in ROLES:
        raise ErrorDeAcceso("Ese rol no existe.")


ROLES_POR_ORIGEN = {"MOVIL": (OPERADOR,), "ESCRITORIO": (ADMIN, INVENTARIO)}


def _validar_rol_para(cur, usuario: str, rol: str) -> None:
    """Una cuenta del celular solo puede ser operador (no entra al PC); una del PC, administrador o inventario."""
    _validar_rol(rol)
    cur.execute(f"SELECT origen FROM {TABLA} WHERE usuario = :u", u=usuario)
    fila = cur.fetchone()
    if fila is None:
        raise ErrorDeAcceso("Esa cuenta no existe.")
    if rol not in ROLES_POR_ORIGEN.get(fila[0], ()):
        raise ErrorDeAcceso("Una cuenta del celular solo puede ser Operador de Inventario." if fila[0] == "MOVIL"
                            else "Una cuenta del PC solo puede ser Administrador o Inventario.")


def _validar_motivo(motivo: str) -> str:
    motivo = (motivo or "").strip()
    if not motivo:
        raise ErrorDeAcceso("Escribe el motivo.")
    if len(motivo) > MAX_MOTIVO:
        raise ErrorDeAcceso(f"El motivo puede tener máximo {MAX_MOTIVO} caracteres.")
    return motivo


def _transicion(cur, usuario: str, desde: str, cambios: str, **binds) -> None:
    """Aplica un cambio de estado solo si la cuenta sigue en ``desde``; si otro administrador se adelantó, avisa."""
    cur.execute(f"UPDATE {TABLA} SET {cambios} WHERE usuario = :u AND estado = :desde", u=usuario, desde=desde, **binds)
    if cur.rowcount == 0:
        raise ErrorDeAcceso("Esta solicitud ya fue resuelta.")


def cambiar_rol(quien: Sesion, usuario: str, rol: str) -> None:
    """Cambia el rol de una cuenta ya ACTIVO (las pendientes se aprueban con ``aprobar``)."""
    _exigir(quien, "roles")
    with db._conexion() as conn:
        cur = conn.cursor()
        _validar_rol_para(cur, usuario, rol)
        if rol != ADMIN and _otros_admins_activos(cur, usuario) == 0:
            raise ErrorDeAcceso("Es el único administrador: nombra otro antes de cambiarle el rol.")
        _transicion(cur, usuario, ACTIVO, "rol = :r", r=rol)
        conn.commit()


def aprobar(quien: Sesion, usuario: str, rol: str) -> None:
    _exigir(quien, "solicitudes")
    with db._conexion() as conn:
        cur = conn.cursor()
        _validar_rol_para(cur, usuario, rol)
        _transicion(cur, usuario, PENDIENTE, "estado = :e, rol = :r, motivo = NULL, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=ACTIVO, r=rol, q=quien.usuario)
        conn.commit()


def rechazar(quien: Sesion, usuario: str, motivo: str) -> None:
    _exigir(quien, "solicitudes")
    motivo = _validar_motivo(motivo)
    with db._conexion() as conn:
        cur = conn.cursor()
        _transicion(cur, usuario, PENDIENTE, "estado = :e, motivo = :m, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=RECHAZADO, m=motivo, q=quien.usuario)
        conn.commit()


def suspender(quien: Sesion, usuario: str, motivo: str) -> None:
    _exigir(quien, "usuarios")
    motivo = _validar_motivo(motivo)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol FROM {TABLA} WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
        if fila and fila[0] == ADMIN and _otros_admins_activos(cur, usuario) == 0:
            raise ErrorDeAcceso("Es el único administrador: no se puede suspender.")
        _transicion(cur, usuario, ACTIVO, "estado = :e, motivo = :m, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=SUSPENDIDO, m=motivo, q=quien.usuario)
        conn.commit()


def reactivar(quien: Sesion, usuario: str) -> None:
    _exigir(quien, "usuarios")
    with db._conexion() as conn:
        cur = conn.cursor()
        _transicion(cur, usuario, SUSPENDIDO, "estado = :e, motivo = NULL, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=ACTIVO, q=quien.usuario)
        conn.commit()


def desvincular_telefono(quien: Sesion, usuario: str) -> None:
    """Suelta la cuenta del celular de su teléfono (p. ej. lo cambió o reinstaló la app): el próximo que sincronice la toma."""
    _exigir(quien, "usuarios")
    with db._conexion() as conn:
        conn.cursor().execute(f"UPDATE {TABLA} SET uuid_dispositivo = NULL WHERE usuario = :u AND origen = 'MOVIL'", u=usuario)
        conn.commit()


def historial_solicitudes() -> list[Solicitud]:
    """Solicitudes de cuenta ya resueltas (aprobadas o rechazadas), la más reciente primero."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, estado, rol, motivo, resuelto_por, resuelto FROM {TABLA} "
                    "WHERE resuelto IS NOT NULL AND estado IN (:a, :r) ORDER BY resuelto DESC", a=ACTIVO, r=RECHAZADO)
        return [Solicitud(*fila) for fila in cur]


def restablecer_clave(quien: Sesion, usuario: str, nueva: str) -> None:
    """Un administrador pone una contraseña nueva a otra cuenta (quien la olvidó) y le quita el bloqueo."""
    _exigir(quien, "usuarios")
    _validar_clave(nueva, nueva)
    with db._conexion() as conn:
        conn.cursor().execute(
            f"UPDATE {TABLA} SET clave_hash = :h, intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u",
            h=crear_hash(nueva), u=usuario)
        conn.commit()


# ------------------------------------------------------------------ solicitudes
def solicitar_clave(usuario: str, nueva: str, confirmacion: str) -> str:
    """Quien olvidó su contraseña deja la nueva (ya con hash) para que un administrador la apruebe.

    Responde lo mismo exista o no la cuenta: así no se descubre qué usuarios hay.
    """
    _validar_clave(nueva, confirmacion)
    with db._conexion() as conn:
        conn.cursor().execute(f"UPDATE {TABLA} SET clave_pendiente = :h WHERE usuario = :u AND estado = 'ACTIVO'",
                              h=crear_hash(nueva), u=_normalizar(usuario))
        conn.commit()
    return "Solicitud enviada. Cuando un administrador la apruebe, entra con la contraseña nueva."


def resolver_clave(quien: Sesion, usuario: str, aprobar: bool) -> None:
    """Aprueba (la contraseña pedida pasa a ser la de la cuenta y se desbloquea) o rechaza la solicitud."""
    _exigir(quien, "solicitudes")
    with db._conexion() as conn:
        cur = conn.cursor()
        if aprobar:
            cur.execute(f"UPDATE {TABLA} SET clave_hash = clave_pendiente, clave_pendiente = NULL, intentos = 0, "
                        "bloqueado_hasta = NULL WHERE usuario = :u AND clave_pendiente IS NOT NULL", u=usuario)
        else:
            cur.execute(f"UPDATE {TABLA} SET clave_pendiente = NULL WHERE usuario = :u", u=usuario)
        conn.commit()


# ------------------------------------------------------------------ esquema
_COLUMNAS_NUEVAS = (
    ("CLAVE_PENDIENTE", "clave_pendiente VARCHAR2(200 CHAR)"),
    ("ESTADO", "estado VARCHAR2(10 CHAR) DEFAULT 'PENDIENTE' NOT NULL"),
    ("MOTIVO", "motivo VARCHAR2(300 CHAR)"),
    ("RESUELTO_POR", "resuelto_por VARCHAR2(30 CHAR)"),
    ("RESUELTO", "resuelto TIMESTAMP"),
    ("ORIGEN", "origen VARCHAR2(10 CHAR) DEFAULT 'ESCRITORIO' NOT NULL"),
    ("UUID_DISPOSITIVO", "uuid_dispositivo VARCHAR2(50 CHAR)"),
)
_CHECK_ROL = "rol IS NULL OR rol IN ('ADMIN', 'INVENTARIO', 'OPERADOR')"
_CHECK_ESTADO = "estado IN ('PENDIENTE', 'ACTIVO', 'RECHAZADO', 'SUSPENDIDO')"


def migrar() -> None:
    """Pone al día una tabla creada con un esquema anterior. Es idempotente.

    Añade las columnas que falten, convierte ``activo`` en ``estado`` (sin rol → PENDIENTE, ``N`` → SUSPENDIDO,
    el resto → ACTIVO), borra ``activo`` y deja los ``CHECK`` de rol (con OPERADOR) y de estado.
    """
    tabla = TABLA.upper()
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = :t", t=tabla)
        columnas = {fila[0] for fila in cur}
        for nombre, definicion in _COLUMNAS_NUEVAS:
            if nombre not in columnas:
                db.ddl_tolerante(cur, f"ALTER TABLE {TABLA} ADD ({definicion})")
        cur.execute("SELECT nullable FROM user_tab_columns WHERE table_name = :t AND column_name = 'ROL'", t=tabla)
        if cur.fetchone()[0] == "N":
            db.ddl_tolerante(cur, f"ALTER TABLE {TABLA} MODIFY (rol NULL)")
        if "ACTIVO" in columnas:
            # Mientras exista ACTIVO la conversión no se hizo (se borra justo después): aunque un arranque anterior
            # alcanzara a crear ESTADO y fallara, aquí se convierte igual y nadie queda PENDIENTE por error.
            try:   # otro escritorio que arranca a la vez pudo convertirla y borrar ACTIVO un instante antes
                cur.execute(f"UPDATE {TABLA} SET estado = CASE WHEN rol IS NULL THEN 'PENDIENTE' "
                            "WHEN activo = 'N' THEN 'SUSPENDIDO' ELSE 'ACTIVO' END")
            except Exception as exc:
                if "ORA-00904" not in str(exc):
                    raise
            db.ddl_tolerante(cur, f"ALTER TABLE {TABLA} DROP COLUMN activo", tambien=("ORA-00904",))   # y su CHECK
        cur.execute("SELECT constraint_name, search_condition FROM user_constraints WHERE table_name = :t "
                    "AND constraint_type = 'C' AND constraint_name LIKE 'CK%'", t=tabla)
        checks = {nombre: condicion for nombre, condicion in cur.fetchall()}
        for sufijo, condicion in (("ROL", _CHECK_ROL), ("ESTADO", _CHECK_ESTADO)):
            existentes = [n for n in checks if n.endswith(sufijo)]
            if existentes and all(checks[n] == condicion for n in existentes):
                continue
            for nombre in existentes:
                db.ddl_tolerante(cur, f"ALTER TABLE {TABLA} DROP CONSTRAINT {nombre}", tambien=("ORA-02443",))
            db.ddl_tolerante(cur, f"ALTER TABLE {TABLA} ADD CONSTRAINT ck_{TABLA}_{sufijo.lower()} CHECK ({condicion})")
        conn.commit()
