"""Respaldos (Fase 5): un ``.zip`` con todas las tablas de la aplicación y las fotos; restaurar reemplaza **todo**.

Contenido del zip::

    manifest.json          {"formato": 1, "fecha", "usuario", "origen", "tablas": {T: {"columnas", "filas"}},
                            "secuencias": {S: last_number}, "fotos": n}
    datos/<TABLA>.jsonl    una fila por línea, como lista JSON en el orden de "columnas"
    fotos/<uuid>/<seq>.jpg

Los valores van como JSON: texto tal cual, ``null``, ``{"n": "1234.567"}`` (NUMBER exacto), ``{"t": "ISO 8601"}``
(DATE/TIMESTAMP) y ``{"b": base64}`` (RAW). Los datos se leen en una transacción de solo lectura (instantánea
coherente). Restaurar borra e inserta todas las tablas en **una** transacción; si algo falla, ROLLBACK y nada cambia.
Las fotos se extraen aparte y se cambian por las actuales solo después del COMMIT.

Lo que no sabe este módulo (pausar el servicio, permisos, auditoría del escritorio) lo hace quien lo llama.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable

import oracledb

from .store import fotos_dir

FORMATO = 1
ORIGENES = ("manual", "auto", "previo")
AUDITORIA = "auditoria"   # la tabla del escritorio; el automático deja ahí su fila si existe
EXCLUIDAS = ("SERVICIO_BT",)
OTRA_VERSION = "Este respaldo es de otra versión del sistema"
log = logging.getLogger("btsync.respaldo")


class ErrorRespaldo(Exception):
    """Un respaldo que no se puede usar: el mensaje es para la persona."""


@dataclass(frozen=True)
class Respaldo:
    archivo: str
    fecha: datetime
    bytes: int
    fotos: int
    usuario: str
    origen: str


def respaldos_dir() -> Path:
    """Carpeta de los respaldos (``RESPALDOS_DIR``; por defecto ``respaldos/`` en el directorio de trabajo)."""
    return Path(os.environ.get("RESPALDOS_DIR", "respaldos"))


def numeros_exactos(cursor, metadata):
    """``outputtypehandler``: los NUMBER llegan como ``Decimal`` (sin redondeos de float)."""
    if metadata.type_code is oracledb.DB_TYPE_NUMBER:
        return cursor.var(Decimal, arraysize=cursor.arraysize)
    return None


# ------------------------------------------------------------------ tablas
def tablas_de_la_app(cur) -> list[str]:
    cur.execute("SELECT table_name FROM user_tables WHERE table_name NOT LIKE '%\\_TST' ESCAPE '\\' "
                "AND table_name NOT LIKE 'BIN$%' ORDER BY table_name")
    return [t for (t,) in cur if t not in EXCLUIDAS]


def _ordenar(cur, tablas: list[str]) -> list[str]:
    """Padres antes que hijas (según las FK entre ``tablas``)."""
    cur.execute("SELECT h.table_name, p.table_name FROM user_constraints h "
                "JOIN user_constraints p ON p.constraint_name = h.r_constraint_name WHERE h.constraint_type = 'R'")
    padres: dict[str, set[str]] = {t: set() for t in tablas}
    for hija, padre in cur:
        if hija in padres and padre in padres and hija != padre:
            padres[hija].add(padre)
    orden: list[str] = []
    pendientes = dict(padres)
    while pendientes:
        listas = sorted(t for t, ps in pendientes.items() if ps <= set(orden))
        if not listas:   # ciclo: no debería haberlo; se respeta el orden alfabético
            listas = sorted(pendientes)
        orden.extend(listas)
        for t in listas:
            del pendientes[t]
    return orden


def _columnas(cur, tabla: str) -> list[str]:
    cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name = :t ORDER BY column_id", t=tabla)
    return [c for (c,) in cur]


def _tipos(cur, tabla: str) -> dict[str, str]:
    cur.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name = :t", t=tabla)
    return dict(cur.fetchall())


def _insertar(cur, sql: str, lote: list, columnas: list[str], tipos: dict[str, str]) -> None:
    """Un ``datetime`` se enviaría como DATE (sin fracciones de segundo): las columnas TIMESTAMP se declaran."""
    cur.setinputsizes(*[oracledb.DB_TYPE_TIMESTAMP if tipos.get(c, "").startswith("TIMESTAMP") else None
                        for c in columnas])
    cur.executemany(sql, lote)


def _codificar(v):
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (Decimal, int, float)):
        return {"n": str(v)}
    if isinstance(v, datetime):
        return {"t": v.isoformat()}
    if isinstance(v, bytes):
        return {"b": base64.b64encode(v).decode("ascii")}
    raise TypeError(f"tipo no soportado en un respaldo: {type(v).__name__}")


def _decodificar(v):
    if isinstance(v, dict):
        if "n" in v:
            return Decimal(v["n"])
        if "t" in v:
            return datetime.fromisoformat(v["t"])
        if "b" in v:
            return base64.b64decode(v["b"])
    return v


# ------------------------------------------------------------------ crear, listar, podar
def _nombre(ahora: datetime, origen: str) -> Path:
    carpeta = respaldos_dir()
    base = f"respaldo-{ahora:%Y%m%d-%H%M%S}-{origen}"
    destino, n = carpeta / f"{base}.zip", 2
    while destino.exists():
        destino, n = carpeta / f"{base}-{n}.zip", n + 1
    return destino


def crear(conn, usuario: str, origen: str, tablas: list[str] | None = None,
          ahora: datetime | None = None) -> Respaldo:
    """Escribe el zip (primero a ``.parcial``: nunca queda uno a medias en la lista). Una tabla creada o cambiada
    hace pocos segundos no se puede leer en la instantánea (ORA-01466): se reintenta unos segundos."""
    for intento in range(_INTENTOS):
        try:
            return _crear(conn, usuario, origen, tablas, ahora)
        except oracledb.DatabaseError as exc:
            if "ORA-01466" not in str(exc) or intento == _INTENTOS - 1:
                raise
            time.sleep(1)
    raise AssertionError("inalcanzable")


_INTENTOS = 8


def _crear(conn, usuario: str, origen: str, tablas: list[str] | None, ahora: datetime | None) -> Respaldo:
    if origen not in ORIGENES:
        raise ValueError(origen)
    ahora = (ahora or datetime.now()).replace(microsecond=0)
    destino = _nombre(ahora, origen)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_name(destino.name + ".parcial")
    conn.rollback()
    cur = conn.cursor()
    cur.execute("SET TRANSACTION READ ONLY")   # todas las tablas en la misma instantánea
    fotos = 0
    try:
        tablas = _ordenar(cur, tablas if tablas is not None else tablas_de_la_app(cur))
        manifest = {"formato": FORMATO, "fecha": ahora.isoformat(), "usuario": usuario, "origen": origen,
                    "tablas": {}, "secuencias": {}, "fotos": 0}
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as z:
            for tabla in tablas:
                columnas = _columnas(cur, tabla)
                lector = conn.cursor()
                lector.outputtypehandler = numeros_exactos
                lector.arraysize = 500
                lector.execute(f"SELECT {', '.join(columnas)} FROM {tabla}")
                filas = 0
                with z.open(f"datos/{tabla}.jsonl", "w") as salida:
                    for fila in lector:
                        salida.write(json.dumps([_codificar(v) for v in fila], ensure_ascii=False).encode() + b"\n")
                        filas += 1
                manifest["tablas"][tabla] = {"columnas": columnas, "filas": filas}
            cur.execute("SELECT sequence_name, last_number FROM user_sequences")
            manifest["secuencias"] = {s: int(n) for s, n in cur}
            raiz = fotos_dir()
            if raiz.is_dir():
                for archivo in sorted(p for p in raiz.rglob("*") if p.is_file() and not p.name.endswith(".parcial")):
                    z.write(archivo, f"fotos/{archivo.relative_to(raiz).as_posix()}")
                    fotos += 1
            manifest["fotos"] = fotos
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        os.replace(parcial, destino)
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    finally:
        conn.rollback()   # cierra la transacción de solo lectura
    return Respaldo(destino.name, ahora, destino.stat().st_size, fotos, usuario, origen)


def _leer_manifest(ruta: Path) -> dict:
    with zipfile.ZipFile(ruta) as z:
        return json.loads(z.read("manifest.json"))


def listar() -> list[Respaldo]:
    """Los respaldos de la carpeta, del más reciente al más antiguo. Lo que no es un respaldo se ignora."""
    carpeta = respaldos_dir()
    if not carpeta.is_dir():
        return []
    salida = []
    for ruta in carpeta.glob("*.zip"):
        try:
            m = _leer_manifest(ruta)
            salida.append(Respaldo(ruta.name, datetime.fromisoformat(m["fecha"]), ruta.stat().st_size,
                                   int(m.get("fotos", 0)), m.get("usuario", ""), m.get("origen", "")))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile):
            continue
    return sorted(salida, key=lambda r: (r.fecha, r.archivo), reverse=True)


def podar(conservar: int) -> list[str]:
    """Borra los automáticos más viejos y deja los ``conservar`` más recientes. Los demás no se tocan."""
    autos = [r for r in listar() if r.origen == "auto"]
    borrados = []
    for r in autos[conservar:]:
        (respaldos_dir() / r.archivo).unlink(missing_ok=True)
        borrados.append(r.archivo)
    return borrados


# ------------------------------------------------------------------ restaurar
def _estado_jobs(conn, jobs: tuple[str, ...]) -> dict[str, bool]:
    """Los jobs que existen y si están habilitados (para dejarlos igual al terminar)."""
    cur = conn.cursor()
    estado = {}
    for job in jobs:
        cur.execute("SELECT enabled FROM user_scheduler_jobs WHERE job_name = :j", j=job)
        fila = cur.fetchone()
        if fila is not None:
            estado[job] = fila[0] == "TRUE"
    return estado


def _deshabilitar(conn, jobs) -> None:
    for job in jobs:
        conn.cursor().execute("BEGIN DBMS_SCHEDULER.DISABLE(:j, force => TRUE); END;", j=job)


def _volver(conn, estado: dict[str, bool]) -> None:
    """Deja cada job como estaba (un error al habilitar uno no impide los demás)."""
    for job, activo in estado.items():
        try:
            if activo:
                conn.cursor().callproc("DBMS_SCHEDULER.ENABLE", [job])
        except Exception:
            log.exception("no se pudo volver a habilitar %s", job)


def _jobs_corriendo(conn, jobs) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT job_name FROM user_scheduler_running_jobs")
    return [j for (j,) in cur if j in jobs]


def _esperar_jobs(conn, jobs, espera_s: float) -> None:
    """DISABLE no detiene una ejecución en curso: se espera a que termine (sus filas quedarían mezcladas)."""
    limite = time.monotonic() + espera_s
    while _jobs_corriendo(conn, jobs):
        if time.monotonic() >= limite:
            raise ErrorRespaldo("El procesamiento de lecturas sigue en curso; inténtalo de nuevo en un momento.")
        time.sleep(0.25)


def _adelantar_secuencias(conn, secuencias: dict) -> None:
    """Cada secuencia queda al menos en el valor del respaldo. Ya hubo COMMIT: un valor raro se registra y se sigue."""
    cur = conn.cursor()
    cur.execute("SELECT sequence_name, last_number FROM user_sequences")
    existentes = {s: int(n) for s, n in cur}
    for nombre, objetivo in secuencias.items():
        try:
            objetivo = int(objetivo)
            if nombre not in existentes or existentes[nombre] >= objetivo:
                continue   # ya va por delante: no se gasta ningún número
            cur.execute(f"SELECT {nombre}.NEXTVAL FROM dual")
            actual = int(cur.fetchone()[0])
            if actual < objetivo:
                cur.execute(f"ALTER SEQUENCE {nombre} INCREMENT BY {objetivo - actual}")
                cur.execute(f"SELECT {nombre}.NEXTVAL FROM dual")
                cur.execute(f"ALTER SEQUENCE {nombre} INCREMENT BY 1")
        except Exception:
            log.exception("no se pudo adelantar la secuencia %r", nombre)


def _extraer_fotos(z: zipfile.ZipFile, destino: Path) -> None:
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    base = destino.resolve()
    for nombre in z.namelist():
        if not nombre.startswith("fotos/") or nombre.endswith("/"):
            continue
        ruta = (base / nombre[len("fotos/"):]).resolve()
        if base not in ruta.parents:
            raise ErrorRespaldo(OTRA_VERSION)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(z.read(nombre))


def _cambiar_fotos(nueva: Path, actual: Path) -> None:
    anterior = actual.with_name(actual.name + ".anterior")
    if anterior.exists():
        shutil.rmtree(anterior)
    if actual.exists():
        os.replace(actual, anterior)
    try:
        os.replace(nueva, actual)
    except BaseException:
        if anterior.exists() and not actual.exists():
            os.replace(anterior, actual)   # las fotos de antes vuelven a su sitio
        raise
    if anterior.exists():
        shutil.rmtree(anterior, ignore_errors=True)


BLOQUEADO = "Otra sesión está usando los datos (p. ej. otro escritorio abierto); inténtalo de nuevo en un momento."


def restaurar(conn, archivo: str, tablas: list[str] | None = None, jobs: tuple[str, ...] = (),
              espera_s: float = 30) -> None:
    """Reemplaza todas las tablas (y las fotos) por las del respaldo.

    Los ``jobs`` se deshabilitan (y se espera a que termine una ejecución en curso) y al final quedan como estaban.
    Las tablas se bloquean en modo exclusivo dentro de la misma transacción: si otra sesión tiene cambios sin
    confirmar, se espera hasta ``espera_s`` y si no, nada cambia. Tras el COMMIT se cambian las fotos y se adelantan
    las secuencias (un fallo ahí ya no deshace los datos)."""
    ruta = respaldos_dir() / Path(archivo).name
    try:
        z = zipfile.ZipFile(ruta)
        m = json.loads(z.read("manifest.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        raise ErrorRespaldo("El archivo no es un respaldo válido.") from exc
    with z:
        if m.get("formato") != FORMATO:
            raise ErrorRespaldo(OTRA_VERSION)
        cur = conn.cursor()
        conn.rollback()
        tablas = _ordenar(cur, tablas if tablas is not None else tablas_de_la_app(cur))
        columnas_db = {t: set(_columnas(cur, t)) for t in tablas}
        for tabla, info in m["tablas"].items():
            if tabla not in columnas_db or not set(info["columnas"]) <= columnas_db[tabla]:
                raise ErrorRespaldo(OTRA_VERSION)
        fotos = fotos_dir()
        nueva = fotos.with_name(fotos.name + ".nueva")
        estado_jobs = _estado_jobs(conn, jobs)
        try:
            _deshabilitar(conn, estado_jobs)
            _esperar_jobs(conn, tuple(estado_jobs), espera_s)
            _extraer_fotos(z, nueva)
            try:
                if tablas:
                    try:
                        cur.execute(f"LOCK TABLE {', '.join(tablas)} IN EXCLUSIVE MODE WAIT {max(1, int(espera_s))}")
                    except oracledb.DatabaseError as exc:
                        if "ORA-30006" in str(exc) or "ORA-00054" in str(exc):
                            raise ErrorRespaldo(BLOQUEADO) from exc
                        raise
                for tabla in reversed(tablas):
                    cur.execute(f"DELETE FROM {tabla}")
                for tabla in tablas:
                    info = m["tablas"].get(tabla)
                    if info is None:
                        continue
                    columnas = info["columnas"]
                    tipos = _tipos(cur, tabla)
                    sql = (f"INSERT INTO {tabla} ({', '.join(columnas)}) "
                           f"VALUES ({', '.join(f':{i + 1}' for i in range(len(columnas)))})")
                    lote = []
                    with z.open(f"datos/{tabla}.jsonl") as entrada:
                        for linea in entrada:
                            if linea.strip():
                                lote.append([_decodificar(v) for v in json.loads(linea)])
                            if len(lote) >= 500:
                                _insertar(cur, sql, lote, columnas, tipos)
                                lote = []
                    if lote:
                        _insertar(cur, sql, lote, columnas, tipos)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            _cambiar_fotos(nueva, fotos)
            _adelantar_secuencias(conn, m.get("secuencias", {}))
        finally:
            shutil.rmtree(nueva, ignore_errors=True)
            _volver(conn, estado_jobs)


# ------------------------------------------------------------------ automático
class Automatico:
    """Tarea periódica del servicio: con ``respaldos.auto = S``, pasada ``respaldos.hora`` y sin un respaldo
    automático de hoy en la carpeta, crea uno y poda los viejos. Mira una vez por minuto."""

    def __init__(self, conectar: Callable, reloj: Callable[[], datetime] = datetime.now) -> None:
        self._conectar = conectar
        self._reloj = reloj
        self._ultimo_minuto: str | None = None

    def __call__(self) -> Respaldo | None:
        from . import config

        ahora = self._reloj()
        minuto = f"{ahora:%Y%m%d%H%M}"
        if minuto == self._ultimo_minuto:
            return None
        self._ultimo_minuto = minuto
        conn = self._conectar()
        try:
            v = config.leer(conn.cursor())
            if v["respaldos.auto"] != "S" or f"{ahora:%H:%M}" < v["respaldos.hora"]:
                return None
            if any(r.origen == "auto" and r.fecha.date() == ahora.date() for r in listar()):
                return None
            try:
                r = crear(conn, "servicio", "auto", ahora=ahora)
            except Exception as exc:
                _notificar(conn, "RESPALDO_FALLO", f"Falló el respaldo automático: {exc}")
                raise
            podar(int(v["respaldos.conservar"]))
            _auditar(conn, r.archivo)
            _notificar(conn, "RESPALDO", f"Respaldo automático creado: {r.archivo}")
            log.info("respaldo automático %s", r.archivo)
            return r
        finally:
            conn.close()


def _notificar(conn, tipo: str, texto: str) -> None:
    """Aviso al Administrador; si no se puede, se registra y se sigue (el respaldo es lo que importa)."""
    from . import notificaciones

    try:
        conn.rollback()
        notificaciones.crear(conn.cursor(), tipo, texto, "Respaldos", rol="ADMIN")
        conn.commit()
    except Exception:
        log.exception("no se pudo crear la notificación del respaldo")


def _auditar(conn, archivo: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = :t", t=AUDITORIA.upper())
    if cur.fetchone()[0]:
        cur.execute(f"INSERT INTO {AUDITORIA} (id, usuario, modulo, accion, detalle) "
                    f"VALUES (seq_auditoria.NEXTVAL, 'servicio', 'respaldos', 'Creó respaldo', :d)", d=archivo)
        conn.commit()
