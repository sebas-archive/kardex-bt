"""Gráfico del dashboard: un solo widget que dibuja los nueve tipos con los colores del tema.

Barras (verticales/horizontales/apiladas/comparativo), líneas, áreas, evolución temporal, circular y anillo. Incluye
tooltip al pasar el cursor, leyenda seleccionable (un clic oculta o muestra una serie o categoría), clic en una
categoría para filtrar (cuando la fuente lo permite) y animación al actualizar. Se adapta a su tamaño: en espacios
pequeños omite leyenda, etiquetas de valor y rotula menos el eje.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen)
from PyQt6.QtWidgets import QWidget

from ..dashboard_datos import Datos
from ..i18n import t
from .. import i18n
from ..tema import colores
from . import widgets

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
        self.cargando = False     # sin datos todavía porque la consulta sigue en curso (no es «Sin datos»)
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

    # ------------------------------------------------------------------ API
    def poner(self, datos: Datos, tipo: str, leyenda: bool = True, etiquetas: bool = True, drill: bool = False,
              animar: bool = True) -> None:
        firma = (tuple(datos.etiquetas), tuple((s.nombre, tuple(s.valores)) for s in datos.series), tipo)
        cambio = firma != self._firma
        self._firma = firma
        self._datos, self._tipo, self._leyenda, self._etiquetas, self._drill = datos, tipo, leyenda, etiquetas, drill
        self._ocultas = {i for i in self._ocultas if i < len(datos.series)}
        self._ocultas_cat = {i for i in self._ocultas_cat if i < len(datos.etiquetas)}
        if cambio and animar:
            widgets._detener(self._anim)
            self._prog = 0.0
            self._anim = widgets.animar(self, 0.0, 1.0, 650, self._avance)
        else:
            self._prog = 1.0
        self.update()

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
        if self._hover != previo or self._hover is not None:
            self.update()

    def leaveEvent(self, evento) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        pos = evento.position()
        for zona, clase, i in self._leyenda_zonas:
            if zona.contains(pos):
                alterna = self._ocultas if clase == "serie" else self._ocultas_cat
                alterna.symmetric_difference_update({i})
                if clase == "serie" and len(self._ocultas) >= len(self._datos.series):
                    self._ocultas.clear()      # nunca se queda sin ninguna serie visible
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
        c = colores()
        self._leyenda_zonas = []
        self._geom = {}
        d = self._datos
        if d.vacio:
            p.setPen(QColor(c["texto_suave"]))
            vacio = t("Sin datos en este período") if d.temporal else t("Sin datos")
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       t("Cargando…") if self.cargando else vacio)
            p.end()
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
        p.end()

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
            sumas = [sum(max(d.series[s].valores[i], 0) for s in visibles) for i in range(len(d.etiquetas))]
            vmax, vmin = max(sumas + [0.0]), 0.0
        else:
            todos = [d.series[s].valores[i] for s in visibles for i in range(len(d.etiquetas))]
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
        if self._hover is not None and 0 <= self._hover < n:
            banda = QColor(c["texto"])
            banda.setAlpha(14)
            p.fillRect(QRectF(plot.left() + slot * self._hover, plot.top(), slot, plot.height()), banda)
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
            for j, s in enumerate(visibles):
                v = d.series[s].valores[i]
                col = self._color_barra(s, v, colores_s)
                if i == self._hover:
                    col = col.lighter(112)
                p.setBrush(col)
                if apilado:
                    if v <= 0:
                        continue
                    ya, yb = ypos(acumulado * prog), ypos((acumulado + v) * prog)
                    acumulado += v
                    x = centro - ancho / 2
                    rect = QRectF(x, yb, ancho, max(0.0, ya - yb))
                else:
                    x = centro - ancho / 2 + sub * j
                    yv = ypos(v * prog)
                    rect = QRectF(x + (1 if k > 1 else 0), min(y0, yv), max(1.0, sub - (2 if k > 1 else 0)), abs(y0 - yv))
                if rect.height() < 0.5:
                    continue
                camino = QPainterPath()
                camino.addRoundedRect(rect, min(4.0, rect.width() / 2), min(4.0, rect.width() / 2))
                p.drawPath(camino)
                if self._etiquetas and not apilado and k == 1 and not pequeno and slot >= 30 and prog > 0.98:
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
        for orden, s in enumerate(visibles):
            col = QColor(colores_s[s % len(colores_s)])
            puntos = [QPointF(plot.left() + slot * i + slot / 2, ypos(d.series[s].valores[i])) for i in range(n)]
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
                alto.setAlpha(110 if len(visibles) == 1 else 70)
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
                    radio = 4.5 if i == self._hover else 3.0
                    p.setBrush(col if i == self._hover else QColor(c["tarjeta"]))
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
            if i == self._hover:
                banda = QColor(c["texto"])
                banda.setAlpha(14)
                p.fillRect(QRectF(area.left(), plot.top() + slot * i, area.width(), slot), banda)
            p.setPen(QColor(c["texto"]))
            p.drawText(QRectF(area.left(), centro - 8, izq - 8, 16),
                       int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       fm.elidedText(d.etiquetas[i], Qt.TextElideMode.ElideRight, int(izq - 10)))
            for j, s in enumerate(visibles):
                v = d.series[s].valores[i]
                col = self._color_barra(s, v, colores_s)
                if i == self._hover:
                    col = col.lighter(112)
                xv = xpos(v * self._prog)
                rect = QRectF(min(x0, xv), centro - grosor / 2 + sub * j, max(1.0, abs(xv - x0)), max(2.0, sub - (1 if k > 1 else 0)))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col)
                camino = QPainterPath()
                camino.addRoundedRect(rect, 4, 4)
                p.drawPath(camino)
                if self._etiquetas and k == 1 and self._prog > 0.98 and area.width() >= PEQUENO - 60:
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
        indices = [i for i, v in enumerate(serie.valores) if v > 0 and i not in self._ocultas_cat]
        total = sum(serie.valores[i] for i in indices)
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
                barrido = serie.valores[i] / total * 360.0
                self._geom["tramos"].append((i, angulo, angulo + barrido))
                col = QColor(colores_s[i % len(colores_s)])
                if i == self._hover:
                    col = col.lighter(112)
                radio = r_ext + (3 if i == self._hover else 0)
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
                               int(Qt.AlignmentFlag.AlignCenter), f"{serie.valores[i] / total * 100:.0f}%")
                angulo += barrido
            if r_int > 0 and r_int > 26:
                p.setPen(QColor(c["texto"]))
                grande = QFont(fuente)
                grande.setPixelSize(18)
                grande.setBold(True)
                p.setFont(grande)
                p.drawText(QRectF(centro.x() - r_int, centro.y() - 18, r_int * 2, 22), int(Qt.AlignmentFlag.AlignCenter),
                           formatear(total))
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
        if not lineas or self._hover is None:
            return
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
