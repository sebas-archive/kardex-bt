"""Cuentas de la aplicación de escritorio: registro, inicio de sesión, roles y preferencias.

Tres roles: ``ADMIN`` (el único administrador), ``INVENTARIO`` (consulta, sincroniza, gráficas) y ``OPERADOR``
(cuentas del celular; no entran al PC).

- La **primera cuenta** del PC queda como ``ADMIN`` y activa; las demás quedan **pendientes** hasta que el
  Administrador las apruebe como ``INVENTARIO``. No se pueden crear más administradores.
- El correo es obligatorio en las cuentas del PC y opcional en las del celular. El login sigue siendo por usuario.
- Solo el Administrador tiene pregunta y respuesta de seguridad, y con ella recupera su contraseña desde Acceso.
- Quien olvidó su contraseña (Inventario) deja una **solicitud** con la nueva ya cifrada; el Administrador la
  aprueba o la rechaza con motivo.
- Cambiar la contraseña desde Perfil: el Administrador la cambia directo; Inventario deja la solicitud pendiente.
- La contraseña nunca se guarda en claro: PBKDF2-HMAC-SHA256 con sal por usuario
  (``pbkdf2-sha256$<vueltas>$<sal>$<derivada>``).
- Cinco fallos seguidos bloquean la cuenta 30 segundos; el mensaje de login es siempre el mismo.

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

from btsync import notificaciones

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
_CORREO = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_TEMAS = ("claro", "sistema", "oscuro")
_IDIOMAS = ("es", "en")

MENSAJE_LOGIN = "Usuario o contraseña incorrectos."

PREGUNTAS = (
    "¿Cuál es el nombre de tu primera mascota?",
    "¿En qué ciudad naciste?",
    "¿Cuál es el nombre de tu mejor amigo de la infancia?",
    "¿Cuál fue tu primer colegio?",
    "¿Cuál es tu comida favorita?",
)


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
    correo: str | None = field(default=None, compare=False)
    foto: str | None = field(default=None, compare=False)
    tema: str = field(default="sistema", compare=False)
    idioma: str = field(default="es", compare=False)
    aviso_clave: str | None = field(default=None, compare=False)   # motivo de una solicitud de contraseña rechazada

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
    correo: str | None = None
    foto: str | None = None
    tema: str = "sistema"
    idioma: str = "es"
    motivo_clave: str | None = None


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


def _normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower()


def _normalizar_respuesta(respuesta: str) -> str:
    return " ".join((respuesta or "").strip().lower().split())


def _validar_correo(correo: str) -> str:
    correo = _normalizar_correo(correo)
    if not correo or len(correo) > 120 or not _CORREO.fullmatch(correo):
        raise ErrorDeAcceso("El correo no es válido.")
    return correo


def _validar_pregunta(pregunta: str, respuesta: str) -> tuple[str, str]:
    pregunta = (pregunta or "").strip()
    respuesta = _normalizar_respuesta(respuesta)
    if pregunta not in PREGUNTAS:
        raise ErrorDeAcceso("Elige una pregunta de seguridad.")
    if len(respuesta) < 2:
        raise ErrorDeAcceso("Escribe la respuesta de seguridad.")
    return pregunta, respuesta


# ------------------------------------------------------------------ registro e inicio de sesión
def hay_admin() -> bool:
    """Si ya existe el Administrador (una cuenta del PC con rol ADMIN, en cualquier estado)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE rol = :r AND origen = 'ESCRITORIO'", r=ADMIN)
        return cur.fetchone()[0] > 0


