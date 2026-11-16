"""Consultas de solo lectura para la pantalla Sincronización: actividad por intervalo y contadores del día.

No tocan el protocolo, el esquema ni las reglas del batch: solo cuentan filas que ya existen en
``CAPTURA_TRANSITO`` (lecturas recibidas y su estado) y ``REGISTROS_PROCESADOS`` (lecturas ya procesadas).
Como todo acceso a Oracle, **no se llaman desde el hilo de la interfaz** (``QueryRunner``).

Los estados ``NUEVO_SKU`` (SKU desconocido esperando decisión) y ``DESCARTADO`` (lectura no tomada) cuentan como
recibidas, pero **no como error**: aquí «error» es solo ``estado = 'ERROR'`` (formato/cantidad inválidos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import db

# clave -> (minutos que abarca, minutos por barra/punto, etiqueta)
RANGOS: dict[str, tuple[int, int, str]] = {
    "15m": (15, 1, "15 min"),
    "1h": (60, 5, "1 hora"),
    "24h": (1440, 60, "24 horas"),
    "7d": (10080, 1440, "7 días"),
}
RANGO_INICIAL = "1h"


@dataclass(frozen=True)
class Actividad:
    """Series por intervalo, de la más antigua a la más reciente."""

    rango: str
    paso_min: int
    recibidas: list[int]
    procesadas: list[int]
    errores: list[int]

    @property
    def total(self) -> int:
        return sum(self.recibidas) + sum(self.procesadas) + sum(self.errores)

    @property
    def vacia(self) -> bool:
        return self.total == 0


@dataclass(frozen=True)
class ContadoresDia:
    """Recibidas del día y, de ellas, las procesadas y las que quedaron en ERROR (los NUEVO_SKU no son error)."""

    recibidas: int
    procesadas: int
    errores: int


def inicio_del_dia_utc(ahora: datetime | None = None) -> datetime:
    """Medianoche local de hoy expresada en UTC sin zona (como guarda Oracle los TIMESTAMP de esta app)."""
    local = (ahora or datetime.now().astimezone()).astimezone()
    medianoche = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return medianoche.astimezone(timezone.utc).replace(tzinfo=None)


def _serie(cur, sql: str, minutos: int, paso: int, n: int) -> list[int]:
    cur.execute(sql, m=minutos, p=paso)
    valores = [0] * n
    for atras, cantidad in cur:
        atras = int(atras)
        if 0 <= atras < n:
            valores[n - 1 - atras] = int(cantidad)   # índice 0 = el intervalo más antiguo
    return valores


_BUCKET = "FLOOR((CAST(SYSTIMESTAMP AS DATE) - CAST({col} AS DATE)) * 1440 / :p)"


def fetch_actividad(rango: str = RANGO_INICIAL) -> Actividad:
    minutos, paso, _ = RANGOS[rango]
    n = minutos // paso
    ventana = "{col} >= SYSTIMESTAMP - NUMTODSINTERVAL(:m, 'MINUTE')"
    with db._conexion() as conn:
        cur = conn.cursor()
        recibidas = _serie(cur, f"SELECT b, COUNT(*) FROM (SELECT {_BUCKET.format(col='fecha_recepcion')} b FROM captura_transito "
                                f"WHERE {ventana.format(col='fecha_recepcion')}) GROUP BY b",
                           minutos, paso, n)
        errores = _serie(cur, f"SELECT b, COUNT(*) FROM (SELECT {_BUCKET.format(col='fecha_recepcion')} b FROM captura_transito "
                              f"WHERE estado = 'ERROR' AND {ventana.format(col='fecha_recepcion')}) GROUP BY b",
                         minutos, paso, n)
        procesadas = _serie(cur, f"SELECT b, COUNT(*) FROM (SELECT {_BUCKET.format(col='fecha_procesado')} b FROM registros_procesados "
                                 f"WHERE {ventana.format(col='fecha_procesado')}) GROUP BY b",
                            minutos, paso, n)
    return Actividad(rango, paso, recibidas, procesadas, errores)


def fetch_contadores_dia(desde_utc: datetime | None = None) -> ContadoresDia:
    desde = desde_utc or inicio_del_dia_utc()
    with db._conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), NVL(SUM(CASE WHEN estado = 'PROCESADO' THEN 1 ELSE 0 END), 0), "
                    "       NVL(SUM(CASE WHEN estado = 'ERROR' THEN 1 ELSE 0 END), 0) "
                    "  FROM captura_transito WHERE fecha_recepcion >= :d", d=desde)
        r = cur.fetchone()
    return ContadoresDia(int(r[0]), int(r[1]), int(r[2]))


def lecturas_por_minuto(actividad: Actividad | None) -> float | None:
    """Promedio de lecturas recibidas por minuto en el rango. ``None`` si no hay actividad que promediar."""
    if actividad is None or sum(actividad.recibidas) == 0:
        return None
    minutos = len(actividad.recibidas) * actividad.paso_min
    return sum(actividad.recibidas) / minutos
