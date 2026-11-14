"""Movimientos de inventario (Fase 3b): entradas, salidas y ajustes, en una sola tabla.

- **Entrada / salida**: cambian la existencia al momento, en la misma transacción. Una salida nunca deja la existencia
  por debajo de 0. Registrarlas exige ``GESTION`` en ``entradas_salidas``.
- **Ajuste**: corrige la existencia a una cantidad nueva, con motivo (p. ej. tras un conteo). Si es **crítico** (cambia
  10 % o más, o vale $200.000 o más) queda ``PENDIENTE`` y no toca nada hasta que el Administrador lo aprueba. Al
  aprobarlo se aplica el **delta** pedido sobre la existencia de ese momento, para no pisar lo que se movió mientras
  tanto. Solicitar exige ``GESTION`` en ``ajustes`` y no ser Administrador (nunca edita la operación diaria, y así nadie
  aprueba lo suyo); aprobar o rechazar exige ``GESTION`` en ``ajustes`` y ser Administrador, comprobado en vivo.

La fila de la existencia se bloquea (``SELECT … FOR UPDATE``) antes de leerla y cambiarla: dos usuarios a la vez no
pueden dejarla negativa ni perder un movimiento. Como todo lo que toca Oracle, se llama fuera del hilo de la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import oracledb

from . import auth, db, maestros, permisos
from .auth import ErrorDeAcceso, Sesion

TABLA = "movimientos"   # las pruebas usan «movimientos_tst»
ENTRADA, SALIDA, AJUSTE = "ENTRADA", "SALIDA", "AJUSTE"
APLICADO, PENDIENTE, RECHAZADO = "APLICADO", "PENDIENTE", "RECHAZADO"
NOMBRE_TIPO = {ENTRADA: "Entrada", SALIDA: "Salida", AJUSTE: "Ajuste"}
NOMBRE_ESTADO = {APLICADO: "Aplicado", PENDIENTE: "Pendiente de aprobación", RECHAZADO: "Rechazado"}
MOTIVOS_SALIDA = ("Venta", "Consumo interno", "Daño", "Vencimiento", "Otro")
UMBRAL_PCT = 10            # % de la existencia anterior
UMBRAL_VALOR = 200_000     # pesos (|Δ| × costo unitario)
_MAXIMO = 999_999_999.999


@dataclass(frozen=True)
class Movimiento:
    id: int
    fecha: datetime
    tipo: str
    sku: str
    producto: str
    almacen: str
    nombre_almacen: str
    cantidad: float          # delta con signo: +entrada, −salida, ± ajuste
    antes: float | None
    despues: float | None
    motivo: str
    observaciones: str
    responsable: str
    estado: str
    resuelto_por: str
    motivo_rechazo: str
    id_conteo: str
    nombre_responsable: str = ""


def fmt(valor: float) -> str:
    """1.234,5 · 70 · 0,25 (como en las pantallas)."""
    texto = f"{valor:,.3f}".rstrip("0").rstrip(".")
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def es_critico(antes: float, despues: float, costo_unit: float) -> bool:
    delta = abs(despues - antes)
    if delta == 0:
        return False
    if antes == 0:
        return True
    return round(delta / antes * 100, 6) >= UMBRAL_PCT or round(delta * costo_unit, 2) >= UMBRAL_VALOR


# ------------------------------------------------------------------ consultas
def listar() -> list[Movimiento]:
    """Todos los movimientos, del más reciente al más antiguo."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT m.id, m.fecha, m.tipo, m.sku, p.nombre, m.almacen, NVL(a.nombre, m.almacen), m.cantidad, m.antes,
                   m.despues, m.motivo, m.observaciones, m.responsable, m.estado, m.resuelto_por, m.motivo_rechazo,
                   m.id_conteo, NVL(u.nombre, m.responsable)
              FROM {TABLA} m
              JOIN productos p ON p.sku = m.sku
              LEFT JOIN {maestros.ALMACENES} a ON a.codigo = m.almacen
              LEFT JOIN {auth.TABLA} u ON u.usuario = m.responsable
             ORDER BY m.fecha DESC, m.id DESC""")
        return [Movimiento(int(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], float(r[7]), db._f(r[8]), db._f(r[9]),
                           r[10] or "", r[11] or "", r[12], r[13], r[14] or "", r[15] or "", r[16] or "", r[17])
                for r in cur]


def existencia(sku: str, almacen: str) -> float:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT cantidad FROM {maestros.EXISTENCIAS} WHERE sku = :s AND codigo_almacen = :a", s=sku, a=almacen)
        fila = cur.fetchone()
        return float(fila[0]) if fila else 0.0


def existencia_y_costo(sku: str, almacen: str) -> tuple[float, float]:
    """Lo que el diálogo de ajuste muestra: la existencia de hoy y el costo (para avisar si será crítico)."""
    return existencia(sku, almacen), costo_unitario(sku)


def costo_unitario(sku: str) -> float:
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT costo_unit FROM productos WHERE sku = :s", s=sku)
        fila = cur.fetchone()
        return float(fila[0]) if fila else 0.0


def propuesta_desde_diferencia(id_conteo: str, sku: str) -> tuple[str, float, float]:
    """(almacén de la tarea, existencia actual, propuesta = actual + diferencia del conteo, sin bajar de 0)."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT c.almacen, k.diferencia FROM conciliacion k JOIN conteos c ON c.id_conteo = k.id_conteo "
                    "WHERE k.id_conteo = :c AND k.sku = :s AND k.clasificacion IN ('FALTANTE', 'SOBRANTE')",
                    c=id_conteo, s=sku)
        fila = cur.fetchone()
    if fila is None or not fila[0]:
        raise ErrorDeAcceso("Esa diferencia no tiene almacén o ya no existe: ajusta a mano desde «Ajustes».")
    almacen, diferencia = fila[0], float(fila[1] or 0)
    actual = existencia(sku, almacen)
    return almacen, actual, max(0.0, actual + diferencia)