def registrar(usuario: str, nombre: str, clave: str, confirmacion: str, correo: str = "",
              pregunta: str = "", respuesta: str = "") -> Sesion | None:
    """Crea la cuenta. La primera es el único ``ADMIN`` y devuelve su sesión; las demás quedan pendientes."""
    alias, nombre = _normalizar(usuario), nombre.strip()
    if not _USUARIO.fullmatch(alias):
        raise ErrorDeAcceso("El usuario debe tener de 3 a 30 caracteres: letras, números, punto o guion.")
    if not nombre or len(nombre) > 60:
        raise ErrorDeAcceso("Escribe tu nombre completo (máximo 60 caracteres).")
    correo = _validar_correo(correo)
    _validar_clave(clave, confirmacion)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"LOCK TABLE {TABLA} IN EXCLUSIVE MODE")  # dos registros a la vez no pueden quedar ambos como primeros
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE usuario = :u", u=alias)
        if cur.fetchone()[0]:
            conn.rollback()
            raise ErrorDeAcceso("Ese usuario ya existe.")
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE LOWER(correo) = :c", c=correo)
        if cur.fetchone()[0]:
            conn.rollback()
            raise ErrorDeAcceso("Ese correo ya está en uso.")
        # Primera cuenta = la primera del PC con rol ADMIN: las que llegan del celular no cuentan.
        cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE rol = :r AND origen = 'ESCRITORIO'", r=ADMIN)
        primero = cur.fetchone()[0] == 0
        pregunta_hash = None
        if primero:
            pregunta, respuesta = _validar_pregunta(pregunta, respuesta)
            pregunta_hash = crear_hash(respuesta)
        else:
            pregunta = None
        cur.execute(
            f"INSERT INTO {TABLA} (usuario, nombre, correo, rol, clave_hash, estado, origen, pregunta, respuesta_hash, tema, idioma) "
            "VALUES (:u, :n, :c, :r, :h, :e, 'ESCRITORIO', :p, :ph, 'sistema', 'es')",
            u=alias, n=nombre, c=correo, r=ADMIN if primero else None, h=crear_hash(clave),
            e=ACTIVO if primero else PENDIENTE, p=pregunta, ph=pregunta_hash)
        if not primero:   # queda pendiente: el administrador recibe el aviso (se resuelve en «Solicitudes»)
            notificaciones.crear(cur, "SOLICITUD", f"Nueva solicitud de cuenta: {nombre}", "Solicitudes", rol=ADMIN)
        conn.commit()
    if not primero:
        return None
    return Sesion(alias, nombre, ADMIN, permisos=None, correo=correo)


def _sesion_fila(usuario: str, nombre: str, rol: str, correo: str | None, foto: str | None,
                 tema: str | None, idioma: str | None, aviso: str | None = None) -> Sesion:
    from . import permisos
    return Sesion(usuario, nombre, rol, permisos.de_rol(rol), correo, foto, tema or "sistema", idioma or "es", aviso)


def _auditar(cur, usuario: str, modulo: str, accion: str, detalle: str = "") -> None:
    from . import auditoria   # aquí y no arriba: auditoria importa este módulo
    auditoria.registrar(cur, usuario, modulo, accion, detalle)


def iniciar_sesion(usuario: str, clave: str) -> Sesion:
    alias = _normalizar(usuario)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT nombre, rol, clave_hash, estado, intentos, "
            f"CASE WHEN bloqueado_hasta > SYSTIMESTAMP THEN 1 ELSE 0 END, motivo, creado, correo, foto, tema, idioma, clave_motivo "
            f"FROM {TABLA} WHERE usuario = :u", u=alias)
        fila = cur.fetchone()
        if fila is None:
            _auditar(cur, alias, "acceso", "Inicio de sesión fallido", "usuario inexistente")
            conn.commit()
            raise ErrorDeAcceso(MENSAJE_LOGIN)
        (nombre, rol, guardado, estado, intentos, bloqueada, motivo, creado,
         correo, foto, tema, idioma, aviso_clave) = fila
        if bloqueada:
            _auditar(cur, alias, "acceso", "Inicio de sesión fallido", "bloqueada por intentos")
            conn.commit()
            raise ErrorDeAcceso(MENSAJE_LOGIN)
        if not verificar_hash(clave, guardado):
            if intentos + 1 >= MAX_INTENTOS:
                cur.execute(f"UPDATE {TABLA} SET intentos = 0, bloqueado_hasta = SYSTIMESTAMP + NUMTODSINTERVAL(:s, 'SECOND') "
                            "WHERE usuario = :u", s=BLOQUEO_S, u=alias)
                _auditar(cur, alias, "acceso", "Inicio de sesión fallido", "contraseña incorrecta; queda bloqueada")
                conn.commit()
                raise ErrorDeAcceso(MENSAJE_LOGIN)
            cur.execute(f"UPDATE {TABLA} SET intentos = intentos + 1 WHERE usuario = :u", u=alias)
            _auditar(cur, alias, "acceso", "Inicio de sesión fallido", "contraseña incorrecta")
            conn.commit()
            raise ErrorDeAcceso(MENSAJE_LOGIN)
        cur.execute(f"UPDATE {TABLA} SET intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u", u=alias)
        if estado != ACTIVO or rol is None:
            if rol == ADMIN:   # el Administrador nunca pasa por Estado de cuenta
                _auditar(cur, alias, "acceso", "Inicio de sesión rechazado", "administrador no activo")
                conn.commit()
                raise ErrorDeAcceso(MENSAJE_LOGIN)
            _auditar(cur, alias, "acceso", "Inicio de sesión rechazado", f"cuenta {estado.lower()}")
            conn.commit()
            raise CuentaSinAcceso(alias, nombre, estado, motivo, creado)
        if rol == OPERADOR:
            _auditar(cur, alias, "acceso", "Inicio de sesión rechazado", "operador: usa la app móvil")
            conn.commit()
            raise ErrorDeAcceso("Los operadores usan la app móvil.")
        _auditar(cur, alias, "acceso", "Inicio de sesión")
        conn.commit()
    return _sesion_fila(alias, nombre, rol, correo, foto, tema, idioma, aviso_clave)


