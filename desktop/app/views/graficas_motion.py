"""Movimiento de **datos** de las gráficas de pyqtgraph: las gráficas evolucionan desde su estado anterior.

Dos partes:

* **Pura** (sin Qt): ``unir``, ``emparejar_barras`` y ``emparejar_puntos`` relacionan lo que se veía con lo nuevo por
  etiqueta estable (nunca por posición), de modo que una categoría que cambia de lugar viaja, una que aparece entra, una
  que desaparece sale y las que siguen conservan su valor anterior como punto de partida.
* **Controladores** (``GraficaBarras``, ``GraficaLinea``): dueños de los ítems de pyqtgraph, que se crean **una sola
  vez** por gráfica (no se hace ``plot.clear()`` en cada dato). Interpolan posiciones, alturas, escala y ejes con una sola
  ``QVariantAnimation`` (``widgets.animar``: el mismo motor del resto de la app) y terminan **exactamente** en los datos
  reales. Sin animaciones (``APP_SIN_ANIMACIONES=1`` o movimiento reducido) saltan directo al estado final.

Los valores intermedios son solo dibujo: el dato real (``finales``) está disponible desde el primer instante.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

import pyqtgraph as pg
from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QObject, QTimer, QVariantAnimation
from PyQt6.QtGui import QBrush, QColor

from . import widgets

# Duraciones (ms) de cada naturaleza de movimiento de datos.
MS_ENTRADA, MS_ACTUALIZA = 720, 440
ALFA_ATENUADA = 88 / 255            # las demás barras mientras se señala una (el mismo 88/255 de antes)
PRESENCIA_DESDE = 0.06              # una etiqueta de valor se omite si la barra es < 6 % de la mayor (muchas barras)


def etiqueta_corta(texto: str) -> str:
    return texto if len(texto) <= 10 else "…" + texto[-6:]


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def _cancelar(anim: QVariantAnimation | None) -> None:
    """Detiene una animación y la libera (una animación detenida no emite ``finished``: sin esto quedaría colgada)."""
    if anim is None:
        return
    try:
        anim.stop()
        anim.deleteLater()
    except RuntimeError:        # ya la borró Qt al terminar
        pass


# ============================================================================================ parte pura
def claves(etiquetas: Sequence[str]) -> list[str]:
    """Clave única por etiqueta (si una se repite, las siguientes llevan un sufijo): así nunca se confunden dos barras."""
    vistas: dict[str, int] = {}
    salida = []
    for e in etiquetas:
        n = vistas.get(e, 0)
        vistas[e] = n + 1
        salida.append(e if n == 0 else f"{e}\x00{n}")
    return salida


def unir(previas: Sequence[str], nuevas: Sequence[str]) -> list[str]:
    """Orden de dibujo durante la transición: el de los datos nuevos, con cada elemento que sale insertado justo tras el
    que lo precedía antes (o al principio). Conserva el orden relativo de ambos conjuntos."""
    union = list(nuevas)
    presentes = set(nuevas)
    ultimo: str | None = None
    for k in previas:
        if k in presentes:
            ultimo = k
            continue
        union.insert(0 if ultimo is None else union.index(ultimo) + 1, k)
        ultimo = k
    return union


@dataclass(frozen=True)
class ElementoBarra:
    """Lo que se ve de una barra en un instante (en reposo: el dato real)."""
    etiqueta: str
    x: float
    valores: tuple
    alfa: float
    color: str
    indice: int = -1          # lugar entre los datos finales; -1 si está saliendo


@dataclass(frozen=True)
class ParBarra:
    etiqueta: str
    x0: float
    x1: float
    v0: tuple
    v1: tuple
    a0: float
    a1: float
    color: str
    indice: int


def emparejar_barras(previos: Sequence[ElementoBarra], nuevos: Sequence[tuple[str, tuple]],
                     colores: Sequence[str]) -> list[ParBarra]:
    """Relaciona lo que se veía con los datos nuevos **por etiqueta**. Las que siguen parten de su altura anterior; las
    nuevas entran desde cero en su sitio; las que ya no están se encogen y se desvanecen donde estaban."""
    ck_prev = claves([p.etiqueta for p in previos])
    ck_new = claves([e for e, _ in nuevos])
    prev = dict(zip(ck_prev, previos))
    idx = {k: i for i, k in enumerate(ck_new)}
    n = len(nuevos[0][1]) if nuevos else (len(previos[0].valores) if previos else 1)
    ceros = (0.0,) * n
    pares: list[ParBarra] = []
    for k in unir(ck_prev, ck_new):
        p, i = prev.get(k), idx.get(k)
        if i is None:                                       # sale: se encoge y se desvanece donde estaba
            pares.append(ParBarra(p.etiqueta, p.x, p.x, p.valores, ceros, p.alfa, 0.0, p.color, -1))
            continue
        etiqueta, v1 = nuevos[i]
        if p is None:                                       # entra: crece desde cero en su sitio
            pares.append(ParBarra(etiqueta, i, i, ceros, tuple(v1), 0.0, 1.0, colores[i], i))
        else:                                               # sigue: viaja y cambia desde lo que mostraba
            pares.append(ParBarra(etiqueta, p.x, i, p.valores, tuple(v1), p.alfa, 1.0, colores[i], i))
    return pares


@dataclass(frozen=True)
class PuntoVisible:
    etiqueta: str
    x: float
    y: float
    alfa: float = 1.0
    indice: int = -1


@dataclass(frozen=True)
class ParPunto:
    etiqueta: str
    x0: float
    y0: float
    x1: float
    y1: float
    a0: float
    a1: float
    indice: int


def emparejar_puntos(previos: Sequence[PuntoVisible], nuevos: Sequence[tuple[str, float]]) -> list[ParPunto]:
    """Como ``emparejar_barras`` para una serie: los puntos que siguen conservan su lugar y valor anteriores. Un punto
    nuevo **brota** del vecino que sigue (la línea se alarga, sin lecturas inventadas) y uno que sale **se pliega** sobre
    él; el orden en x se mantiene monótono, así que la línea nunca se cruza. Si no queda ninguno en común, los nuevos
    crecen desde la base y los viejos bajan a ella."""
    ck_prev = claves([p.etiqueta for p in previos])
    ck_new = claves([e for e, _ in nuevos])
    prev = dict(zip(ck_prev, previos))
    idx = {k: i for i, k in enumerate(ck_new)}
    orden = unir(ck_prev, ck_new)
    pares: list[ParPunto | None] = []
    for k in orden:
        p, i = prev.get(k), idx.get(k)
        if p is not None and i is not None:
            pares.append(ParPunto(p.etiqueta, p.x, p.y, i, nuevos[i][1], p.alfa, 1.0, i))
        else:
            pares.append(None)
    quedan = [j for j, par in enumerate(pares) if par is not None]
    for j, k in enumerate(orden):
        if pares[j] is not None:
            continue
        ancla = None
        if quedan:
            antes = [q for q in quedan if q < j]
            ancla = pares[antes[-1] if antes else quedan[0]]
        p, i = prev.get(k), idx.get(k)
        if i is not None:                                   # nace en el vecino
            x0, y0 = (ancla.x0, ancla.y0) if ancla else (float(i), 0.0)
            pares[j] = ParPunto(nuevos[i][0], x0, y0, i, nuevos[i][1], 0.0, 1.0, i)
        else:                                               # se pliega sobre el vecino
            x1, y1 = (ancla.x1, ancla.y1) if ancla else (p.x, 0.0)
            pares[j] = ParPunto(p.etiqueta, p.x, p.y, x1, y1, p.alfa, 0.0, -1)
    return [par for par in pares if par is not None]


def revelado(n: int, f: float) -> tuple[int, float]:
    """Trazado progresivo de ``n`` puntos al avance ``f`` (0–1): (último punto completo, fracción hacia el siguiente)."""
    if n <= 1:
        return 0, 0.0
    frente = max(0.0, min(1.0, f)) * (n - 1)
    k = min(int(math.floor(frente)), n - 1)
    return k, (0.0 if k >= n - 1 else frente - k)


# ======================================================================================= controladores
class _Controlador(QObject):
    """Ciclo de vida común: una sola animación viva, cancelable y liberada; ``terminar`` salta al estado final."""

    def __init__(self, plot: pg.PlotWidget) -> None:
        super().__init__(plot)
        self._plot = plot
        self._anim: QVariantAnimation | None = None
        self._f = 1.0
        self._timer_revelar: QTimer | None = None

    def _correr(self, ms: int, curva: QEasingCurve.Type) -> None:
        _cancelar(self._anim)
        self._f = 0.0
        self._anim = widgets.animar(self, 0.0, 1.0, widgets._ms(ms), self._paso, self._fin, curva)

    def _paso(self, f: float) -> None:
        if sip.isdeleted(self):
            return
        self._f = f
        self._dibujar(f)

    def _fin(self) -> None:
        self._anim = None

    def en_transicion(self) -> bool:
        return self._anim is not None and self._anim.state() == QVariantAnimation.State.Running

    def terminar(self) -> None:
        """Salta al estado final real (lo usa Guardar PNG: se exporta siempre el dato definitivo)."""
        if self._timer_revelar is not None:
            self._timer_revelar.stop()
        _cancelar(self._anim)
        self._anim = None
        self._f = 1.0
        self._dibujar(1.0)

    def _dibujar(self, f: float) -> None:        # pragma: no cover - lo define cada gráfica
        raise NotImplementedError

    def revelar(self, retardo: int = 0) -> None:
        """Repite la entrada inicial (la baldosa acaba de aparecer o de abrirse la pantalla)."""
        if self._timer_revelar is None:
            self._timer_revelar = QTimer(self)
            self._timer_revelar.setSingleShot(True)
            self._timer_revelar.timeout.connect(self._revelar_ya)
        if retardo > 0 and widgets.ANIMAR:
            self._ocultar_para_revelar()
            self._timer_revelar.start(retardo)
        else:
            self._revelar_ya()

    def _ocultar_para_revelar(self) -> None:    # pragma: no cover
        pass

    def _revelar_ya(self) -> None:              # pragma: no cover
        raise NotImplementedError


class GraficaBarras(_Controlador):
    """Barras (una o dos series) que se transforman en vez de reiniciarse. Dueña de los ``BarGraphItem``, de las cifras
    sobre cada barra y de los ticks del eje; el ``HoverBarras`` le pide los realces con ``poner_alfas``."""

    def __init__(self, plot: pg.PlotWidget, formato: Callable[[float], str], color_texto: str, *,
                 colores_serie: Sequence[str] | None = None, ancho: float = 0.6,
                 desplazamientos: Sequence[float] = (0.0,), cifras: bool = True) -> None:
        super().__init__(plot)
        self._formato = formato
        self._color_texto = color_texto
        self._colores_serie = list(colores_serie) if colores_serie else None
        self._desp = tuple(desplazamientos)
        self._cifras = cifras
        self.items = [pg.BarGraphItem(x=[], height=[], width=ancho, pen=pg.mkPen(None)) for _ in self._desp]
        for item in self.items:
            plot.addItem(item)
        self._textos: list[pg.TextItem] = []
        self._elementos: list[ElementoBarra] = []     # lo que se dibuja ahora (en reposo, los datos reales)
        self._pares: list[ParBarra] = []
        self._finales: list[tuple[str, tuple]] = []
        self._colores: list[str] = []
        self._alfas: list[float] = []                 # realce del hover, por índice de dato final
        self._pulso: tuple[int, float] = (-1, 0.0)
        self._a_pulso: QVariantAnimation | None = None
        self._rango0 = self._rango1 = (-0.8, 0.8, 1.0)
        self._muchas = False
        self._abreviar = False
        self._cifra_en: set[str] = set()
        self._intro = False
        self._ticks_puestos: list | None = None
        self._rango_puesto: tuple | None = None
        self._velo = False                              # oculta mientras espera un ``revelar`` con retardo

    # ----------------------------------------------------------------------- datos
    def finales(self) -> list[tuple[str, tuple]]:
        return list(self._finales)

    def alturas(self) -> list[float]:
        """Alturas de la primera serie tal como están dibujadas (en reposo, exactamente los datos reales)."""
        return [float(e.valores[0]) for e in self._elementos]

    def poner(self, datos: Sequence[tuple[str, Sequence[float]]], colores: Sequence[str], tope: float, paso: float,
              *, x_rango: tuple[float, float] | None = None) -> None:
        """Datos nuevos: desde lo que se ve hacia ellos. ``tope``/``paso`` = escala del eje Y que corresponde a los datos."""
        nuevos = [(e, tuple(float(x) for x in v)) for e, v in datos]
        colores = list(colores)
        n = len(nuevos)
        rango1 = (*(x_rango or (-0.8, n - 0.2)), float(tope))
        if nuevos == self._finales and colores == self._colores and rango1 == self._rango1 and self._elementos:
            return                                        # nada cambió: no hay nada que mover
        self._finales, self._colores, self._rango1 = nuevos, colores, rango1
        self._muchas = n > 6
        self._abreviar = self._muchas
        mayor = max([abs(v[0]) for _, v in nuevos] + [0.0]) or 1.0
        self._mayor = mayor
        self._plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        previos = list(self._elementos)
        visible = self._plot.isVisible() and widgets.ANIMAR
        self._intro = not previos
        self._pares = emparejar_barras(previos, nuevos, colores)
        self._cifra_en = {p.etiqueta for p in self._pares
                          if not self._muchas or max(abs(p.v0[0]), abs(p.v1[0])) >= PRESENCIA_DESDE * mayor}
        self._rango0 = self._rango_actual() if previos else (rango1[0], rango1[1], rango1[2])
        if not visible:
            self.terminar()
            return
        self._velo = False
        self._correr(MS_ENTRADA if self._intro else MS_ACTUALIZA,
                     QEasingCurve.Type.Linear if self._intro else QEasingCurve.Type.OutCubic)

    def _rango_actual(self) -> tuple[float, float, float]:
        return self._rango_puesto or self._rango1    # type: ignore[return-value]

    def _revelar_ya(self) -> None:
        self._velo = False
        if not self._finales or not self._plot.isVisible():
            self.terminar()
            return
        self._elementos = []
        self._pares = emparejar_barras([], self._finales, self._colores)
        self._intro = True
        self._rango0 = self._rango1
        self._correr(MS_ENTRADA, QEasingCurve.Type.Linear)

    def _ocultar_para_revelar(self) -> None:
        self._velo = True
        _cancelar(self._anim)
        self._anim = None
        self._elementos = []
        self._render()

    # --------------------------------------------------------------------- dibujo
    def _progreso(self, par: ParBarra, rango: int, n: int, f: float) -> float:
        """Avance de una barra (0–1). En la entrada inicial se escalonan de izquierda a derecha; luego, todas a la vez."""
        if not self._intro:
            return f
        k = 0.55
        u = max(0.0, min(1.0, f * (1 + k) - k * (rango / max(1, n - 1))))
        return 1 - (1 - u) ** 3

    def _dibujar(self, f: float) -> None:
        pares = self._pares
        if f >= 1.0:
            self._elementos = [ElementoBarra(p.etiqueta, p.x1, p.v1, 1.0, p.color, p.indice)
                               for p in pares if p.a1 > 0]
            rango = self._rango1
        else:
            n = len([p for p in pares if p.indice >= 0])
            els = []
            for j, p in enumerate(pares):
                u = self._progreso(p, p.indice if p.indice >= 0 else j, n, f)
                a = _lerp(p.a0, p.a1, min(1.0, u * (2.6 if p.a1 < p.a0 else 3.0)))
                els.append(ElementoBarra(p.etiqueta, _lerp(p.x0, p.x1, u),
                                         tuple(_lerp(a0, a1, u) for a0, a1 in zip(p.v0, p.v1)), a, p.color, p.indice))
            self._elementos = els
            rango = tuple(_lerp(a, b, f) for a, b in zip(self._rango0, self._rango1))
        self._rango_puesto = rango                       # type: ignore[assignment]
        self._render()

    def _render(self) -> None:
        els = self._elementos
        hay = bool(els) and not self._velo
        for s, item in enumerate(self.items):
            item.setVisible(hay)
            if not hay:
                continue
            marca, fuerza = self._pulso
            brushes = []
            for e in els:
                color = QColor(self._colores_serie[s] if self._colores_serie else e.color)
                realce = self._alfas[e.indice] if 0 <= e.indice < len(self._alfas) else 1.0
                if e.indice == marca and fuerza > 0:
                    color = color.lighter(100 + int(45 * fuerza))
                color.setAlphaF(max(0.0, min(1.0, e.alfa * realce)))
                brushes.append(QBrush(color))
            item.setOpts(x=[e.x + self._desp[s] for e in els], height=[e.valores[s] for e in els], brushes=brushes)
        self._cifras_y_ejes(els if not self._velo else [])

    def _cifras_y_ejes(self, els: list[ElementoBarra]) -> None:
        plot = self._plot
        if self._cifras:
            while len(self._textos) < len(els):
                texto = pg.TextItem("", color=self._color_texto, anchor=(0.5, 1.0))
                plot.addItem(texto)
                self._textos.append(texto)
            for k, texto in enumerate(self._textos):
                if k >= len(els) or els[k].etiqueta not in self._cifra_en:
                    texto.setVisible(False)
                    continue
                e = els[k]
                cifra = self._formato(e.valores[0])
                if getattr(texto, "_ultima", None) != cifra:
                    texto.setText(cifra)
                    texto._ultima = cifra               # type: ignore[attr-defined]
                texto.setPos(e.x, e.valores[0])
                texto.setOpacity(max(0.0, min(1.0, e.alfa)))
                texto.setVisible(True)
        ticks = [(round(e.x, 3), etiqueta_corta(e.etiqueta) if self._abreviar else e.etiqueta)
                 for e in els if e.indice >= 0 or self._intro]
        if ticks != self._ticks_puestos:
            self._ticks_puestos = ticks
            plot.getAxis("bottom").setTicks([ticks])
        if els or self._rango_puesto is not None:
            lo, hi, tope = self._rango_puesto or self._rango1
            if (lo, hi, tope) != getattr(self, "_rango_aplicado", None):
                self._rango_aplicado = (lo, hi, tope)
                plot.setXRange(lo, hi, padding=0)
                plot.setYRange(0, tope, padding=0)

    # ---------------------------------------------------------------- hover y clic
    def poner_alfas(self, alfas: list[float]) -> None:
        """Realce del hover por índice de dato final (1 = la señalada, el resto atenuado). Solo repinta los pinceles."""
        self._alfas = list(alfas)
        if self._elementos and not sip.isdeleted(self):
            self._render()

    def pulsar(self, indice: int) -> None:
        """Destello breve de la barra pulsada: la selección se distingue del hover."""
        _cancelar(self._a_pulso)

        def paso(v: float) -> None:
            if not sip.isdeleted(self):
                self._pulso = (indice, v)
                self._render()

        def fin() -> None:
            self._a_pulso = None
            paso(0.0)

        self._pulso = (indice, 1.0)
        self._a_pulso = widgets.animar(self, 1.0, 0.0, widgets._ms(340), paso, fin, QEasingCurve.Type.OutCubic)
        if self._a_pulso is None:
            self._pulso = (-1, 0.0)

    def terminar(self) -> None:
        _cancelar(self._a_pulso)
        self._a_pulso = None
        self._pulso = (-1, 0.0)
        self._rango0 = self._rango1
        if not self._pares and self._finales:
            self._pares = emparejar_barras(self._elementos, self._finales, self._colores)
        self._intro = False
        super().terminar()
        self._velo = False
        self._render()


class GraficaLinea(_Controlador):
    """Línea con área y puntos que se transforma en vez de reiniciarse. La primera vez se traza de izquierda a derecha;
    después cada punto viaja desde donde estaba, los nuevos brotan del vecino y la línea se alarga sin reiniciarse."""

    TAM_PUNTO = 8

    def __init__(self, plot: pg.PlotWidget, color: str, color_borde: str) -> None:
        super().__init__(plot)
        relleno = QColor(color)
        relleno.setAlpha(45)
        self.curva = pg.PlotDataItem([], [], pen=pg.mkPen(color, width=3), fillLevel=0, brush=pg.mkBrush(relleno))
        self.puntos = pg.ScatterPlotItem(pen=pg.mkPen(color_borde), brush=pg.mkBrush(color), size=self.TAM_PUNTO)
        plot.addItem(self.curva)
        plot.addItem(self.puntos)
        self._visibles: list[PuntoVisible] = []       # lo que se dibuja ahora (en reposo, los datos reales)
        self._pares: list[ParPunto] = []
        self._finales: list[tuple[str, float]] = []
        self._rango0 = self._rango1 = (-0.5, 0.5, 1.0)
        self._rango_puesto: tuple | None = None
        self._un_dia = False
        self._intro = False
        self._ticks_puestos: list | None = None
        self._rango_aplicado: tuple | None = None
        self._velo = False

    def finales(self) -> list[tuple[str, float]]:
        return list(self._finales)

    def dibujados(self) -> list[tuple[float, float]]:
        return [(p.x, p.y) for p in self._visibles]

    def poner(self, datos: Sequence[tuple[str, float]], tope: float, paso: float) -> None:
        nuevos = [(h, float(v)) for h, v in datos]
        n = len(nuevos)
        rango1 = (-0.5, max(n - 0.5, 0.5), float(tope))
        if nuevos == self._finales and rango1 == self._rango1 and self._visibles:
            return
        previos = list(self._visibles)
        self._finales, self._rango1 = nuevos, rango1
        self._un_dia = len({h[:10] for h, _ in nuevos}) == 1
        self._plot.getAxis("left").setTickSpacing(major=paso, minor=paso)
        self._pares = emparejar_puntos(previos, nuevos)
        self._intro = not previos
        self._rango0 = (self._rango_puesto or rango1) if previos else rango1
        if not (self._plot.isVisible() and widgets.ANIMAR) or not nuevos:
            self.terminar()
            return
        self._velo = False
        self._correr(MS_ENTRADA + 60 if self._intro else MS_ACTUALIZA + 60,
                     QEasingCurve.Type.Linear if self._intro else QEasingCurve.Type.InOutCubic)

    def _revelar_ya(self) -> None:
        self._velo = False
        if not self._finales or not self._plot.isVisible():
            self.terminar()
            return
        self._visibles = []
        self._pares = emparejar_puntos([], self._finales)
        self._intro = True
        self._rango0 = self._rango1
        self._correr(MS_ENTRADA + 60, QEasingCurve.Type.Linear)

    def _ocultar_para_revelar(self) -> None:
        self._velo = True
        _cancelar(self._anim)
        self._anim = None
        self._visibles = []
        self._dibujar_puntos([], [], [])

    def _dibujar(self, f: float) -> None:
        pares = self._pares
        if f >= 1.0:
            self._visibles = [PuntoVisible(p.etiqueta, p.x1, p.y1, 1.0, p.indice) for p in pares if p.a1 > 0]
            self._rango_puesto = self._rango1
            xs = [p.x for p in self._visibles]
            ys = [p.y for p in self._visibles]
            self._dibujar_puntos(xs, ys, [1.0] * len(xs))
            self._ejes(self._visibles)
            return
        self._rango_puesto = tuple(_lerp(a, b, f) for a, b in zip(self._rango0, self._rango1))   # type: ignore[assignment]
        if self._intro:
            fin = [p for p in pares]
            k, frac = revelado(len(fin), f)
            xs = [p.x1 for p in fin[:k + 1]]
            ys = [p.y1 for p in fin[:k + 1]]
            tam = [max(0.0, min(1.0, (f * (len(fin) - 1) - i) * 1.5 + 0.2)) for i in range(len(xs))]
            if frac > 0 and k + 1 < len(fin):
                a, b = fin[k], fin[k + 1]
                xs.append(_lerp(a.x1, b.x1, frac))
                ys.append(_lerp(a.y1, b.y1, frac))
                tam.append(0.0)
            if len(fin) == 1:
                tam = [min(1.0, f * 3)]
            self._visibles = [PuntoVisible(p.etiqueta, x, y, t, p.indice) for p, x, y, t in zip(fin, xs, ys, tam)]
        else:
            e = f
            vis = [PuntoVisible(p.etiqueta, _lerp(p.x0, p.x1, e), _lerp(p.y0, p.y1, e),
                                _lerp(p.a0, p.a1, min(1.0, e * 1.8) if p.a1 >= p.a0 else min(1.0, e * 2.0)), p.indice)
                   for p in pares]
            self._visibles = vis
            xs = [p.x for p in vis]
            ys = [p.y for p in vis]
            tam = [p.alfa for p in vis]
        self._dibujar_puntos(xs, ys, tam)
        self._ejes(self._visibles)

    def _dibujar_puntos(self, xs: list[float], ys: list[float], tam: list[float]) -> None:
        hay = bool(xs) and not self._velo
        self.curva.setVisible(hay)
        self.puntos.setVisible(hay)
        if not hay:
            return
        self.curva.setData(xs, ys)
        self.puntos.setData(x=xs, y=ys, size=[self.TAM_PUNTO * max(0.0, min(1.0, t)) for t in tam])

    def _ejes(self, visibles: list[PuntoVisible]) -> None:
        plot = self._plot
        ticks = [(round(p.x, 3), p.etiqueta[-5:] if self._un_dia else p.etiqueta[5:])
                 for p in visibles if p.indice >= 0 or self._intro]
        if ticks != self._ticks_puestos:
            self._ticks_puestos = ticks
            plot.getAxis("bottom").setTicks([ticks])
        rango = self._rango_puesto or self._rango1
        if rango != self._rango_aplicado:
            self._rango_aplicado = rango
            plot.setXRange(rango[0], rango[1], padding=0)
            plot.setYRange(0, rango[2], padding=0)

    def terminar(self) -> None:
        self._rango0 = self._rango1
        if not self._pares and self._finales:
            self._pares = emparejar_puntos(self._visibles, self._finales)
        self._intro = False
        self._velo = False
        super().terminar()
        if not self._finales:
            self._visibles = []
            self._dibujar_puntos([], [], [])
            self._ejes([])