# ------------------------------------------------------------------ validaciones
def _validar_cantidad(cantidad: float, cero: bool = False) -> float:
    cantidad = float(cantidad)
    if cero and cantidad < 0:
        raise ErrorDeAcceso("La cantidad nueva debe ser 0 o más.")
    if not cero and cantidad <= 0:
        raise ErrorDeAcceso("La cantidad debe ser mayor que 0.")
    if round(cantidad, 3) != cantidad:
        raise ErrorDeAcceso("La cantidad admite hasta 3 decimales.")
    if cantidad > _MAXIMO:
        raise ErrorDeAcceso("La cantidad es demasiado grande.")
    return cantidad


def _validar_destino(cur, sku: str, almacen: str) -> float:
    """Almacén activo y producto de una categoría activa; devuelve el costo unitario."""
    cur.execute(f"SELECT COUNT(*) FROM {maestros.ALMACENES} WHERE codigo = :a AND activo = 'S'", a=almacen)
    if not cur.fetchone()[0]:
        raise ErrorDeAcceso("Ese almacén ya no está activo. Actualiza la lista.")
    cur.execute(f"SELECT p.costo_unit FROM productos p JOIN {maestros.CATEGORIAS} c ON c.nombre = p.categoria "
                f"AND c.activa = 'S' WHERE p.sku = :s", s=sku)
    fila = cur.fetchone()
    if fila is None:
        raise ErrorDeAcceso("Ese producto es de una categoría inactiva o ya no existe. Actualiza la lista.")
    return float(fila[0])


def _fecha(fecha: date) -> datetime:
    if fecha > date.today():
        raise ErrorDeAcceso("La fecha no puede ser futura.")
    return datetime.now() if fecha == date.today() else datetime.combine(fecha, datetime.min.time())