def consultar_cuenta(usuario: str) -> CuentaSinAcceso | None:
    """El estado de una cuenta, para mostrar su pantalla (p. ej. tras registrarse). ``None`` si no existe."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, estado, motivo, creado FROM {TABLA} WHERE usuario = :u", u=_normalizar(usuario))
        fila = cur.fetchone()
    return None if fila is None else CuentaSinAcceso(*fila)


def consumir_aviso_clave(usuario: str) -> None:
    """El motivo de una solicitud rechazada se muestra una vez; después se borra."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {TABLA} SET clave_motivo = NULL WHERE usuario = :u", u=usuario)
        conn.commit()


def pregunta_de(usuario: str) -> str | None:
    """La pregunta de seguridad solo existe para el Administrador; para el resto, ``None``."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol, pregunta FROM {TABLA} WHERE usuario = :u", u=_normalizar(usuario))
        fila = cur.fetchone()
    return fila[1] if fila is not None and fila[0] == ADMIN else None


def recuperar(usuario: str, nueva: str, confirmacion: str, respuesta: str = "") -> str:
    """Recuperación desde Acceso. El Administrador responde su pregunta; Inventario deja una solicitud.

    No se revela si la cuenta existe: para cuentas que no son del Administrador la respuesta es la misma.
    """
    alias = _normalizar(usuario)
    _validar_clave(nueva, confirmacion)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol, origen, estado, respuesta_hash FROM {TABLA} WHERE usuario = :u", u=alias)
        fila = cur.fetchone()
        if fila is None:
            return "Solicitud enviada. Un administrador la revisará."
        rol, origen, estado, respuesta_hash = fila
        if rol == ADMIN:
            if not respuesta_hash or not verificar_hash(_normalizar_respuesta(respuesta), respuesta_hash):
                raise ErrorDeAcceso("La respuesta de seguridad no es correcta.")
            cur.execute(f"UPDATE {TABLA} SET clave_hash = :h, clave_pendiente = NULL, clave_motivo = NULL, "
                        "intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u", h=crear_hash(nueva), u=alias)
            _auditar(cur, alias, "acceso", "Recuperó contraseña", "pregunta de seguridad")
            conn.commit()
            return "Contraseña cambiada. Entra con la nueva."
        if origen == "ESCRITORIO":
            cur.execute(f"UPDATE {TABLA} SET clave_pendiente = :h, clave_motivo = NULL, intentos = 0, "
                        "bloqueado_hasta = NULL WHERE usuario = :u AND estado = 'ACTIVO'", h=crear_hash(nueva), u=alias)
            if cur.rowcount:
                cur.execute(f"SELECT nombre FROM {TABLA} WHERE usuario = :u", u=alias)
                notificaciones.crear(cur, "SOLICITUD", f"{cur.fetchone()[0]} pidió restablecer su contraseña",
                                     "Solicitudes", rol=ADMIN)
            conn.commit()
            return "Solicitud enviada. Un administrador la revisará."
        conn.rollback()
    raise ErrorDeAcceso("Los operadores no recuperan su contraseña desde el escritorio.")


def cambiar_clave(usuario: str, actual: str, nueva: str, confirmacion: str) -> str:
    """Cambio desde Perfil. El Administrador cambia directo; Inventario deja la solicitud pendiente."""
    alias = _normalizar(usuario)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT clave_hash, rol FROM {TABLA} WHERE usuario = :u", u=alias)
        fila = cur.fetchone()
        if fila is None or not verificar_hash(actual, fila[0]):
            raise ErrorDeAcceso("La contraseña actual no es correcta.")
        rol = fila[1]
        if rol == OPERADOR:
            raise ErrorDeAcceso("Los operadores usan la app móvil.")
        _validar_clave(nueva, confirmacion)
        if rol == ADMIN:
            cur.execute(f"UPDATE {TABLA} SET clave_hash = :h WHERE usuario = :u", h=crear_hash(nueva), u=alias)
            _auditar(cur, alias, "perfil", "Cambió contraseña")
            conn.commit()
            return "Contraseña cambiada."
        cur.execute(f"UPDATE {TABLA} SET clave_pendiente = :h, clave_motivo = NULL WHERE usuario = :u",
                    h=crear_hash(nueva), u=alias)
        cur.execute(f"SELECT nombre FROM {TABLA} WHERE usuario = :u", u=alias)
        notificaciones.crear(cur, "SOLICITUD", f"{cur.fetchone()[0]} pidió cambiar su contraseña", "Solicitudes", rol=ADMIN)
        _auditar(cur, alias, "perfil", "Solicitó cambio de contraseña")
        conn.commit()
    return "Solicitud enviada. Un administrador la aprobará."


# ------------------------------------------------------------------ administración (solo ADMIN)
def listar() -> list[Usuario]:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, rol, estado, motivo, origen, clave_pendiente, creado, uuid_dispositivo, "
                    f"correo, foto, tema, idioma, clave_motivo FROM {TABLA} ORDER BY usuario")
        return [Usuario(r[0], r[1], r[2], r[3], r[4], r[5], r[6] is not None, r[7], r[8] is not None,
                        r[9], r[10], r[11] or "sistema", r[12] or "es", r[13]) for r in cur]


def _exigir(quien: Sesion, modulo: str) -> None:
    """Comprueba la matriz de permisos en Oracle (no solo el botón visible). Import tardío: permisos importa auth."""
    from . import permisos
    permisos.exigir(quien, modulo)


def _validar_rol(rol: str) -> None:
    if rol not in ROLES:
        raise ErrorDeAcceso("Ese rol no existe.")


ROLES_POR_ORIGEN = {"MOVIL": (OPERADOR,), "ESCRITORIO": (INVENTARIO,)}


def _validar_rol_para(cur, usuario: str, rol: str) -> None:
    """Una cuenta del celular solo puede ser Operador; una del PC solo puede ser Inventario.

    El único Administrador ya existe y no se promueve a nadie más.
    """
    _validar_rol(rol)
    if rol == ADMIN:
        raise ErrorDeAcceso("Solo existe un Administrador y no se puede crear otro.")
    cur.execute(f"SELECT origen, rol FROM {TABLA} WHERE usuario = :u", u=usuario)
    fila = cur.fetchone()
    if fila is None:
        raise ErrorDeAcceso("Esa cuenta no existe.")
    if fila[1] == ADMIN:
        raise ErrorDeAcceso("El Administrador no cambia de rol.")
    if rol not in ROLES_POR_ORIGEN.get(fila[0], ()):
        raise ErrorDeAcceso("Una cuenta del celular solo puede ser Operador de Inventario." if fila[0] == "MOVIL"
                            else "Una cuenta del PC solo puede ser de Inventario.")


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
    _exigir(quien, "usuarios")
    with db._conexion() as conn:
        cur = conn.cursor()
        _validar_rol_para(cur, usuario, rol)
        _transicion(cur, usuario, ACTIVO, "rol = :r", r=rol)
        _auditar(cur, quien.usuario, "usuarios", "Cambió rol", f"{usuario}: {NOMBRE_ROL[rol]}")
        conn.commit()


def aprobar(quien: Sesion, usuario: str, rol: str) -> None:
    _exigir(quien, "solicitudes")
    with db._conexion() as conn:
        cur = conn.cursor()
        _validar_rol_para(cur, usuario, rol)
        _transicion(cur, usuario, PENDIENTE, "estado = :e, rol = :r, motivo = NULL, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=ACTIVO, r=rol, q=quien.usuario)
        _auditar(cur, quien.usuario, "usuarios", "Aprobó cuenta", f"{usuario} como {NOMBRE_ROL[rol]}")
        conn.commit()


def rechazar(quien: Sesion, usuario: str, motivo: str) -> None:
    _exigir(quien, "solicitudes")
    motivo = _validar_motivo(motivo)
    with db._conexion() as conn:
        cur = conn.cursor()
        _transicion(cur, usuario, PENDIENTE, "estado = :e, motivo = :m, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=RECHAZADO, m=motivo, q=quien.usuario)
        _auditar(cur, quien.usuario, "usuarios", "Rechazó cuenta", f"{usuario} — «{motivo}»")
        conn.commit()


def suspender(quien: Sesion, usuario: str, motivo: str) -> None:
    _exigir(quien, "usuarios")
    motivo = _validar_motivo(motivo)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT rol FROM {TABLA} WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
        if fila and fila[0] == ADMIN:
            raise ErrorDeAcceso("El Administrador no se puede suspender.")
        _transicion(cur, usuario, ACTIVO, "estado = :e, motivo = :m, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=SUSPENDIDO, m=motivo, q=quien.usuario)
        _auditar(cur, quien.usuario, "usuarios", "Suspendió cuenta", f"{usuario} — «{motivo}»")
        conn.commit()


def reactivar(quien: Sesion, usuario: str) -> None:
    _exigir(quien, "usuarios")
    with db._conexion() as conn:
        cur = conn.cursor()
        _transicion(cur, usuario, SUSPENDIDO, "estado = :e, motivo = NULL, resuelto_por = :q, resuelto = SYSTIMESTAMP",
                    e=ACTIVO, q=quien.usuario)
        _auditar(cur, quien.usuario, "usuarios", "Reactivó cuenta", usuario)
        conn.commit()


def desvincular_telefono(quien: Sesion, usuario: str) -> None:
    """Suelta la cuenta del celular de su teléfono (p. ej. lo cambió o reinstaló la app): el próximo que sincronice la toma."""
    _exigir(quien, "usuarios")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {TABLA} SET uuid_dispositivo = NULL WHERE usuario = :u AND origen = 'MOVIL'", u=usuario)
        _auditar(cur, quien.usuario, "usuarios", "Desvinculó teléfono", usuario)
        conn.commit()


def historial_solicitudes() -> list[Solicitud]:
    """Solicitudes de cuenta ya resueltas (aprobadas o rechazadas), la más reciente primero."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre, estado, rol, motivo, resuelto_por, resuelto FROM {TABLA} "
                    "WHERE resuelto IS NOT NULL AND estado IN (:a, :r) ORDER BY resuelto DESC", a=ACTIVO, r=RECHAZADO)
        return [Solicitud(*fila) for fila in cur]


