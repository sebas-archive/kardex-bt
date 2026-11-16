"""Gráfico del dashboard: un solo widget que dibuja los nueve tipos con los colores del tema.

Barras (verticales/horizontales/apiladas/comparativo), líneas, áreas, evolución temporal, circular y anillo. Incluye
tooltip al pasar el cursor, leyenda seleccionable (un clic oculta o muestra una serie o categoría), clic en una
categoría para filtrar (cuando la fuente lo permite) y animación al actualizar. Se adapta a su tamaño: en espacios
pequeños omite leyenda, etiquetas de valor y rotula menos el eje.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap)
from PyQt6.QtWidgets import QWidget

from ..dashboard_datos import Datos
from ..i18n import t
from .. import i18n
from ..tema import colores
from . import motion, widgets

PEQUENO = 260   # por debajo de este ancho se simplifica el dibujo


def formatear(v: float, unidad: str = "") -> str:
    if abs(v - round(v)) < 1e-9:
        texto = i18n.miles(int(round(v)))
    else:
        texto = i18n.miles(v, 1)
    return f"{texto} {unidad}".strip() if unidad else texto


def _ticks(vmin: float, vmax: float, n: int = 4) -> list[float]:
    rango = vmax - vmin if vmax > vmin else 1.0
    bruto = rango / n
    mag = 10 ** math.floor(math.log10(bruto))
    paso = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= bruto)
    ini = math.floor(vmin / paso) * paso
    fin = math.ceil(vmax / paso) * paso
    out, v = [], ini
    while v <= fin + paso * 0.001:
        out.append(round(v, 10))
        v += paso
    return out


def paleta() -> list[QColor]:
    c = colores()
    return [QColor(c[k]) for k in ("acento", "info", "aviso", "error", "texto_suave", "acento_suave")]


class GraficoPersonal(QWidget):
    elegido = pyqtSignal(str)      # clic en una categoría (si la fuente permite filtrar)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(110)
        self._datos = Datos()
        self._cargando = False    # sin datos todavía porque la consulta sigue en curso (no es «Sin datos»)
        self._fase_carga = 0.0
        self._a_carga: QVariantAnimation | None = None
        self._tipo = "barras"
        self._leyenda = True
        self._etiquetas = True
        self._drill = False
        self._prog = 1.0
        self._anim = None
        self._firma = None
        self._ocultas: set[int] = set()       # series ocultas desde la leyenda
        self._ocultas_cat: set[int] = set()   # categorías ocultas (circular/anillo)
        self._hover: int | None = None
        self._pos = QPointF()
        self._leyenda_zonas: list[tuple[QRectF, str, int]] = []
        self._geom: dict = {}
        # Capas de movimiento (cada una escribe su propia variable; el dibujo las combina):
        #   _prog   revelado desde el origen (primera vez, cambio de tipo, revelar())
        #   _mezcla transición de valores reales anteriores → nuevos (mismo tipo de gráfica)
        #   _hov/_dim/_g_idx  resalte suave bajo el cursor, atenuación del resto y guía vertical
        #   _vis_cat visibilidad suavizada de las categorías de un circular al usar la leyenda
        #   _fantasma imagen del tipo anterior que se funde al cambiar de tipo de gráfica
        self._mezcla = 1.0
        self._previos: dict[tuple[str, str], float] = {}
        self._a_mezcla = None
        self._fantasma: QPixmap | None = None
        self._alfa_fantasma = 0.0
        self._a_fantasma = None
        self._hov: dict[int, float] = {}
        self._dim = 0.0
        self._g_idx: float | None = None
        self._a_hover = None
        self._vis_cat: dict[int, float] = {}
        self._a_vis = None
        self._tip_prev: list[str] = []

    @property
    def cargando(self) -> bool:
        return self._cargando

    @cargando.setter
    def cargando(self, valor: bool) -> None:
        valor = bool(valor)
        if valor != self._cargando:
            self._cargando = valor
            self._sincronizar_carga()
            self.update()

    # ------------------------------------------------------------------ API
    def poner(self, datos: Datos, tipo: str, leyenda: bool = True, etiquetas: bool = True, drill: bool = False,
              animar: bool = True) -> None:
        """Dibuja ``datos``. El estado final siempre es exactamente el dato recibido; solo el camino hasta él se anima:
        misma gráfica con otros valores → los valores reales se interpolan; otro tipo → la imagen anterior se funde;
        primera vez → se revela desde su origen."""
        firma = (tuple(datos.etiquetas), tuple((s.nombre, tuple(s.valores)) for s in datos.series), tipo)
        cambio = firma != self._firma
        antes_tipo = self._tipo
        tenia = self._firma is not None and not self._datos.vacio
        misma_forma = tenia and antes_tipo == tipo and not datos.vacio
        fantasma = None
        if cambio and animar and widgets.ANIMAR and tenia and antes_tipo != tipo and self.isVisible() and self.width() > 0:
            fantasma = self.grab()                    # lo que se ve ahora: se funde hacia el tipo nuevo
        previos = self._valores_mostrados() if (cambio and animar and misma_forma) else {}
        self._firma = firma
        self._datos, self._tipo, self._leyenda, self._etiquetas, self._drill = datos, tipo, leyenda, etiquetas, drill
        self._ocultas = {i for i in self._ocultas if i < len(datos.series)}
        self._ocultas_cat = {i for i in self._ocultas_cat if i < len(datos.etiquetas)}
        widgets._detener(self._anim)
        widgets._detener(self._a_mezcla)
        if cambio and animar:
            if misma_forma:
                self._prog, self._previos, self._mezcla = 1.0, previos, 0.0
                self._a_mezcla = widgets.animar(self, 0.0, 1.0, motion.dur(440), self._paso_mezcla, self._fin_mezcla)
            else:
                self._previos, self._mezcla, self._prog = {}, 1.0, 0.0
                self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(650), self._avance)
                if fantasma is not None:
                    self._fantasma, self._alfa_fantasma = fantasma, 1.0
                    widgets._detener(self._a_fantasma)
                    self._a_fantasma = widgets.animar(self, 1.0, 0.0, motion.dur(280), self._paso_fantasma, self._fin_fantasma)
        else:
            self._previos, self._mezcla, self._prog = {}, 1.0, 1.0
        self._sincronizar_carga()
        self.update()

    def revelar(self) -> None:
        """Repite el revelado desde el origen (lo usa la entrada del Dashboard). No cambia ningún dato."""
        if not widgets.ANIMAR or self._datos.vacio or not self.isVisible():
            return
        widgets._detener(self._a_mezcla)
        widgets._detener(self._anim)
        self._previos, self._mezcla, self._prog = {}, 1.0, 0.0
        self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(650), self._avance)
        self.update()

    def limpiar(self) -> None:
        """Olvida lo dibujado (y sus transiciones): el próximo ``poner`` se revela desde cero en vez de interpolar
        desde otra gráfica sin relación (p. ej. la vista previa al abrir la configuración de otro gráfico)."""
        for anim in (self._anim, self._a_mezcla, self._a_fantasma):
            widgets._detener(anim)
        self._firma, self._datos = None, Datos()
        self._previos, self._mezcla, self._prog = {}, 1.0, 1.0
        self._fantasma, self._alfa_fantasma = None, 0.0
        self._hov, self._dim, self._g_idx, self._vis_cat = {}, 0.0, None, {}
        self.update()

    def _val(self, s: int, i: int) -> float:
        """El valor que se dibuja ahora: el real, o —durante la transición— el intermedio entre el anterior y el real."""
        v = self._datos.series[s].valores[i]
        if self._mezcla >= 1.0 or not self._previos:
            return v
        ant = self._previos.get((self._datos.etiquetas[i], self._datos.series[s].nombre))
        if ant is None:
            return v * self._mezcla                 # un elemento nuevo crece desde su origen
        return ant + (v - ant) * self._mezcla

    def _valores_mostrados(self) -> dict[tuple[str, str], float]:
        d = self._datos
        if d.vacio:
            return {}
        return {(d.etiquetas[i], d.series[s].nombre): self._val(s, i)
                for s in range(len(d.series)) for i in range(len(d.etiquetas))}

    def _paso_mezcla(self, v: float) -> None:
        self._mezcla = v
        self.update()

    def _fin_mezcla(self) -> None:
        self._previos, self._mezcla = {}, 1.0
        self.update()

    def _paso_fantasma(self, v: float) -> None:
        self._alfa_fantasma = v
        self.update()

    def _fin_fantasma(self) -> None:
        self._fantasma, self._alfa_fantasma = None, 0.0
        self.update()

    @staticmethod
    def _prog_i(i: int, n: int, prog: float) -> float:
        """Revelado escalonado: cada barra arranca un poco después de la anterior (todas llegan a 1 con ``prog`` = 1)."""
        if prog >= 1.0 or n <= 1:
            return prog
        x = max(0.0, min(1.0, prog * 1.6 - 0.6 * i / (n - 1)))
        return 1.0 - (1.0 - x) ** 3

    def _resaltar(self, col: QColor, hv: float) -> QColor:
        """Barra/sector bajo el cursor: más claro; el resto se atenúa (suavemente, según ``_hov`` y ``_dim``)."""
        col = QColor(col)
        if hv > 0.01:
            col = col.lighter(int(100 + 12 * hv))
        if self._dim > 0.01:
            col.setAlphaF(col.alphaF() * (1.0 - 0.5 * self._dim * (1.0 - hv)))
        return col

    # ---- carga: esqueleto discreto (no un spinner)
    def _sincronizar_carga(self) -> None:
        debe = self._cargando and self._datos.vacio and motion.decorativo() and self.isVisible()
        if debe and self._a_carga is None:
            anim = QVariantAnimation(self)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(1500)
            anim.setLoopCount(-1)
            anim.setEasingCurve(QEasingCurve.Type.Linear)
            anim.valueChanged.connect(self._paso_carga)
            anim.start()
            self._a_carga = anim
        elif not debe and self._a_carga is not None:
            self._a_carga.stop()
            self._a_carga.deleteLater()
            self._a_carga = None

    def _paso_carga(self, v) -> None:
        self._fase_carga = float(v)
        self.update()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._sincronizar_carga()

    def hideEvent(self, evento) -> None:
        if self._a_carga is not None:                 # el ciclo solo corre con el gráfico a la vista
            self._a_carga.stop()
            self._a_carga.deleteLater()
            self._a_carga = None
        super().hideEvent(evento)

    def _esqueleto(self, p: QPainter, c: dict) -> None:
        """Columnas tenues con un destello que las recorre de izquierda a derecha mientras llega el dato real."""
        area = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        alturas = (0.42, 0.66, 0.5, 0.86, 0.58, 0.74, 0.46)
        n = len(alturas) if area.width() > 220 else 5
        slot = area.width() / n
        ancho = min(slot * 0.56, 36.0)
        foco = self._fase_carga * 1.6 - 0.3           # posición del destello (en fracción del ancho)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            alto = area.height() * alturas[i] * 0.82
            brillo = max(0.0, 1.0 - abs(foco - (i + 0.5) / n) / 0.22)
            col = QColor(c["texto_suave"])
            col.setAlphaF(0.12 + 0.16 * brillo)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(area.left() + slot * i + (slot - ancho) / 2, area.bottom() - alto, ancho, alto), 5, 5)

    def _avance(self, v: float) -> None:
        self._prog = v
        self.update()

    def tooltip_texto(self) -> list[str]:
        """Las líneas del tooltip vigente (para pruebas)."""
        return self._lineas_tooltip()

    # ------------------------------------------------------------------ ratón
    def mouseMoveEvent(self, evento) -> None:
        self._pos = evento.position()
        previo = self._hover
        self._hover = self._buscar(self._pos)
        sobre_leyenda = any(z.contains(self._pos) for z, _k, _i in self._leyenda_zonas)
        clicable = sobre_leyenda or (self._drill and self._hover is not None)
        self.setCursor(Qt.CursorShape.PointingHandCursor if clicable else Qt.CursorShape.ArrowCursor)
        if self._hover != previo:
            self._animar_hover()
        if self._hover != previo or self._hover is not None:
            self.update()

    def leaveEvent(self, evento) -> None:
        if self._hover is not None:
            self._hover = None
            self._animar_hover()
        self.update()
        super().leaveEvent(evento)

    def _animar_hover(self) -> None:
        """Resalte suave del elemento bajo el cursor, atenuación del resto y guía vertical que se desliza."""
        widgets._detener(self._a_hover)
        idx = self._hover
        ini, dim0 = dict(self._hov), self._dim
        dim1 = 1.0 if idx is not None else 0.0
        g0 = self._g_idx if self._g_idx is not None else (float(idx) if idx is not None else 0.0)

        def paso(v: float) -> None:
            for k in set(ini) | ({idx} if idx is not None else set()):
                a = ini.get(k, 0.0)
                self._hov[k] = a + ((1.0 if k == idx else 0.0) - a) * v
            self._dim = dim0 + (dim1 - dim0) * v
            if idx is not None:
                self._g_idx = g0 + (idx - g0) * v
            self.update()

        def fin() -> None:
            self._hov = {k: x for k, x in self._hov.items() if x > 0.001}
            if self._dim <= 0.001:
                self._g_idx = None

        self._a_hover = widgets.animar(self, 0.0, 1.0, motion.dur(150), paso, fin)

    def _alternar_cat(self, i: int) -> None:
        """Oculta o muestra una categoría del circular: su sector se cierra/abre y los demás se reparten el círculo."""
        n = len(self._datos.etiquetas)
        ini = {k: self._vis(k) for k in range(n)}
        self._ocultas_cat.symmetric_difference_update({i})
        fin = {k: (0.0 if k in self._ocultas_cat else 1.0) for k in range(n)}
        widgets._detener(self._a_vis)

        def paso(v: float) -> None:
            self._vis_cat = {k: ini[k] + (fin[k] - ini[k]) * v for k in range(n)}
            self.update()

        def terminar() -> None:
            self._vis_cat = {}
            self.update()

        self._a_vis = widgets.animar(self, 0.0, 1.0, motion.dur(280), paso, terminar, QEasingCurve.Type.OutCubic)

    def _vis(self, i: int) -> float:
        if i in self._vis_cat:
            return self._vis_cat[i]
        return 0.0 if i in self._ocultas_cat else 1.0

    def mousePressEvent(self, evento) -> None:
        pos = evento.position()
        for zona, clase, i in self._leyenda_zonas:
            if zona.contains(pos):
                if clase == "serie":
                    self._ocultas.symmetric_difference_update({i})
                    if len(self._ocultas) >= len(self._datos.series):
                        self._ocultas.clear()      # nunca se queda sin ninguna serie visible
                else:
                    self._alternar_cat(i)
                self.update()
                return
        if self._drill and self._hover is not None and 0 <= self._hover < len(self._datos.etiquetas):
            self.elegido.emit(self._datos.etiquetas[self._hover])
        super().mousePressEvent(evento)

    def _buscar(self, pos: QPointF) -> int | None:
        g = self._geom
        if not g:
            return None
        if g["clase"] == "cart":
            area: QRectF = g["area"]
            if not area.contains(pos) or g["n"] == 0:
                return None
            return max(0, min(g["n"] - 1, int((pos.x() - area.left()) / (area.width() / g["n"]))))
        if g["clase"] == "horiz":
            area = g["area"]
            if not area.contains(pos) or g["n"] == 0:
                return None
            return max(0, min(g["n"] - 1, int((pos.y() - area.top()) / (area.height() / g["n"]))))
        if g["clase"] == "pie":
            dx, dy = pos.x() - g["centro"].x(), pos.y() - g["centro"].y()
            r = math.hypot(dx, dy)
            if r > g["r_ext"] or r < g["r_int"]:
                return None
            ang = (math.degrees(math.atan2(-dy, dx)) - 90.0) % 360.0   # 0° arriba, sentido horario
            ang = (360.0 - ang) % 360.0
            for i, ini, fin in g["tramos"]:
                if ini <= ang < fin:
                    return i
        return None

    # ------------------------------------------------------------------ dibujo
    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._dibujar(p)
        if self._fantasma is not None and self._alfa_fantasma > 0.01:    # el tipo anterior se desvanece encima
            p.setOpacity(self._alfa_fantasma)
            p.drawPixmap(0, 0, self._fantasma)
        p.end()

    def _dibujar(self, p: QPainter) -> None:
        c = colores()
        self._leyenda_zonas = []
        self._geom = {}
        d = self._datos
        if d.vacio:
            if self._cargando and widgets.ANIMAR:
                self._esqueleto(p, c)
                return
            p.setPen(QColor(c["texto_suave"]))
            vacio = t("Sin datos en este período") if d.temporal else t("Sin datos")
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       t("Cargando…") if self._cargando else vacio)
            return
        area = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        visibles = [i for i in range(len(d.series)) if i not in self._ocultas] or list(range(len(d.series)))
        if self._leyenda and len(d.series) > 1 and area.width() >= PEQUENO - 20:
            area = self._leyenda_superior(p, area, c)
        if self._tipo in ("circular", "anillo"):
            self._circular(p, area, c)
        elif self._tipo == "barras_h":
            self._horizontal(p, area, c, visibles)
        else:
            self._cartesiano(p, area, c, visibles)
        self._tooltip(p, c)

    # ---- leyenda (varias series)
    def _leyenda_superior(self, p: QPainter, area: QRectF, c: dict) -> QRectF:
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        colores_s = paleta()
        x, y = area.left() + 2, area.top() + 2
        for i, serie in enumerate(self._datos.series):
            ancho = fm.horizontalAdvance(serie.nombre) + 26
            if x + ancho > area.right() and x > area.left() + 4:
                x, y = area.left() + 2, y + 18
            zona = QRectF(x - 2, y - 2, ancho, 18)
            oculto = i in self._ocultas
            p.setPen(Qt.PenStyle.NoPen)
            col = QColor(colores_s[i % len(colores_s)])
            if oculto:
                col.setAlpha(70)
            p.setBrush(col)
            p.drawEllipse(QPointF(x + 5, y + 7), 4.5, 4.5)
            texto = QColor(c["texto_suave"] if oculto else c["texto"])
            p.setPen(texto)
            p.drawText(QRectF(x + 14, y - 2, ancho - 14, 18), int(Qt.AlignmentFlag.AlignVCenter), serie.nombre)
            self._leyenda_zonas.append((zona, "serie", i))
            x += ancho + 6
        return QRectF(area.left(), y + 22, area.width(), max(20.0, area.bottom() - y - 22))

    # ---- eje cartesiano
    def _rango_valores(self, visibles: list[int], apilado: bool) -> tuple[float, float]:
        d = self._datos
        if apilado:
            sumas = [sum(max(self._val(s, i), 0) for s in visibles) for i in range(len(d.etiquetas))]
            vmax, vmin = max(sumas + [0.0]), 0.0
        else:
            todos = [self._val(s, i) for s in visibles for i in range(len(d.etiquetas))]
            vmax, vmin = max(todos + [0.0]), min(todos + [0.0])
        return (vmin, vmax if vmax > vmin else vmin + 1.0)

    def _cartesiano(self, p: QPainter, area: QRectF, c: dict, visibles: list[int]) -> None:
        d, tipo = self._datos, self._tipo
        n = len(d.etiquetas)
        apilado = tipo == "apiladas"
        vmin, vmax = self._rango_valores(visibles, apilado)
        ticks = _ticks(vmin, vmax)
        vmin, vmax = min(vmin, ticks[0]), max(vmax, ticks[-1])
        if self._etiquetas and tipo == "barras" and area.height() > 140:   # sitio para el valor sobre/bajo la barra
            holgura = (vmax - vmin) * 0.09
            vmax += holgura if vmax > 0 else 0
            vmin -= holgura if vmin < 0 else 0
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        unidad = d.unidad if d.unidad == "%" else ""
        ancho_y = max(fm.horizontalAdvance(formatear(v, unidad)) for v in ticks) + 10
        pequeno = area.width() < PEQUENO
        plot = QRectF(area.left() + ancho_y, area.top() + 6, area.width() - ancho_y - 6, area.height() - 6 - 22)
        if plot.width() < 20 or plot.height() < 20:
            return
        escala = (plot.height()) / (vmax - vmin)

        def ypos(v: float) -> float:
            return plot.bottom() - (v - vmin) * escala

        slot = plot.width() / n
        self._geom = {"clase": "cart", "area": plot, "n": n}
        # rejilla y eje Y
        for v in ticks:
            y = ypos(v)
            p.setPen(QPen(QColor(c["borde"]), 1.0, Qt.PenStyle.SolidLine if abs(v) < 1e-9 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(c["texto_tenue"]))
            p.drawText(QRectF(area.left(), y - 8, ancho_y - 6, 16),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), formatear(v, unidad))
        # eje X
        etiqueta_ancho = max((fm.horizontalAdvance(e) for e in d.etiquetas), default=10) + 10
        paso = max(1, math.ceil(etiqueta_ancho / slot))
        p.setPen(QColor(c["texto_tenue"]))
        for i, e in enumerate(d.etiquetas):
            if i % paso == 0:
                caja = QRectF(plot.left() + slot * i + slot / 2 - slot * paso / 2, plot.bottom() + 4, slot * paso, 16)
                p.drawText(caja, int(Qt.AlignmentFlag.AlignCenter),
                           fm.elidedText(e, Qt.TextElideMode.ElideRight, int(slot * paso) - 2))
        # banda del elemento bajo el cursor
        for k, hv in self._hov.items():
            if 0 <= k < n and hv > 0.01:
                banda = QColor(c["texto"])
                banda.setAlpha(int(14 * hv))
                p.fillRect(QRectF(plot.left() + slot * k, plot.top(), slot, plot.height()), banda)
        colores_s = paleta()
        prog = self._prog
        if tipo in ("barras", "apiladas", "comparativo"):
            self._barras(p, c, plot, slot, ypos, visibles, apilado, pequeno, fm, colores_s, prog)
        else:
            self._lineas(p, c, plot, slot, ypos, visibles, tipo, colores_s, prog, n)

    def _color_barra(self, serie: int, v: float, colores_s: list[QColor]) -> QColor:
        if self._datos.semaforo:
            c = colores()
            return QColor(c["error"] if v < 0 else c["aviso"] if v > 0 else c["texto_suave"])
        return QColor(colores_s[serie % len(colores_s)])

    def _barras(self, p, c, plot, slot, ypos, visibles, apilado, pequeno, fm, colores_s, prog) -> None:
        d = self._datos
        n = len(d.etiquetas)
        k = 1 if apilado else len(visibles)
        ancho = min(slot * 0.64, 54.0 if k == 1 else 70.0)
        sub = ancho / k
        y0 = ypos(0.0)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            centro = plot.left() + slot * i + slot / 2
            acumulado = 0.0
            hv = self._hov.get(i, 0.0)
            pr = self._prog_i(i, n, prog)
            for j, s in enumerate(visibles):
                v = d.series[s].valores[i]
                vm = self._val(s, i)                  # el valor que se dibuja (intermedio durante una transición)
                col = self._resaltar(self._color_barra(s, v, colores_s), hv)
                p.setBrush(col)
                if apilado:
                    vm = max(vm, 0.0)
                    if v <= 0 and vm <= 0.0001:
                        continue
                    ya, yb = ypos(acumulado * pr), ypos((acumulado + vm) * pr)
                    acumulado += vm
                    x = centro - ancho / 2
                    rect = QRectF(x, yb, ancho, max(0.0, ya - yb))
                else:
                    x = centro - ancho / 2 + sub * j
                    yv = ypos(vm * pr)
                    rect = QRectF(x + (1 if k > 1 else 0), min(y0, yv), max(1.0, sub - (2 if k > 1 else 0)), abs(y0 - yv))
                if rect.height() < 0.5:
                    continue
                camino = QPainterPath()
                camino.addRoundedRect(rect, min(4.0, rect.width() / 2), min(4.0, rect.width() / 2))
                p.drawPath(camino)
                if self._etiquetas and not apilado and k == 1 and not pequeno and slot >= 30 and pr > 0.98:
                    p.setPen(QColor(c["texto"]))
                    texto = formatear(v, "%" if d.unidad == "%" else "")
                    arriba = v >= 0
                    p.drawText(QRectF(centro - slot / 2, rect.top() - 16 if arriba else rect.bottom() + 1, slot, 15),
                               int(Qt.AlignmentFlag.AlignCenter), texto)
                    p.setPen(Qt.PenStyle.NoPen)

    def _lineas(self, p, c, plot, slot, ypos, visibles, tipo, colores_s, prog, n) -> None:
        d = self._datos
        p.save()
        p.setClipRect(QRectF(plot.left() - 2, plot.top() - 4, plot.width() * prog + 4, plot.height() + 8))
        if self._dim > 0.02 and self._g_idx is not None and prog >= 1.0:    # guía vertical que sigue a la lectura
            gx = plot.left() + slot * self._g_idx + slot / 2
            guia = QColor(c["texto_tenue"])
            guia.setAlphaF(0.6 * self._dim)
            p.setPen(QPen(guia, 1.0, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(gx, plot.top()), QPointF(gx, plot.bottom()))
        for orden, s in enumerate(visibles):
            col = QColor(colores_s[s % len(colores_s)])
            puntos = [QPointF(plot.left() + slot * i + slot / 2, ypos(self._val(s, i))) for i in range(n)]
            if len(puntos) == 1:
                puntos = [QPointF(puntos[0].x() - slot / 4, puntos[0].y()), QPointF(puntos[0].x() + slot / 4, puntos[0].y())]
            linea = QPainterPath(puntos[0])
            for q in puntos[1:]:
                linea.lineTo(q)
            if tipo in ("area", "evolucion"):
                relleno = QPainterPath(linea)
                relleno.lineTo(QPointF(puntos[-1].x(), ypos(0.0)))
                relleno.lineTo(QPointF(puntos[0].x(), ypos(0.0)))
                relleno.closeSubpath()
                grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
                alto = QColor(col)
                alto.setAlpha(int((110 if len(visibles) == 1 else 70) * min(1.0, prog * 1.5)))   # el área se «enciende»
                bajo = QColor(col)
                bajo.setAlpha(8)
                grad.setColorAt(0.0, alto)
                grad.setColorAt(1.0, bajo)
                p.fillPath(relleno, grad)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(col, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(linea)
            if n <= 40:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c["tarjeta"]))
                for i, q in enumerate(puntos if len(puntos) == n else []):
                    pop = max(0.0, min(1.0, (prog * 1.25 - (i + 0.5) / n) * 5.0))   # los puntos asoman al paso del trazo
                    if pop <= 0.01:
                        continue
                    hv = self._hov.get(i, 0.0)
                    radio = (3.0 + 1.5 * hv) * pop
                    hueco = QColor(c["tarjeta"])
                    relleno = QColor(int(hueco.red() + (col.red() - hueco.red()) * hv),
                                     int(hueco.green() + (col.green() - hueco.green()) * hv),
                                     int(hueco.blue() + (col.blue() - hueco.blue()) * hv))
                    p.setBrush(relleno)
                    p.setPen(QPen(col, 1.6))
                    p.drawEllipse(q, radio, radio)
        p.restore()

    # ---- barras horizontales
    def _horizontal(self, p: QPainter, area: QRectF, c: dict, visibles: list[int]) -> None:
        d = self._datos
        n = len(d.etiquetas)
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        vmin, vmax = self._rango_valores(visibles, False)
        ticks = _ticks(vmin, vmax, 4)
        vmin, vmax = min(vmin, ticks[0]), max(vmax, ticks[-1])
        izq = min(area.width() * 0.38, max(fm.horizontalAdvance(e) for e in d.etiquetas) + 12)
        plot = QRectF(area.left() + izq, area.top() + 4, area.width() - izq - 10, area.height() - 4 - 20)
        if plot.width() < 20 or plot.height() < 20:
            return
        escala = plot.width() / (vmax - vmin)

        def xpos(v: float) -> float:
            return plot.left() + (v - vmin) * escala

        slot = plot.height() / n
        self._geom = {"clase": "horiz", "area": QRectF(area.left(), plot.top(), area.width(), plot.height()), "n": n}
        unidad = d.unidad if d.unidad == "%" else ""
        for v in ticks:
            x = xpos(v)
            p.setPen(QPen(QColor(c["borde"]), 1.0, Qt.PenStyle.SolidLine if abs(v) < 1e-9 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            p.setPen(QColor(c["texto_tenue"]))
            p.drawText(QRectF(x - 30, plot.bottom() + 3, 60, 16), int(Qt.AlignmentFlag.AlignCenter), formatear(v, unidad))
        colores_s = paleta()
        k = len(visibles)
        grosor = min(slot * 0.62, 22.0)
        sub = grosor / k
        x0 = xpos(0.0)
        for i in range(n):
            centro = plot.top() + slot * i + slot / 2
            hv = self._hov.get(i, 0.0)
            pr = self._prog_i(i, n, self._prog)
            if hv > 0.01:
                banda = QColor(c["texto"])
                banda.setAlpha(int(14 * hv))
                p.fillRect(QRectF(area.left(), plot.top() + slot * i, area.width(), slot), banda)
            p.setPen(QColor(c["texto"]))
            p.drawText(QRectF(area.left(), centro - 8, izq - 8, 16),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       fm.elidedText(d.etiquetas[i], Qt.TextElideMode.ElideRight, int(izq - 10)))
            for j, s in enumerate(visibles):
                v = d.series[s].valores[i]
                col = self._resaltar(self._color_barra(s, v, colores_s), hv)
                xv = xpos(self._val(s, i) * pr)
                rect = QRectF(min(x0, xv), centro - grosor / 2 + sub * j, max(1.0, abs(xv - x0)), max(2.0, sub - (1 if k > 1 else 0)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                camino = QPainterPath()
                camino.addRoundedRect(rect, 4, 4)
                p.drawPath(camino)
                if self._etiquetas and k == 1 and pr > 0.98 and area.width() >= PEQUENO - 60:
                    p.setPen(QColor(c["texto"]))
                    texto = formatear(v, unidad)
                    ancho_t = fm.horizontalAdvance(texto) + 6
                    if v >= 0:
                        p.drawText(QRectF(rect.right() + 3, centro - 8, ancho_t, 16),
                                   int(Qt.AlignmentFlag.AlignVCenter), texto)
                    else:
                        p.drawText(QRectF(rect.left() - ancho_t - 3, centro - 8, ancho_t, 16),
                                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), texto)

    # ---- circular / anillo
    def _circular(self, p: QPainter, area: QRectF, c: dict) -> None:
        d = self._datos
        serie = d.series[0]
        # Peso de cada sector: su valor (intermedio durante una transición) por su visibilidad suavizada en la leyenda.
        pesos = {i: max(self._val(0, i), 0.0) * self._vis(i) for i in range(len(serie.valores))}
        indices = [i for i, w in pesos.items() if w > 0.0005]
        total = sum(pesos[i] for i in indices)
        colores_s = paleta()
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        lado_leyenda = self._leyenda and area.width() >= 300
        if lado_leyenda:
            ancho_ley = min(area.width() * 0.45, max(fm.horizontalAdvance(e) for e in d.etiquetas) + 90)
            zona_pie = QRectF(area.left(), area.top(), area.width() - ancho_ley, area.height())
        else:
            zona_pie = area
        lado = max(40.0, min(zona_pie.width(), zona_pie.height()) - 8)
        centro = QPointF(zona_pie.center().x(), zona_pie.center().y())
        r_ext = lado / 2
        r_int = r_ext * 0.60 if self._tipo == "anillo" else 0.0
        self._geom = {"clase": "pie", "centro": centro, "r_ext": r_ext, "r_int": r_int, "tramos": []}
        if total <= 0:
            p.setPen(QColor(c["texto_suave"]))
            p.drawText(area, int(Qt.AlignmentFlag.AlignCenter), t("Sin datos"))
        else:
            angulo = 0.0
            for i in indices:
                barrido = pesos[i] / total * 360.0
                self._geom["tramos"].append((i, angulo, angulo + barrido))
                hv = self._hov.get(i, 0.0)
                col = self._resaltar(QColor(colores_s[i % len(colores_s)]), hv)
                radio = r_ext + 3 * hv
                caja = QRectF(centro.x() - radio, centro.y() - radio, radio * 2, radio * 2)
                camino = QPainterPath()
                camino.moveTo(centro)
                camino.arcTo(caja, 90 - angulo, -barrido * self._prog)
                camino.closeSubpath()
                if r_int > 0:
                    hueco = QPainterPath()
                    hueco.addEllipse(centro, r_int, r_int)
                    camino = camino.subtracted(hueco)
                p.setPen(QPen(QColor(c["tarjeta"]), 2.0))
                p.setBrush(col)
                p.drawPath(camino)
                if barrido >= 24 and self._prog > 0.98 and r_ext > 46:
                    mitad = math.radians(90 - (angulo + barrido / 2))
                    rr = (r_ext + r_int) / 2 if r_int else r_ext * 0.66
                    p.setPen(QColor("#FFFFFF"))
                    p.drawText(QRectF(centro.x() + rr * math.cos(mitad) - 20, centro.y() - rr * math.sin(mitad) - 8, 40, 16),
                               int(Qt.AlignmentFlag.AlignCenter), f"{pesos[i] / total * 100:.0f}%")
                angulo += barrido
            if r_int > 0 and r_int > 26:
                p.setPen(QColor(c["texto"]))
                grande = QFont(fuente)
                grande.setPixelSize(18)
                grande.setBold(True)
                p.setFont(grande)
                p.drawText(QRectF(centro.x() - r_int, centro.y() - 18, r_int * 2, 22), int(Qt.AlignmentFlag.AlignCenter),
                           formatear(round(total) if (self._mezcla < 1.0 or self._vis_cat) else total))
                p.setFont(fuente)
                p.setPen(QColor(c["texto_suave"]))
                p.drawText(QRectF(centro.x() - r_int, centro.y() + 2, r_int * 2, 16), int(Qt.AlignmentFlag.AlignCenter),
                           t("Total"))
        if lado_leyenda:
            x = zona_pie.right() + 12
            y = area.top() + max(4.0, (area.height() - len(d.etiquetas) * 20) / 2)
            for i, e in enumerate(d.etiquetas):
                if y + 18 > area.bottom():
                    break
                oculto = i in self._ocultas_cat or serie.valores[i] <= 0
                col = QColor(colores_s[i % len(colores_s)])
                if oculto:
                    col.setAlpha(70)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                p.drawEllipse(QPointF(x + 5, y + 8), 4.5, 4.5)
                p.setPen(QColor(c["texto_suave"] if oculto else c["texto"]))
                texto = f"{e}  {formatear(serie.valores[i])}"
                p.drawText(QRectF(x + 14, y, area.right() - x - 14, 18), int(Qt.AlignmentFlag.AlignVCenter),
                           fm.elidedText(texto, Qt.TextElideMode.ElideRight, int(area.right() - x - 14)))
                self._leyenda_zonas.append((QRectF(x - 2, y, area.right() - x, 18), "cat", i))
                y += 20

    # ---- tooltip
    def _lineas_tooltip(self) -> list[str]:
        d, i = self._datos, self._hover
        if i is None or i >= len(d.etiquetas) or d.vacio:
            return []
        if self._tipo in ("circular", "anillo"):
            serie = d.series[0]
            total = sum(v for k, v in enumerate(serie.valores) if v > 0 and k not in self._ocultas_cat)
            pct = f" · {i18n.decimal(serie.valores[i] / total * 100)}%" if total > 0 and serie.valores[i] > 0 else ""
            return [d.etiquetas[i], f"{formatear(serie.valores[i])}{pct}"]
        unidad = d.unidad if d.unidad == "%" else ""
        lineas = [d.etiquetas[i]]
        for s, serie in enumerate(d.series):
            if s in self._ocultas:
                continue
            etiqueta = f"{serie.nombre}: " if len(d.series) > 1 or d.unidad not in ("",) else f"{serie.nombre}: "
            lineas.append(f"{etiqueta}{formatear(serie.valores[i], unidad)}")
        return lineas

    def _tooltip(self, p: QPainter, c: dict) -> None:
        lineas = self._lineas_tooltip()
        if lineas and self._hover is not None:
            self._tip_prev = lineas
        elif self._dim > 0.02 and self._tip_prev:
            lineas = self._tip_prev              # sigue unos instantes mientras se desvanece
        else:
            return
        p.setOpacity(max(0.0, min(1.0, self._dim * 1.6)))     # aparece y se va con un fundido, sin saltos
        fuente = QFont(self.font())
        fuente.setPixelSize(12)
        p.setFont(fuente)
        fm = QFontMetrics(fuente)
        negrita_m = QFont(fuente)
        negrita_m.setBold(True)
        ancho = max([QFontMetrics(negrita_m).horizontalAdvance(lineas[0])] + [fm.horizontalAdvance(x) for x in lineas[1:]]) + 22
        alto = 16 * len(lineas) + 12
        x = min(max(4.0, self._pos.x() + 14), max(4.0, self.width() - ancho - 4))
        y = min(max(4.0, self._pos.y() - alto - 6), max(4.0, self.height() - alto - 4))
        caja = QRectF(x, y, ancho, alto)
        oscuro = QColor(c["fondo"]).lightness() < 128
        p.setPen(QPen(QColor("#33403B" if oscuro else "#1C2623"), 1.0))
        p.setBrush(QColor("#1B211F" if oscuro else "#0B0F0E"))
        p.drawRoundedRect(caja, 9, 9)
        for k, texto in enumerate(lineas):
            p.setPen(QColor("#FFFFFF" if k == 0 else "#D1D5DB"))
            if k == 0:
                negrita = QFont(fuente)
                negrita.setBold(True)
                p.setFont(negrita)
            else:
                p.setFont(fuente)
            p.drawText(QRectF(x + 10, y + 6 + 16 * k, ancho - 14, 16), int(Qt.AlignmentFlag.AlignVCenter), texto)