def _rol_actual(cur, quien: Sesion) -> str | None:
    cur.execute(f"SELECT rol FROM {auth.TABLA} WHERE usuario = :u", u=quien.usuario)
    fila = cur.fetchone()
    return fila[0] if fila else None


# ------------------------------------------------------------------ existencias (con la fila bloqueada)
def _bloquear(cur, sku: str, almacen: str) -> float | None:
    cur.execute(f"SELECT cantidad FROM {maestros.EXISTENCIAS} WHERE sku = :s AND codigo_almacen = :a FOR UPDATE",
                s=sku, a=almacen)
    fila = cur.fetchone()
    return None if fila is None else float(fila[0])


def _bloquear_o_crear(cur, sku: str, almacen: str) -> float:
    """La existencia bloqueada; si no hay fila la crea en 0 (si otro la creó a la vez, la bloquea)."""
    actual = _bloquear(cur, sku, almacen)
    if actual is not None:
        return actual
    try:
        cur.execute(f"INSERT INTO {maestros.EXISTENCIAS} (sku, codigo_almacen, cantidad) VALUES (:s, :a, 0)",
                    s=sku, a=almacen)
        return 0.0
    except oracledb.IntegrityError:
        return _bloquear(cur, sku, almacen) or 0.0


def _poner(cur, sku: str, almacen: str, cantidad: float) -> None:
    cur.execute(f"UPDATE {maestros.EXISTENCIAS} SET cantidad = :c WHERE sku = :s AND codigo_almacen = :a",
                c=cantidad, s=sku, a=almacen)


def _insertar(cur, tipo, sku, almacen, delta, antes, despues, fecha, motivo, observaciones, responsable, estado,
              id_conteo=None) -> int:
    cur.execute("SELECT seq_movimientos.NEXTVAL FROM dual")
    id_mov = int(cur.fetchone()[0])
    cur.execute(f"INSERT INTO {TABLA} (id, tipo, sku, almacen, cantidad, antes, despues, fecha, motivo, observaciones, "
                f"responsable, estado, id_conteo) VALUES (:i, :t, :s, :a, :c, :an, :de, :f, :m, :o, :r, :e, :ic)",
                i=id_mov, t=tipo, s=sku, a=almacen, c=delta, an=antes, de=despues, f=fecha, m=motivo or None,
                o=observaciones or None, r=responsable, e=estado, ic=id_conteo)
    return id_mov


def _observaciones(texto: str) -> str:
    texto = (texto or "").strip()
    if len(texto) > 300:
        raise ErrorDeAcceso("Las observaciones pueden tener máximo 300 caracteres.")
    return texto


# ------------------------------------------------------------------ entradas y salidas
def registrar_entrada(quien: Sesion, sku: str, almacen: str, cantidad: float, fecha: date, observaciones: str) -> int:
    permisos.exigir(quien, "entradas_salidas")
    cantidad, cuando, observaciones = _validar_cantidad(cantidad), _fecha(fecha), _observaciones(observaciones)
    with db._conexion() as conn:
        cur = conn.cursor()
        try:
            _validar_destino(cur, sku, almacen)
            antes = _bloquear_o_crear(cur, sku, almacen)
            _poner(cur, sku, almacen, antes + cantidad)
            id_mov = _insertar(cur, ENTRADA, sku, almacen, cantidad, antes, antes + cantidad, cuando, "", observaciones,
                               quien.usuario, APLICADO)
            conn.commit()
            return id_mov
        except Exception:
            conn.rollback()
            raise