def restablecer_clave(quien: Sesion, usuario: str, nueva: str) -> None:
    """El Administrador pone una contraseña nueva a una cuenta del PC (nunca a un operador del celular)."""
    _exigir(quien, "usuarios")
    _validar_clave(nueva, nueva)
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT origen FROM {TABLA} WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
        if fila is None:
            raise ErrorDeAcceso("Esa cuenta no existe.")
        if fila[0] == "MOVIL":
            raise ErrorDeAcceso("La contraseña de un operador vive en el teléfono.")
        cur.execute(f"UPDATE {TABLA} SET clave_hash = :h, clave_pendiente = NULL, clave_motivo = NULL, "
                    "intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u", h=crear_hash(nueva), u=usuario)
        _auditar(cur, quien.usuario, "usuarios", "Restableció contraseña", usuario)
        conn.commit()


# ------------------------------------------------------------------ solicitudes de contraseña
def resolver_clave(quien: Sesion, usuario: str, aprobar: bool, motivo: str = "") -> None:
    """Aprueba (la contraseña pedida pasa a ser la de la cuenta) o rechaza con motivo obligatorio."""
    _exigir(quien, "solicitudes")
    motivo = "" if aprobar else _validar_motivo(motivo)
    with db._conexion() as conn:
        cur = conn.cursor()
        if aprobar:
            cur.execute(f"UPDATE {TABLA} SET clave_hash = clave_pendiente, clave_pendiente = NULL, clave_motivo = NULL, "
                        "intentos = 0, bloqueado_hasta = NULL WHERE usuario = :u AND clave_pendiente IS NOT NULL", u=usuario)
        else:
            cur.execute(f"UPDATE {TABLA} SET clave_pendiente = NULL, clave_motivo = :m "
                        "WHERE usuario = :u AND clave_pendiente IS NOT NULL", u=usuario, m=motivo)
        if cur.rowcount == 0:
            conn.rollback()
            raise ErrorDeAcceso("Esta solicitud ya fue resuelta.")
        _auditar(cur, quien.usuario, "usuarios", "Aprobó contraseña nueva" if aprobar else "Rechazó contraseña nueva",
                 usuario + ("" if aprobar else f" — «{motivo}»"))
        conn.commit()


