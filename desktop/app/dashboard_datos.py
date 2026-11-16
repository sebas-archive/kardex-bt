"""Convierte los datos reales del dashboard en lo que dibuja cada gráfico, según las opciones de la persona.

No inventa nada: cada fuente sale de una consulta existente (``db.fetch_series``, ``db.fetch_por_categoria`` y
``db.fetch_actividad``). Si un período no tiene datos, el resultado queda vacío y el gráfico lo dice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .i18n import t

FORMATO_TS = "%Y-%m-%d %H:%M"


@dataclass
class Serie:
    nombre: str
    valores: list[float]


@dataclass
class Datos:
    etiquetas: list[str] = field(default_factory=list)
    series: list[Serie] = field(default_factory=list)
    temporal: bool = False
    semaforo: bool = False        # una sola serie coloreada según el signo (falta / sobra)
    unidad: str = ""

    @property
    def vacio(self) -> bool:
        return not self.etiquetas or not self.series


def _ts(texto: str) -> datetime | None:
    try:
        return datetime.strptime(texto, FORMATO_TS)
    except (TypeError, ValueError):
        return None


def rango(opciones: dict, ahora: datetime) -> tuple[datetime | None, datetime | None]:
    """El intervalo [desde, hasta) del período elegido, en UTC como los datos. ``(None, None)`` = todo."""
    p = opciones.get("periodo", "todo")
    hoy = datetime(ahora.year, ahora.month, ahora.day)
    if p == "hoy":
        return hoy, hoy + timedelta(days=1)
    if p in ("7d", "30d", "90d"):
        return ahora - timedelta(days=int(p[:-1])), None
    if p == "mes":
        return datetime(ahora.year, ahora.month, 1), None
    if p == "anio":
        return datetime(ahora.year, 1, 1), None
    if p == "personalizado":
        return _fecha(opciones.get("desde")), _fecha(opciones.get("hasta"), fin=True)
    return None, None


def _fecha(texto, fin: bool = False) -> datetime | None:
    if not texto:
        return None
    try:
        d = date.fromisoformat(str(texto))
    except ValueError:
        return None
    base = datetime(d.year, d.month, d.day)
    return base + timedelta(days=1) if fin else base


def _dentro(ts: datetime, desde, hasta) -> bool:
    return (desde is None or ts >= desde) and (hasta is None or ts < hasta)


def _agrupacion(opciones: dict, tiempos: list[datetime]) -> str:
    g = opciones.get("agrupar", "auto")
    if g != "auto":
        return g
    if not tiempos:
        return "hora"
    lapso = max(tiempos) - min(tiempos)
    return "minuto" if lapso <= timedelta(hours=6) else "hora" if lapso <= timedelta(days=3) else "dia"


def _cubo(ts: datetime, agrupar: str) -> datetime:
    if agrupar == "dia":
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    if agrupar == "hora":
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(second=0, microsecond=0)


def _etiqueta(ts: datetime, agrupar: str, varios_dias: bool) -> str:
    if agrupar == "dia":
        return f"{ts:%d/%m}"
    if agrupar == "hora":
        return f"{ts:%d/%m %H:00}" if varios_dias else f"{ts:%H:00}"
    return f"{ts:%d/%m %H:%M}" if varios_dias else f"{ts:%H:%M}"


def _ordenar(pares: list[tuple[str, float]], opciones: dict) -> list[tuple[str, float]]:
    orden = opciones.get("orden", "original")
    if orden == "valor_desc":
        pares = sorted(pares, key=lambda p: (-p[1], p[0]))
    elif orden == "valor_asc":
        pares = sorted(pares, key=lambda p: (p[1], p[0]))
    elif orden == "nombre":
        pares = sorted(pares, key=lambda p: p[0].lower())
    top = int(opciones.get("top", 0) or 0)
    return pares[:top] if top > 0 else pares


def _categorico(pares: list[tuple[str, float]], opciones: dict, nombre: str, semaforo: bool = False,
                unidad: str = "") -> Datos:
    pares = _ordenar(list(pares), opciones)
    return Datos([p[0] for p in pares], [Serie(nombre, [p[1] for p in pares])], False, semaforo, unidad)


def _serie_temporal(filas: list[tuple[str, float]], opciones: dict, ahora: datetime, nombre: str) -> Datos:
    desde, hasta = rango(opciones, ahora)
    puntos = [(ts, v) for texto, v in filas if (ts := _ts(texto)) is not None and _dentro(ts, desde, hasta)]
    if not puntos:
        return Datos(temporal=True)
    g = _agrupacion(opciones, [p[0] for p in puntos])
    cubos: dict[datetime, float] = {}
    for ts, v in puntos:
        cubos[_cubo(ts, g)] = cubos.get(_cubo(ts, g), 0.0) + v
    claves = sorted(cubos)
    varios = claves[0].date() != claves[-1].date()
    return Datos([_etiqueta(c, g, varios) for c in claves], [Serie(nombre, [cubos[c] for c in claves])], True)


def construir(fuente: str, opciones: dict, crudo: dict, ahora: datetime | None = None) -> Datos:
    """``crudo``: ``categorias`` (diferencia por categoría), ``series`` (``db.fetch_series``) y ``actividad``."""
    ahora = ahora or datetime.now(timezone.utc).replace(tzinfo=None)
    series = crudo.get("series") or {}
    if fuente == "dif_categoria":
        return _categorico(crudo.get("categorias") or [], opciones, t("Diferencia"), semaforo=True, unidad=t("u."))
    if fuente == "avance_categoria":
        return _categorico(series.get("avance_categoria") or [], opciones, t("Avance"), unidad="%")
    if fuente == "lecturas_categoria":
        return _categorico(series.get("top_categorias") or [], opciones, t("Lecturas"))
    if fuente == "danados":
        return _categorico(series.get("danados") or [], opciones, t("Dañados"), unidad=t("u."))
    if fuente == "contados_pendientes":
        pares = [(t("Contados") if k == "contados" else t("Pendientes"), v)
                 for k, v in (series.get("contados_pendientes") or [])]
        return Datos([p[0] for p in pares], [Serie(t("Productos"), [p[1] for p in pares])])
    if fuente == "lecturas_tiempo":
        return _serie_temporal(series.get("por_hora") or [], opciones, ahora, t("Lecturas"))
    if fuente == "operador":
        desde, hasta = rango(opciones, ahora)
        total: dict[str, float] = {}
        for operador, hora, n in crudo.get("actividad") or []:
            ts = _ts(hora)
            if ts is not None and _dentro(ts, desde, hasta):
                total[operador] = total.get(operador, 0.0) + n
        return _categorico(list(total.items()), opciones, t("Lecturas"))
    if fuente == "operador_tiempo":
        desde, hasta = rango(opciones, ahora)
        filas = [(op, ts, n) for op, hora, n in crudo.get("actividad") or []
                 if (ts := _ts(hora)) is not None and _dentro(ts, desde, hasta)]
        if not filas:
            return Datos(temporal=True)
        g = _agrupacion(opciones, [f[1] for f in filas])
        cubos = sorted({_cubo(f[1], g) for f in filas})
        operadores = sorted({f[0] for f in filas})
        valores = {op: {c: 0.0 for c in cubos} for op in operadores}
        for op, ts, n in filas:
            valores[op][_cubo(ts, g)] += n
        top = int(opciones.get("top", 0) or 0)
        if top > 0:
            operadores = sorted(operadores, key=lambda o: -sum(valores[o].values()))[:top]
        varios = cubos[0].date() != cubos[-1].date()
        return Datos([_etiqueta(c, g, varios) for c in cubos],
                     [Serie(op, [valores[op][c] for c in cubos]) for op in operadores], True)
    if fuente == "batch_corridas":
        desde, hasta = rango(opciones, ahora)
        ok = dict(series.get("batch") or [])
        fallos = dict(series.get("batch_errores") or [])
        marcas = [(ts, texto) for texto in ok if (ts := _ts(texto)) is not None and _dentro(ts, desde, hasta)]
        marcas.sort()
        if not marcas:
            return Datos(temporal=True)
        varios = marcas[0][0].date() != marcas[-1][0].date()
        return Datos([f"{ts:%d/%m %H:%M}" if varios else f"{ts:%H:%M}" for ts, _ in marcas],
                     [Serie(t("Procesadas"), [ok[tx] for _, tx in marcas]),
                      Serie(t("Con error"), [fallos.get(tx, 0.0) for _, tx in marcas])], True)
    return Datos()