def registrar_salida(quien: Sesion, sku: str, almacen: str, cantidad: float, fecha: date, motivo: str,
                     observaciones: str) -> int:
    permisos.exigir(quien, "entradas_salidas")
    cantidad, cuando, observaciones = _validar_cantidad(cantidad), _fecha(fecha), _observaciones(observaciones)
    if motivo not in MOTIVOS_SALIDA:
        raise ErrorDeAcceso("Elige el motivo de la salida.")
    with db._conexion() as conn:
        cur = conn.cursor()
        try:
            _validar_destino(cur, sku, almacen)
            antes = _bloquear(cur, sku, almacen) or 0.0
            if cantidad > antes:
                raise ErrorDeAcceso(f"Solo hay {fmt(antes)} en ese almacén.")
            _poner(cur, sku, almacen, antes - cantidad)
            id_mov = _insertar(cur, SALIDA, sku, almacen, -cantidad, antes, antes - cantidad, cuando, motivo,
                               observaciones, quien.usuario, APLICADO)
            conn.commit()
            return id_mov
        except Exception:
            conn.rollback()   # suelta el bloqueo de la fila
            raise


# ------------------------------------------------------------------ ajustes
def solicitar_ajuste(quien: Sesion, sku: str, almacen: str, nueva: float, motivo: str,
                     id_conteo: str | None = None) -> str:
    """Devuelve ``APLICADO`` (no crítico) o ``PENDIENTE`` (crítico: espera al Administrador)."""
    permisos.exigir(quien, "ajustes")
    nueva = _validar_cantidad(nueva, cero=True)
    motivo = (motivo or "").strip()
    if not motivo or len(motivo) > 60:
        raise ErrorDeAcceso("Escribe el motivo del ajuste (máximo 60 caracteres).")
    with db._conexion() as conn:
        cur = conn.cursor()
        try:
            if _rol_actual(cur, quien) == auth.ADMIN:
                raise ErrorDeAcceso("El Administrador no solicita ajustes: los registra Inventario y el Administrador "
                                    "aprueba los críticos.")
            costo = _validar_destino(cur, sku, almacen)
            bloqueada = _bloquear(cur, sku, almacen)   # serializa las solicitudes de ese producto y almacén
            antes = bloqueada or 0.0
            cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE tipo = :t AND sku = :s AND almacen = :a AND estado = :e",
                        t=AJUSTE, s=sku, a=almacen, e=PENDIENTE)
            if cur.fetchone()[0]:
                raise ErrorDeAcceso("Ya hay un ajuste pendiente de ese producto en ese almacén: espera a que el "
                                    "Administrador lo resuelva.")
            if id_conteo:
                cur.execute(f"SELECT COUNT(*) FROM {TABLA} WHERE tipo = :t AND sku = :s AND id_conteo = :c "
                            f"AND estado <> :r", t=AJUSTE, s=sku, c=id_conteo, r=RECHAZADO)
                if cur.fetchone()[0]:
                    raise ErrorDeAcceso("Esa diferencia ya tiene un ajuste. Actualiza la lista.")
            if nueva == antes:
                raise ErrorDeAcceso("La cantidad nueva es igual a la actual: el ajuste no cambia nada.")
            estado = PENDIENTE if es_critico(antes, nueva, costo) else APLICADO
            if estado == APLICADO:   # un pendiente no crea la fila: el producto no aparece «Agotado» donde nunca estuvo
                if bloqueada is None:
                    _bloquear_o_crear(cur, sku, almacen)
                _poner(cur, sku, almacen, nueva)
            _insertar(cur, AJUSTE, sku, almacen, nueva - antes, antes, nueva, datetime.now(), motivo, "", quien.usuario,
                      estado, id_conteo)
            conn.commit()
            return estado
        except Exception:
            conn.rollback()
            raise


def _resolver(cur, quien: Sesion, id_mov: int) -> tuple:
    if _rol_actual(cur, quien) != auth.ADMIN:
        raise ErrorDeAcceso("Solo el Administrador aprueba o rechaza ajustes.")
    cur.execute(f"SELECT sku, almacen, antes, despues, estado FROM {TABLA} WHERE id = :i AND tipo = :t FOR UPDATE",
                i=id_mov, t=AJUSTE)
    fila = cur.fetchone()
    if fila is None:
        raise ErrorDeAcceso("Ese ajuste ya no existe. Actualiza la lista.")
    if fila[4] != PENDIENTE:
        raise ErrorDeAcceso("Ese ajuste ya fue resuelto. Actualiza la lista.")
    return fila[0], fila[1], float(fila[2]), float(fila[3])