# ------------------------------------------------------------------ preferencias y foto
def guardar_preferencias(usuario: str, tema: str | None = None, idioma: str | None = None) -> tuple[str, str]:
    """Guarda el tema y/o el idioma de una cuenta; devuelve los valores vigentes."""
    if tema is not None and tema not in _TEMAS:
        raise ErrorDeAcceso("Ese tema no existe.")
    if idioma is not None and idioma not in _IDIOMAS:
        raise ErrorDeAcceso("Ese idioma no existe.")
    with db._conexion() as conn:
        cur = conn.cursor()
        if tema is not None:
            cur.execute(f"UPDATE {TABLA} SET tema = :t WHERE usuario = :u", t=tema, u=usuario)
        if idioma is not None:
            cur.execute(f"UPDATE {TABLA} SET idioma = :i WHERE usuario = :u", i=idioma, u=usuario)
        conn.commit()
        cur.execute(f"SELECT tema, idioma FROM {TABLA} WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
    return (fila[0] or "sistema", fila[1] or "es") if fila else ("sistema", "es")


def guardar_foto(usuario: str, ruta: str | None) -> None:
    """Guarda (o borra, con ``None``) la ruta relativa de la foto de perfil."""
    if ruta is not None:
        ruta = ruta.replace("\\", "/").strip()
        if not ruta or ruta.startswith("/") or ".." in ruta.split("/"):
            raise ErrorDeAcceso("La ruta de la foto no es válida.")
        if len(ruta) > 200:
            raise ErrorDeAcceso("La ruta de la foto es demasiado larga.")
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE {TABLA} SET foto = :f WHERE usuario = :u", f=ruta, u=usuario)
        conn.commit()


def foto_de(usuario: str) -> str | None:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT foto FROM {TABLA} WHERE usuario = :u", u=usuario)
        fila = cur.fetchone()
    return fila[0] if fila else None


# ------------------------------------------------------------------ esquema
_COLUMNAS_NUEVAS = (
    ("CLAVE_PENDIENTE", "clave_pendiente VARCHAR2(200 CHAR)"),
    ("ESTADO", "estado VARCHAR2(10 CHAR) DEFAULT 'PENDIENTE' NOT NULL"),
    ("MOTIVO", "motivo VARCHAR2(300 CHAR)"),
    ("RESUELTO_POR", "resuelto_por VARCHAR2(30 CHAR)"),
    ("RESUELTO", "resuelto TIMESTAMP"),
    ("ORIGEN", "origen VARCHAR2(10 CHAR) DEFAULT 'ESCRITORIO' NOT NULL"),
    ("UUID_DISPOSITIVO", "uuid_dispositivo VARCHAR2(50 CHAR)"),
    ("CORREO", "correo VARCHAR2(120 CHAR)"),
    ("PREGUNTA", "pregunta VARCHAR2(200 CHAR)"),
    ("RESPUESTA_HASH", "respuesta_hash VARCHAR2(200 CHAR)"),
    ("FOTO", "foto VARCHAR2(200 CHAR)"),
    ("TEMA", "tema VARCHAR2(10 CHAR) DEFAULT 'sistema'"),
    ("IDIOMA", "idioma VARCHAR2(2 CHAR) DEFAULT 'es'"),
    ("CLAVE_MOTIVO", "clave_motivo VARCHAR2(300 CHAR)"),
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
        cur.execute(f"UPDATE {TABLA} SET tema = 'sistema' WHERE tema IS NULL")
        cur.execute(f"UPDATE {TABLA} SET idioma = 'es' WHERE idioma IS NULL")
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