def aprobar(quien: Sesion, id_mov: int) -> None:
    """Aplica el delta pedido sobre la existencia de ahora; nunca la deja negativa."""
    permisos.exigir(quien, "ajustes")
    with db._conexion() as conn:
        cur = conn.cursor()
        try:
            sku, almacen, antes, despues = _resolver(cur, quien, id_mov)
            actual = _bloquear_o_crear(cur, sku, almacen)
            nuevo = round(actual + (despues - antes), 3)
            if nuevo < 0:
                raise ErrorDeAcceso(f"Al aplicarlo, la existencia quedaría en {fmt(nuevo)} (hoy hay {fmt(actual)}). "
                                    f"Recházalo y pide un ajuste nuevo.")
            _poner(cur, sku, almacen, nuevo)
            # «antes» y «después» quedan como se pidieron: el historial muestra la solicitud y el delta aplicado.
            cur.execute(f"UPDATE {TABLA} SET estado = :e, resuelto_por = :q, resuelto = SYSTIMESTAMP WHERE id = :i",
                        e=APLICADO, q=quien.usuario, i=id_mov)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def rechazar(quien: Sesion, id_mov: int, motivo: str) -> None:
    permisos.exigir(quien, "ajustes")
    motivo = (motivo or "").strip()
    if not motivo or len(motivo) > 300:
        raise ErrorDeAcceso("Escribe el motivo del rechazo (máximo 300 caracteres).")
    with db._conexion() as conn:
        cur = conn.cursor()
        try:
            _resolver(cur, quien, id_mov)
            cur.execute(f"UPDATE {TABLA} SET estado = :e, motivo_rechazo = :m, resuelto_por = :q, "
                        f"resuelto = SYSTIMESTAMP WHERE id = :i", e=RECHAZADO, m=motivo, q=quien.usuario, i=id_mov)
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ------------------------------------------------------------------ esquema
def migrar() -> None:
    """La secuencia y la tabla, si faltan. Idempotente y tolerante a dos escritorios a la vez."""
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_sequences WHERE sequence_name = 'SEQ_MOVIMIENTOS'")
        if not cur.fetchone()[0]:
            db.ddl_tolerante(cur, "CREATE SEQUENCE seq_movimientos START WITH 1 NOCACHE")
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=TABLA.upper())
        if not cur.fetchone()[0]:
            db.ddl_tolerante(cur, f"""CREATE TABLE {TABLA} (
                id              NUMBER             NOT NULL,
                tipo            VARCHAR2(10 CHAR)  NOT NULL,
                sku             VARCHAR2(30 CHAR)  NOT NULL,
                almacen         VARCHAR2(20 CHAR)  NOT NULL,
                cantidad        NUMBER(13, 3)      NOT NULL,
                antes           NUMBER(13, 3),
                despues         NUMBER(13, 3),
                fecha           TIMESTAMP          NOT NULL,
                registrado      TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
                motivo          VARCHAR2(60 CHAR),
                observaciones   VARCHAR2(300 CHAR),
                responsable     VARCHAR2(30 CHAR)  NOT NULL,
                estado          VARCHAR2(10 CHAR)  NOT NULL,
                resuelto_por    VARCHAR2(30 CHAR),
                resuelto        TIMESTAMP,
                motivo_rechazo  VARCHAR2(300 CHAR),
                id_conteo       VARCHAR2(30 CHAR),
                CONSTRAINT pk_{TABLA} PRIMARY KEY (id),
                CONSTRAINT ck_{TABLA}_tipo CHECK (tipo IN ('ENTRADA', 'SALIDA', 'AJUSTE')),
                CONSTRAINT ck_{TABLA}_estado CHECK (estado IN ('APLICADO', 'PENDIENTE', 'RECHAZADO')))""")
        conn.commit()
