"""Piezas visuales de la pantalla Sincronización (centro de control Bluetooth).

Todo se pinta con ``QPainter`` leyendo ``tema.colores()`` en cada ``paintEvent``: cambiar de tema claro a oscuro
no exige reconstruir nada. Las animaciones pasan por ``widgets.animar`` o por ciclos que solo corren mientras el
widget es visible, y se apagan con ``APP_SIN_ANIMACIONES=1`` (``widgets.ANIMAR``). Regla heredada de ``widgets``:
el **dato** (``valor()``, ``texto()``, ``estado()``) queda disponible al instante; solo el dibujo se anima.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt6.QtWidgets import QPushButton, QStyledItemDelegate, QTableWidget, QVBoxLayout, QLabel, QWidget

from .. import tema
from . import motion, widgets

AZUL = QColor("#3B5BDB")          # el azul de Bluetooth que ya usan el indicador y el diagrama anteriores
TONOS = {"ok": "acento", "pausa": "texto_suave", "aviso": "aviso", "error": "error"}


# ------------------------------------------------------------------ utilidades de color y ciclos
def col(clave: str) -> QColor:
    return QColor(tema.colores()[clave])


def con_alfa(color: QColor, alfa: float) -> QColor:
    c = QColor(color)
    c.setAlphaF(max(0.0, min(1.0, alfa)))
    return c


def mezclar(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(round(a.red() + (b.red() - a.red()) * t), round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t), round(a.alpha() + (b.alpha() - a.alpha()) * t))


def color_tono(tono: str) -> QColor:
    return col(TONOS.get(tono, "texto_suave"))


def ciclo(dueno: QWidget, ms: int, paso) -> QVariantAnimation:
    """Animación 0→1 que se repite sin fin; quien la crea decide cuándo arrancarla."""
    anim = QVariantAnimation(dueno)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setDuration(ms)
    anim.setLoopCount(-1)
    anim.valueChanged.connect(lambda v: paso(float(v)))
    return anim


def _fuente(base: QFont, px: int, peso: QFont.Weight = QFont.Weight.Normal) -> QFont:
    f = QFont(base)
    f.setPixelSize(px)
    f.setWeight(peso)
    return f


def _marcha(anim: QVariantAnimation, debe: bool) -> None:
    if debe and widgets.ANIMAR:
        if anim.state() != QVariantAnimation.State.Running:
            anim.start()
    else:
        anim.stop()


# ------------------------------------------------------------------ píldora de estado
class Pildora(QWidget):
    """Punto de color semántico + texto. En ``ok`` y ``aviso`` el punto «respira»."""

    def __init__(self, texto: str = "", tono: str = "pausa", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._texto, self._tono, self._previo, self._mez, self._fase = texto, tono, tono, 1.0, 0.0
        self._anim_color: QVariantAnimation | None = None
        self._respira = ciclo(self, 2400, self._latir)
        self.setFixedHeight(30)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hover = 0.0
        self._anim_hover: QVariantAnimation | None = None

    def tono(self) -> str:
        return self._tono

    def texto(self) -> str:
        return self._texto

    def set_estado(self, tono: str, texto: str) -> None:
        cambio = tono != self._tono
        self._texto = texto
        if cambio:
            self._previo, self._tono = self._tono, tono
            widgets._detener(self._anim_color)
            self._mez = 0.0
            self._anim_color = widgets.animar(self, 0.0, 1.0, 250, self._paso_color)
        self._arrancar()
        self.updateGeometry()
        self.update()

    def _paso_color(self, v: float) -> None:
        self._mez = v
        self.update()

    def _latir(self, v: float) -> None:
        self._fase = v
        self.update()

    def _arrancar(self) -> None:
        _marcha(self._respira, self._tono in ("ok", "aviso") and self.isVisible())

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._arrancar()

    def hideEvent(self, e) -> None:
        self._respira.stop()
        super().hideEvent(e)

    def enterEvent(self, e) -> None:
        self._mover_hover(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._mover_hover(0.0)
        super().leaveEvent(e)

    def _mover_hover(self, destino: float) -> None:
        widgets._detener(self._anim_hover)
        self._anim_hover = widgets.animar(self, self._hover, destino, 150, self._paso_hover)

    def _paso_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def sizeHint(self):
        fm = QFontMetricsF(_fuente(self.font(), 12, QFont.Weight.DemiBold))
        from PyQt6.QtCore import QSize
        return QSize(int(fm.horizontalAdvance(self._texto)) + 14 + 12 + 10 + 4, 30)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = mezclar(color_tono(self._previo), color_tono(self._tono), self._mez)
        caja = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(mezclar(col("tarjeta_alt"), color, 0.06 + 0.06 * self._hover))
        p.setPen(QPen(mezclar(col("borde"), color, 0.25 + 0.2 * self._hover), 1))
        p.drawRoundedRect(caja, caja.height() / 2, caja.height() / 2)
        centro = QPointF(caja.left() + 15, caja.center().y())
        if self._tono in ("ok", "aviso") and widgets.ANIMAR:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alfa(color, 0.35 * (1 - self._fase)))
            r = 4 + 5 * self._fase
            p.drawEllipse(centro, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(centro, 4, 4)
        p.setFont(_fuente(self.font(), 12, QFont.Weight.DemiBold))
        p.setPen(col("texto"))
        p.drawText(QRectF(caja.left() + 28, caja.top(), caja.width() - 34, caja.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._texto)


# ------------------------------------------------------------------ botón Actualizar
class BotonActualizar(QPushButton):
    """«Actualizar» con icono de refrescar que gira mientras trabaja (y queda deshabilitado)."""

    def __init__(self, texto: str = "Actualizar", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setObjectName("accionSync")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._angulo, self._girando = 0.0, False
        self._giro = ciclo(self, 900, self._girar)
        self._poner_icono()

    def girando(self) -> bool:
        return self._girando

    def iniciar(self) -> None:
        self._girando = True
        self.setEnabled(False)
        _marcha(self._giro, True)

    def detener(self) -> None:
        self._girando = False
        self._giro.stop()
        self._angulo = 0.0
        self.setEnabled(True)
        self._poner_icono()

    def _girar(self, v: float) -> None:
        self._angulo = 360.0 * v
        self._poner_icono()

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() in (QEvent.Type.PaletteChange, QEvent.Type.EnabledChange):
            self._poner_icono()

    def _poner_icono(self) -> None:
        dpr = 2
        px = QPixmap(16 * dpr, 16 * dpr)
        px.setDevicePixelRatio(dpr)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = col("texto") if self.isEnabled() or self._girando else col("texto_suave")
        p.translate(8, 8)
        p.rotate(self._angulo)
        r = 5.6
        p.setPen(QPen(color, 1.7, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), 70 * 16, 270 * 16)
        fin = math.radians(340)
        punta = QPointF(r * math.cos(fin), -r * math.sin(fin))
        t = QPointF(-math.sin(fin), -math.cos(fin))
        n = QPointF(-t.y(), t.x())
        flecha = QPainterPath()
        flecha.moveTo(punta + t * 3.6)
        flecha.lineTo(punta + n * 3.2)
        flecha.lineTo(punta - n * 3.2)
        flecha.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(flecha)
        p.end()
        self.setIcon(QIcon(px))


# ------------------------------------------------------------------ icono grande de Bluetooth
def _runa(centro: QPointF, s: float) -> QPainterPath:
    trazo = QPainterPath()
    trazo.moveTo(centro.x() - s * 0.6, centro.y() - s * 0.55)
    trazo.lineTo(centro.x() + s * 0.55, centro.y() + s * 0.55)
    trazo.lineTo(centro.x(), centro.y() + s * 1.1)
    trazo.lineTo(centro.x(), centro.y() - s * 1.1)
    trazo.lineTo(centro.x() + s * 0.55, centro.y() - s * 0.55)
    trazo.lineTo(centro.x() - s * 0.6, centro.y() + s * 0.55)
    return trazo


class IconoBluetooth(QWidget):
    """Círculo con la runa de Bluetooth. Activo: ondas y pulso; buscando: arco que gira; en pausa: atenuado
    con insignia de pausa; error y detenido: insignia propia. Sin ondas cuando no hay actividad."""

    MODOS = ("activo", "buscando", "pausado", "error", "detenido")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modo, self._fase, self._entrada = "pausado", 0.0, 1.0
        self._anim_entrada: QVariantAnimation | None = None
        self._ciclo = ciclo(self, 2400, self._girar)
        self.setMinimumSize(176, 176)

    def modo(self) -> str:
        return self._modo

    def set_modo(self, modo: str) -> None:
        if modo not in self.MODOS:
            raise ValueError(modo)
        if modo != self._modo:
            self._modo = modo
            widgets._detener(self._anim_entrada)
            self._anim_entrada = widgets.animar(self, 0.0, 1.0, 320, self._paso_entrada,
                                                curva=widgets.QEasingCurve.Type.OutBack)
        self._arrancar()
        self.update()

    def _paso_entrada(self, v: float) -> None:
        self._entrada = v
        self.update()

    def _girar(self, v: float) -> None:
        self._fase = v
        self.update()

    def _arrancar(self) -> None:
        _marcha(self._ciclo, self._modo in ("activo", "buscando") and self.isVisible())

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._arrancar()

    def hideEvent(self, e) -> None:
        self._ciclo.stop()
        super().hideEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        radio = min(self.width(), self.height()) / 2 - 4
        nucleo = radio * 0.5 * (0.85 + 0.15 * self._entrada)
        modo = self._modo
        base = {"activo": AZUL, "buscando": AZUL, "error": col("error")}.get(modo, col("texto_suave"))
        opac = {"pausado": 0.62, "detenido": 0.45}.get(modo, 1.0)
        p.setPen(Qt.PenStyle.NoPen)
        if modo == "activo":
            for i in range(3):
                f = (self._fase + i / 3) % 1.0
                r = nucleo + (radio - nucleo) * f
                p.setBrush(con_alfa(base, 0.10 * (1 - f)))
                p.drawEllipse(c, r, r)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(con_alfa(base, 0.45 * (1 - f)), 1.6))
                p.drawEllipse(c, r, r)
                p.setPen(Qt.PenStyle.NoPen)
            nucleo *= 1 + 0.03 * math.sin(2 * math.pi * self._fase)
        elif modo == "buscando":
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = nucleo * 1.38
            p.setPen(QPen(con_alfa(base, 0.18), 3))
            p.drawEllipse(c, r, r)
            p.setPen(QPen(base, 3.4, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), int((90 - 360 * self._fase) * 16), -95 * 16)
            p.setPen(Qt.PenStyle.NoPen)
        p.setOpacity(opac)
        brillo = QRadialGradient(QPointF(c.x() - nucleo * 0.3, c.y() - nucleo * 0.4), nucleo * 1.5)
        brillo.setColorAt(0.0, mezclar(base, QColor("#FFFFFF"), 0.22))
        brillo.setColorAt(1.0, base)
        p.setBrush(brillo)
        p.drawEllipse(c, nucleo, nucleo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#FFFFFF"), max(3.0, nucleo * 0.12), cap=Qt.PenCapStyle.RoundCap,
                      join=Qt.PenJoinStyle.RoundJoin))
        p.drawPath(_runa(c, nucleo * 0.42))
        p.setOpacity(1.0)
        self._insignia(p, QPointF(c.x() + nucleo * 0.74, c.y() + nucleo * 0.74), nucleo * 0.3)

    def _insignia(self, p: QPainter, c: QPointF, r: float) -> None:
        modo = self._modo
        if modo == "buscando":
            return
        color = {"activo": col("acento"), "error": col("error")}.get(modo, col("texto_suave"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("tarjeta"))
        p.drawEllipse(c, r + 3, r + 3)
        if modo == "activo" and widgets.ANIMAR:
            p.setBrush(con_alfa(color, 0.35 * (1 - self._fase)))
            p.drawEllipse(c, r + 5 * self._fase, r + 5 * self._fase)
        p.setBrush(color)
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor("#FFFFFF"), max(2.0, r * 0.2), cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        if modo == "activo":
            v = QPainterPath()
            v.moveTo(c.x() - r * 0.45, c.y())
            v.lineTo(c.x() - r * 0.1, c.y() + r * 0.38)
            v.lineTo(c.x() + r * 0.5, c.y() - r * 0.35)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(v)
        elif modo == "pausado":
            p.drawLine(QPointF(c.x() - r * 0.28, c.y() - r * 0.4), QPointF(c.x() - r * 0.28, c.y() + r * 0.4))
            p.drawLine(QPointF(c.x() + r * 0.28, c.y() - r * 0.4), QPointF(c.x() + r * 0.28, c.y() + r * 0.4))
        elif modo == "error":
            p.drawLine(QPointF(c.x(), c.y() - r * 0.45), QPointF(c.x(), c.y() + r * 0.12))
            p.drawPoint(QPointF(c.x(), c.y() + r * 0.45))
        else:  # detenido
            p.drawLine(QPointF(c.x() - r * 0.35, c.y() - r * 0.35), QPointF(c.x() + r * 0.35, c.y() + r * 0.35))
            p.drawLine(QPointF(c.x() + r * 0.35, c.y() - r * 0.35), QPointF(c.x() - r * 0.35, c.y() + r * 0.35))


# ------------------------------------------------------------------ contador tipo odómetro
def formato_miles(n: int) -> str:
    return f"{int(n):,}".replace(",", ".")


class Odometro(QWidget):
    """Cifra grande cuyos dígitos «ruedan» al cambiar. ``valor()``/``texto()`` son el dato final al instante."""

    def __init__(self, valor: int = 0, tamano: int = 34, clave_color: str = "texto_fuerte",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._valor, self._txt, self._prev, self._p, self._dir = int(valor), formato_miles(valor), formato_miles(valor), 1.0, 1
        self._tamano, self._clave = tamano, clave_color
        self._anim: QVariantAnimation | None = None
        from PyQt6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def valor(self) -> int:
        return self._valor

    def texto(self) -> str:
        return self._txt

    def set_clave_color(self, clave: str) -> None:
        self._clave = clave
        self.update()

    def set_valor(self, valor: int) -> None:
        valor = int(valor)
        if valor == self._valor:
            return
        self._dir = 1 if valor > self._valor else -1
        self._prev = self._txt   # lo que se veía queda como «anterior»
        self._valor, self._txt = valor, formato_miles(valor)
        widgets._detener(self._anim)
        self._p = 0.0
        self._anim = widgets.animar(self, 0.0, 1.0, 450, self._paso)
        self.updateGeometry()

    def _paso(self, v: float) -> None:
        self._p = v
        self.update()

    def _fm(self) -> QFontMetricsF:
        return QFontMetricsF(_fuente(self.font(), self._tamano, QFont.Weight.DemiBold))

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        fm = self._fm()
        return QSize(int(fm.horizontalAdvance(self._txt)) + 4, int(fm.height()) + 4)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(_fuente(self.font(), self._tamano, QFont.Weight.DemiBold))
        fm = self._fm()
        color = col(self._clave)
        n = max(len(self._txt), len(self._prev))
        nuevo, viejo = self._txt.rjust(n), self._prev.rjust(n)
        alto = float(self.height())
        base = (alto + fm.ascent() - fm.descent()) / 2
        x = 0.0
        for a, b in zip(viejo, nuevo):
            ancho = max(fm.horizontalAdvance(a), fm.horizontalAdvance(b))
            if a == b or self._p >= 1.0:
                p.setPen(color)
                p.drawText(QPointF(x, base), b)
            else:
                p.save()
                p.setClipRect(QRectF(x, 0, ancho + 1, alto))
                p.setPen(con_alfa(color, 1 - self._p))
                p.drawText(QPointF(x, base - self._dir * self._p * alto), a)
                p.setPen(con_alfa(color, self._p))
                p.drawText(QPointF(x, base + self._dir * (1 - self._p) * alto), b)
                p.restore()
            x += ancho


# ------------------------------------------------------------------ flujo de datos animado
NODOS = ("Android", "Bluetooth", "PC servidor", "Oracle")


def _icono_android(p: QPainter, c: QPointF, color: QColor) -> None:
    p.setPen(QPen(color, 2, cap=Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(c.x() - 8, c.y() - 13, 16, 26), 4, 4)
    p.drawLine(QPointF(c.x() - 2.5, c.y() - 9.5), QPointF(c.x() + 2.5, c.y() - 9.5))
    p.drawPoint(QPointF(c.x(), c.y() + 9.5))


def _icono_pc(p: QPainter, c: QPointF, color: QColor) -> None:
    p.setPen(QPen(color, 2, cap=Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(c.x() - 13, c.y() - 11, 26, 17), 3, 3)
    p.drawLine(QPointF(c.x(), c.y() + 6), QPointF(c.x(), c.y() + 11))
    p.drawLine(QPointF(c.x() - 6, c.y() + 11.5), QPointF(c.x() + 6, c.y() + 11.5))


def _icono_oracle(p: QPainter, c: QPointF, color: QColor) -> None:
    p.setPen(QPen(color, 2, cap=Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    ancho, alto = 22.0, 7.0
    for dy in (-9.0, 0.0):
        p.drawLine(QPointF(c.x() - ancho / 2, c.y() + dy), QPointF(c.x() - ancho / 2, c.y() + dy + 9))
        p.drawLine(QPointF(c.x() + ancho / 2, c.y() + dy), QPointF(c.x() + ancho / 2, c.y() + dy + 9))
    p.drawEllipse(QRectF(c.x() - ancho / 2, c.y() - 9 - alto / 2, ancho, alto))
    p.drawArc(QRectF(c.x() - ancho / 2, c.y() - alto / 2, ancho, alto), 180 * 16, 180 * 16)
    p.drawArc(QRectF(c.x() - ancho / 2, c.y() + 9 - alto / 2, ancho, alto), 180 * 16, 180 * 16)


def _icono_bt(p: QPainter, c: QPointF, color: QColor) -> None:
    p.setPen(QPen(color, 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(_runa(c, 11))


class FlujoDatos(QWidget):
    """Android → Bluetooth → PC servidor → Oracle. Cada enlace es ``off``, ``enlazado`` o ``activo``; solo los
    activos llevan paquetes luminosos (a velocidad ``velocidad``). Un nodo en error vibra y se pinta en rojo."""

    elegido = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nodos = [{"tono": "pausa", "estado": "", "detalle": ""} for _ in NODOS]
        self._enlaces = ["off", "off", "off"]
        self._etiquetas = ["", "", ""]
        self._velocidad, self._pos, self._error, self._alerta = 1.0, 0.0, None, 1.0
        self._hover: int | None = None
        self._anim_alerta: QVariantAnimation | None = None
        self._reloj = QTimer(self)
        self._reloj.setInterval(30)
        self._reloj.timeout.connect(self._avanzar)
        self.setMinimumHeight(196)
        self.setMouseTracking(True)

    # --- dato
    def enlaces(self) -> list[str]:
        return list(self._enlaces)

    def nodos(self) -> list[dict]:
        return [dict(n) for n in self._nodos]

    def error(self) -> int | None:
        return self._error

    def velocidad(self) -> float:
        return self._velocidad

    def set_modelo(self, nodos: list[dict], enlaces: list[str], etiquetas: list[str],
                   velocidad: float = 1.0, error: int | None = None) -> None:
        nuevo_error = error is not None and error != self._error
        self._nodos, self._enlaces, self._etiquetas = [dict(n) for n in nodos], list(enlaces), list(etiquetas)
        self._velocidad, self._error = velocidad, error
        if nuevo_error:   # alerta breve: el nodo vibra una vez
            widgets._detener(self._anim_alerta)
            self._alerta = 0.0
            self._anim_alerta = widgets.animar(self, 0.0, 1.0, 460, self._paso_alerta)
        self._arrancar()
        self.update()

    def _paso_alerta(self, v: float) -> None:
        self._alerta = v
        self.update()

    def _arrancar(self) -> None:
        if widgets.ANIMAR and self.isVisible() and "activo" in self._enlaces:
            if not self._reloj.isActive():
                self._reloj.start()
        else:
            self._reloj.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._arrancar()

    def hideEvent(self, e) -> None:
        self._reloj.stop()
        super().hideEvent(e)

    def _avanzar(self) -> None:
        self._pos = (self._pos + 0.030 / 1.8 * self._velocidad) % 1.0
        self.update()

    # --- geometría
    def _tarjeta(self, i: int) -> QRectF:
        w = self.width() / 4
        ancho = min(176.0, w - 44)
        return QRectF(w * (i + 0.5) - ancho / 2, 6, ancho, self.height() - 12)

    def _centro_icono(self, i: int) -> QPointF:
        t = self._tarjeta(i)
        return QPointF(t.center().x(), t.top() + 46)

    def _nodo_en(self, punto) -> int | None:
        for i in range(4):
            if self._tarjeta(i).contains(punto):
                return i
        return None

    def mouseMoveEvent(self, e) -> None:
        i = self._nodo_en(e.position())
        if i != self._hover:
            self._hover = i
            self.setToolTip("" if i is None else
                            f"{NODOS[i]}: {self._nodos[i]['estado']}" + (f"\n{self._nodos[i]['detalle']}" if self._nodos[i]['detalle'] else ""))
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        i = self._nodo_en(e.position())
        if i is not None and e.button() == Qt.MouseButton.LeftButton:
            self.elegido.emit(i)
        super().mousePressEvent(e)

    # --- dibujo
    def _color_nodo(self, i: int) -> QColor:
        n = self._nodos[i]
        if i == 1 and n["tono"] == "ok":
            return AZUL
        return color_tono(n["tono"])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i in range(3):
            self._enlace(p, i)
        for i in range(4):
            self._nodo(p, i)

    def _enlace(self, p: QPainter, i: int) -> None:
        a, b = self._centro_icono(i), self._centro_icono(i + 1)
        x1, x2, y = a.x() + 34, b.x() - 34, a.y()
        estado = self._enlaces[i]
        azul = i < 2
        color = AZUL if azul else col("acento")
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col("borde_fuerte"), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x1, y), QPointF(x2, y))
        if estado == "enlazado":
            p.setPen(QPen(con_alfa(color, 0.5), 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y), QPointF(x2, y))
        elif estado == "activo":
            g = QLinearGradient(x1, y, x2, y)
            g.setColorAt(0.0, con_alfa(color, 0.35))
            g.setColorAt(0.5, con_alfa(color, 0.9))
            g.setColorAt(1.0, con_alfa(color, 0.35))
            p.setPen(QPen(g, 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y), QPointF(x2, y))
            if widgets.ANIMAR:
                for k in range(3):
                    f = (self._pos + k / 3) % 1.0
                    x = x1 + (x2 - x1) * f
                    vis = math.sin(math.pi * f)
                    halo = QRadialGradient(QPointF(x, y), 11)
                    halo.setColorAt(0.0, con_alfa(color, 0.55 * vis))
                    halo.setColorAt(1.0, con_alfa(color, 0.0))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(halo)
                    p.drawEllipse(QPointF(x, y), 11, 11)
                    p.setBrush(mezclar(color, QColor("#FFFFFF"), 0.55 * vis + 0.1))
                    p.drawRoundedRect(QRectF(x - 4.5, y - 2.5, 9, 5), 2.5, 2.5)
        texto = self._etiquetas[i]
        if texto:
            p.setFont(_fuente(self.font(), 10, QFont.Weight.DemiBold))
            fm = QFontMetricsF(p.font())
            w = min(fm.horizontalAdvance(texto) + 16, x2 - x1)
            caja = QRectF((x1 + x2) / 2 - w / 2, y - 26, w, 18)
            p.setPen(QPen(col("borde"), 1))
            p.setBrush(col("tarjeta"))
            p.drawRoundedRect(caja, 9, 9)
            p.setPen(col("texto_tenue"))
            p.drawText(caja, Qt.AlignmentFlag.AlignCenter, fm.elidedText(texto, Qt.TextElideMode.ElideRight, w - 8))

    def _nodo(self, p: QPainter, i: int) -> None:
        n = self._nodos[i]
        caja = self._tarjeta(i)
        error = self._error == i
        if error and self._alerta < 1.0:
            caja = caja.translated(math.sin(self._alerta * math.pi * 7) * 5 * (1 - self._alerta), 0)
        color = self._color_nodo(i)
        resaltado = self._hover == i
        p.setBrush(mezclar(col("tarjeta_alt"), color, 0.07 if error else 0.0))
        p.setPen(QPen(col("error") if error else (col("borde_fuerte") if resaltado else col("borde")), 1.5 if error else 1))
        p.drawRoundedRect(caja, 18, 18)
        c = QPointF(caja.center().x(), caja.top() + 46)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alfa(color, 0.16))
        p.drawEllipse(c, 27, 27)
        {0: _icono_android, 1: _icono_bt, 2: _icono_pc, 3: _icono_oracle}[i](p, c, color)
        p.setFont(_fuente(self.font(), 14, QFont.Weight.DemiBold))
        p.setPen(col("texto_fuerte"))
        p.drawText(QRectF(caja.left(), c.y() + 36, caja.width(), 20), Qt.AlignmentFlag.AlignCenter, NODOS[i])
        # estado con su punto
        p.setFont(_fuente(self.font(), 12, QFont.Weight.DemiBold))
        fm = QFontMetricsF(p.font())
        txt = fm.elidedText(n["estado"], Qt.TextElideMode.ElideRight, caja.width() - 36)
        w = fm.horizontalAdvance(txt) + 14
        x0 = caja.center().x() - w / 2
        y = c.y() + 66
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(x0 + 3.5, y), 3.5, 3.5)
        p.setPen(col("texto"))
        p.drawText(QRectF(x0 + 14, y - 10, w, 20), Qt.AlignmentFlag.AlignVCenter, txt)
        if n["detalle"]:
            p.setFont(_fuente(self.font(), 11))
            fm = QFontMetricsF(p.font())
            p.setPen(col("texto_tenue"))
            p.drawText(QRectF(caja.left() + 8, y + 12, caja.width() - 16, 18), Qt.AlignmentFlag.AlignCenter,
                       fm.elidedText(n["detalle"], Qt.TextElideMode.ElideRight, caja.width() - 16))


# ------------------------------------------------------------------ etapas de la sincronización
ETAPAS = ("Esperando dispositivo", "Dispositivo conectado", "Recibiendo lecturas", "Procesando información",
          "Sincronización completada")


class Etapas(QWidget):
    """Cinco etapas. ``set_estado(actual, hechas, error)``: las primeras ``hechas`` llevan check, ``actual`` es la
    que está en curso y ``error`` (si lo hay) se pinta en rojo y vibra una vez."""

    def __init__(self, nombres: list[str] | tuple[str, ...] = ETAPAS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nombres = list(nombres)
        self._actual: int | None = None
        self._hechas, self._error = 0, None
        self._lleno, self._fase, self._alerta = 0.0, 0.0, 1.0
        self._anim_lleno: QVariantAnimation | None = None
        self._anim_alerta: QVariantAnimation | None = None
        self._halo = ciclo(self, 1500, self._latir)
        self.setMinimumHeight(84)

    def estado(self) -> tuple[int | None, int, int | None]:
        return self._actual, self._hechas, self._error

    def nombres(self) -> list[str]:
        return list(self._nombres)

    def set_estado(self, actual: int | None, hechas: int, error: int | None = None) -> None:
        nuevo_error = error is not None and error != self._error
        self._actual, self._hechas, self._error = actual, hechas, error
        destino = float(min(len(self._nombres) - 1, error if error is not None else hechas))
        widgets._detener(self._anim_lleno)
        self._anim_lleno = widgets.animar(self, self._lleno, destino, 350, self._paso_lleno)
        if nuevo_error:
            widgets._detener(self._anim_alerta)
            self._alerta = 0.0
            self._anim_alerta = widgets.animar(self, 0.0, 1.0, 430, self._paso_alerta)
        _marcha(self._halo, actual is not None and self.isVisible())
        self.update()

    def _paso_lleno(self, v: float) -> None:
        self._lleno = v
        self.update()

    def _paso_alerta(self, v: float) -> None:
        self._alerta = v
        self.update()

    def _latir(self, v: float) -> None:
        self._fase = v
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        _marcha(self._halo, self._actual is not None)

    def hideEvent(self, e) -> None:
        self._halo.stop()
        super().hideEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._nombres)
        paso = self.width() / n
        cy, r = 22.0, 13.0
        xs = [paso * (i + 0.5) for i in range(n)]
        p.setPen(QPen(col("borde_fuerte"), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(xs[0], cy), QPointF(xs[-1], cy))
        lleno_x = xs[0] + (xs[-1] - xs[0]) * (self._lleno / max(1, n - 1))
        if lleno_x > xs[0]:
            color_linea = col("error") if self._error is not None else col("acento")
            p.setPen(QPen(color_linea, 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(xs[0], cy), QPointF(lleno_x, cy))
        for i, nombre in enumerate(self._nombres):
            hecho = i < self._hechas
            activo = i == self._actual and not hecho
            error = i == self._error
            cx = xs[i]
            if error and self._alerta < 1.0:
                cx += math.sin(self._alerta * math.pi * 7) * 5 * (1 - self._alerta)
            radio = r * (1.12 if activo else 1.0)
            if activo and widgets.ANIMAR:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(con_alfa(AZUL, 0.32 * (1 - self._fase)))
                p.drawEllipse(QPointF(cx, cy), radio + 9 * self._fase, radio + 9 * self._fase)
            if error:
                fondo, borde = col("error"), col("error")
            elif hecho:
                fondo, borde = col("acento"), col("acento")
            elif activo:
                fondo, borde = AZUL, AZUL
            else:
                fondo, borde = col("tarjeta"), col("borde_fuerte")
            p.setBrush(fondo)
            p.setPen(QPen(borde, 2))
            p.drawEllipse(QPointF(cx, cy), radio, radio)
            blanco = QPen(QColor("#FFFFFF"), 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin)
            if error:
                p.setPen(blanco)
                p.drawLine(QPointF(cx, cy - 5), QPointF(cx, cy + 1.5))
                p.drawPoint(QPointF(cx, cy + 5))
            elif hecho:
                p.setPen(blanco)
                p.setBrush(Qt.BrushStyle.NoBrush)
                v = QPainterPath()
                v.moveTo(cx - 5, cy + 0.5)
                v.lineTo(cx - 1.5, cy + 4)
                v.lineTo(cx + 5.5, cy - 4)
                p.drawPath(v)
            elif activo:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#FFFFFF"))
                p.drawEllipse(QPointF(cx, cy), 3.6, 3.6)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(col("borde_fuerte"))
                p.drawEllipse(QPointF(cx, cy), 3, 3)
            p.setFont(_fuente(self.font(), 12, QFont.Weight.DemiBold if (activo or error) else QFont.Weight.Normal))
            p.setPen(col("error") if error else (col("texto_fuerte") if (activo or hecho) else col("texto_suave")))
            p.drawText(QRectF(xs[i] - paso / 2 + 4, cy + radio + 8, paso - 8, 34),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, nombre)


# ------------------------------------------------------------------ gráfica de actividad
def escala_agradable(maximo: float) -> float:
    """Tope del eje Y con una cifra «redonda» (4, 8, 20, 40, 100…) para que las marcas sean enteras."""
    if maximo <= 4:
        return 4.0
    exp = 10 ** math.floor(math.log10(maximo))
    for k in (1, 2, 4, 5, 8, 10):
        if k * exp >= maximo:
            return float(k * exp)
    return float(10 * exp)


class GraficaActividad(QWidget):
    """Líneas suaves con áreas degradadas (recibidas, procesadas, con error), ejes discretos, tooltip al pasar el
    mouse y transición al cambiar los datos. Sin actividad real en el rango muestra un estado vacío, no ceros."""

    SERIES = (("recibidas", "Recibidas", "acento"), ("procesadas", "Procesadas", "azul"),
              ("errores", "Con error", "error"))

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._act = None
        self._vista: dict[str, list[float]] = {k: [] for k, _, _ in self.SERIES}
        self._meta: dict[str, list[float]] = {k: [] for k, _, _ in self.SERIES}
        self._etiquetas: list[str] = []
        self._hover: int | None = None
        self._anim: QVariantAnimation | None = None
        self._titulos = {"vacio": "Sin actividad en este periodo", "ayuda": "Cuando lleguen lecturas, aparecerán aquí.",
                         "cargando": "Cargando…"}
        self._cargando = True
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def textos(self, vacio: str, ayuda: str, cargando: str) -> None:
        self._titulos = {"vacio": vacio, "ayuda": ayuda, "cargando": cargando}

    def actividad(self):
        return self._act

    def vacia(self) -> bool:
        return self._act is None or self._act.vacia

    def valores(self, serie: str) -> list[int]:
        return [int(round(v)) for v in self._meta[serie]]

    def etiquetas(self) -> list[str]:
        return list(self._etiquetas)

    def set_actividad(self, act, ahora: datetime | None = None) -> None:
        self._cargando = False
        self._act = act
        self._hover = None
        if act is None:
            self._etiquetas = []
            for k in self._meta:
                self._meta[k] = []
        else:
            ahora = ahora or datetime.now()
            n = len(act.recibidas)
            formato = "%H:%M" if act.paso_min < 1440 else "%d/%m"
            self._etiquetas = [(ahora - timedelta(minutes=act.paso_min * (n - 1 - i))).strftime(formato)
                               for i in range(n)]
            for k in self._meta:
                self._meta[k] = [float(v) for v in getattr(act, k)]
        inicio = {k: (list(self._vista[k]) if len(self._vista[k]) == len(self._meta[k]) else [0.0] * len(self._meta[k]))
                  for k in self._meta}
        widgets._detener(self._anim)

        def paso(v: float) -> None:
            for k in self._meta:
                self._vista[k] = [a + (b - a) * v for a, b in zip(inicio[k], self._meta[k])]
            self.update()

        self._anim = widgets.animar(self, 0.0, 1.0, 450, paso)

    # --- ratón
    def _plot(self) -> QRectF:
        return QRectF(44, 34, max(10, self.width() - 44 - 16), max(10, self.height() - 34 - 28))

    def mouseMoveEvent(self, e) -> None:
        n = len(self._etiquetas)
        if n and not self.vacia():
            plot = self._plot()
            if plot.adjusted(-8, -8, 8, 8).contains(e.position()):
                f = (e.position().x() - plot.left()) / plot.width() if plot.width() else 0
                i = max(0, min(n - 1, round(f * (n - 1)))) if n > 1 else 0
            else:
                i = None
            if i != self._hover:
                self._hover = i
                self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def _color_serie(self, clave: str) -> QColor:
        return AZUL if clave == "azul" else col(clave)

    def _puntos(self, serie: str, plot: QRectF, tope: float) -> list[QPointF]:
        v = self._vista[serie]
        n = len(v)
        if n == 0:
            return []
        return [QPointF(plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2),
                        plot.bottom() - plot.height() * min(1.0, val / tope)) for i, val in enumerate(v)]

    @staticmethod
    def _suave(pts: list[QPointF], plot: QRectF) -> QPainterPath:
        ruta = QPainterPath(pts[0])
        for i in range(len(pts) - 1):
            p0, p1, p2, p3 = pts[max(0, i - 1)], pts[i], pts[i + 1], pts[min(len(pts) - 1, i + 2)]
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, p1.y() + (p2.y() - p0.y()) / 6)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, p2.y() - (p3.y() - p1.y()) / 6)
            c1.setY(min(plot.bottom(), max(plot.top(), c1.y())))
            c2.setY(min(plot.bottom(), max(plot.top(), c2.y())))
            ruta.cubicTo(c1, c2, p2)
        return ruta

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        if self.vacia():
            self._pintar_vacio(p)
            return
        tope = escala_agradable(max((max(v) for v in self._vista.values() if v), default=1.0))
        p.setFont(_fuente(self.font(), 11))
        for k in range(3):   # rejilla discreta: 0, mitad y tope
            y = plot.bottom() - plot.height() * k / 2
            p.setPen(QPen(col("grid"), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(col("texto_suave"))
            p.drawText(QRectF(0, y - 9, plot.left() - 8, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       formato_miles(round(tope * k / 2)))
        n = len(self._etiquetas)
        marcas = sorted({0, n // 2, n - 1}) if n >= 3 else list(range(n))
        for i in marcas:
            x = plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2)
            ancho = 56
            alin = Qt.AlignmentFlag.AlignHCenter
            rx = x - ancho / 2
            if i == 0:
                rx, alin = x - 4, Qt.AlignmentFlag.AlignLeft
            elif i == n - 1:
                rx, alin = x - ancho + 4, Qt.AlignmentFlag.AlignRight
            p.setPen(col("texto_suave"))
            p.drawText(QRectF(rx, plot.bottom() + 6, ancho, 16), alin, self._etiquetas[i])
        for clave, _nombre, color_clave in self.SERIES:
            pts = self._puntos(clave, plot, tope)
            if not pts or (clave == "errores" and not any(self._vista[clave])):
                continue
            color = self._color_serie(color_clave)
            if len(pts) == 1:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawEllipse(pts[0], 4, 4)
                continue
            linea = self._suave(pts, plot)
            if clave != "errores":
                area = QPainterPath(linea)
                area.lineTo(pts[-1].x(), plot.bottom())
                area.lineTo(pts[0].x(), plot.bottom())
                area.closeSubpath()
                g = QLinearGradient(0, plot.top(), 0, plot.bottom())
                g.setColorAt(0.0, con_alfa(color, 0.28 if clave == "recibidas" else 0.16))
                g.setColorAt(1.0, con_alfa(color, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawPath(area)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            p.drawPath(linea)
        self._leyenda(p)
        if self._hover is not None:
            self._pintar_hover(p, plot, tope)

    def _leyenda(self, p: QPainter) -> None:
        x = 44.0
        p.setFont(_fuente(self.font(), 11, QFont.Weight.DemiBold))
        fm = QFontMetricsF(p.font())
        for clave, nombre, color_clave in self.SERIES:
            if clave == "errores" and (self._act is None or not any(self._act.errores)):
                continue
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._color_serie(color_clave))
            p.drawEllipse(QPointF(x + 4, 14), 4, 4)
            p.setPen(col("texto_tenue"))
            p.drawText(QPointF(x + 14, 18), nombre)
            x += 14 + fm.horizontalAdvance(nombre) + 16

    def _pintar_hover(self, p: QPainter, plot: QRectF, tope: float) -> None:
        i = self._hover
        n = len(self._etiquetas)
        x = plot.left() + (plot.width() * i / (n - 1) if n > 1 else plot.width() / 2)
        p.setPen(QPen(col("borde_fuerte"), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        lineas = []
        for clave, nombre, color_clave in self.SERIES:
            if clave == "errores" and not any(self._meta[clave]):
                continue
            v = self._meta[clave][i]
            y = plot.bottom() - plot.height() * min(1.0, self._vista[clave][i] / tope)
            color = self._color_serie(color_clave)
            p.setPen(QPen(col("tarjeta"), 2))
            p.setBrush(color)
            p.drawEllipse(QPointF(x, y), 4.5, 4.5)
            lineas.append((nombre, int(round(v)), color))
        fuente = _fuente(self.font(), 12)
        negrita = _fuente(self.font(), 12, QFont.Weight.DemiBold)
        fm = QFontMetricsF(negrita)
        ancho = max([fm.horizontalAdvance(self._etiquetas[i])] + [fm.horizontalAdvance(f"{n}   {v}") + 18 for n, v, _ in lineas]) + 24
        alto = 28 + 20 * len(lineas)
        bx = x + 14 if x + 14 + ancho < self.width() - 4 else x - 14 - ancho
        caja = QRectF(bx, plot.top() + 4, ancho, alto)
        p.setPen(QPen(col("borde_fuerte"), 1))
        p.setBrush(col("tarjeta"))
        p.drawRoundedRect(caja, 10, 10)
        p.setFont(negrita)
        p.setPen(col("texto_fuerte"))
        p.drawText(QRectF(caja.left() + 12, caja.top() + 6, caja.width() - 24, 18), Qt.AlignmentFlag.AlignVCenter, self._etiquetas[i])
        p.setFont(fuente)
        for k, (nombre, v, color) in enumerate(lineas):
            y = caja.top() + 36 + 20 * k
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(caja.left() + 16, y), 3.5, 3.5)
            p.setPen(col("texto_tenue"))
            p.drawText(QRectF(caja.left() + 26, y - 9, caja.width() - 90, 18), Qt.AlignmentFlag.AlignVCenter, nombre)
            p.setPen(col("texto_fuerte"))
            p.drawText(QRectF(caja.left() + 26, y - 9, caja.width() - 38, 18),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, formato_miles(v))

    def _pintar_vacio(self, p: QPainter) -> None:
        c = QPointF(self.width() / 2, self.height() / 2 - 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alfa(col("texto_suave"), 0.12))
        p.drawEllipse(c, 26, 26)
        p.setPen(QPen(col("texto_suave"), 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        onda = QPainterPath(QPointF(c.x() - 12, c.y() + 6))
        onda.cubicTo(QPointF(c.x() - 6, c.y() - 10), QPointF(c.x() - 2, c.y() + 10), QPointF(c.x() + 3, c.y() - 2))
        onda.cubicTo(QPointF(c.x() + 6, c.y() - 8), QPointF(c.x() + 9, c.y() - 4), QPointF(c.x() + 12, c.y() - 7))
        p.drawPath(onda)
        p.setFont(_fuente(self.font(), 14, QFont.Weight.DemiBold))
        p.setPen(col("texto_fuerte"))
        titulo = self._titulos["cargando"] if self._cargando else self._titulos["vacio"]
        p.drawText(QRectF(0, c.y() + 36, self.width(), 22), Qt.AlignmentFlag.AlignCenter, titulo)
        if not self._cargando:
            p.setFont(_fuente(self.font(), 12))
            p.setPen(col("texto_suave"))
            p.drawText(QRectF(0, c.y() + 58, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self._titulos["ayuda"])


# ------------------------------------------------------------------ tabla de lecturas con error
COL_DISPOSITIVO, COL_SECUENCIA, COL_SKU, COL_MOTIVO, COL_FECHA, COL_ESTADO, COL_ACCION = range(7)
SIN_ACCION = "—"


class _FilaDelegate(QStyledItemDelegate):
    """Fila ligera: sin rejilla, separador fino, hover suave, estado como píldora y acción como enlace."""

    def paint(self, p: QPainter, opt, idx) -> None:
        tabla: TablaErrores = self.parent()
        fila, c = idx.row(), idx.column()
        rect = QRectF(opt.rect)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(1.0 - tabla.desvanecido(fila))
        if tabla.selectionModel() and tabla.selectionModel().isRowSelected(fila, idx.parent()):
            p.fillRect(rect, con_alfa(col("acento"), 0.13))
        elif fila == tabla.fila_hover:
            p.fillRect(rect, con_alfa(col("texto"), 0.045))
        p.setPen(QPen(col("grid"), 1))
        p.drawLine(rect.bottomLeft(), rect.bottomRight())
        texto = str(idx.data(Qt.ItemDataRole.DisplayRole) or "")
        izq = rect.adjusted(14, 0, -8, 0)
        if c == COL_ESTADO and texto:
            p.setFont(_fuente(tabla.font(), 11, QFont.Weight.DemiBold))
            fm = QFontMetricsF(p.font())
            w = fm.horizontalAdvance(texto) + 26
            caja = QRectF(izq.left(), rect.center().y() - 11, min(w, izq.width()), 22)
            color = col("error")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alfa(color, 0.14))
            p.drawRoundedRect(caja, 11, 11)
            p.setBrush(color)
            p.drawEllipse(QPointF(caja.left() + 11, caja.center().y()), 3, 3)
            p.setPen(color)
            p.drawText(caja.adjusted(21, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, texto)
        else:
            fuente = _fuente(tabla.font(), 13)
            color = col("texto")
            if c == COL_SKU:
                fuente = _fuente(tabla.font(), 13, QFont.Weight.DemiBold)
                color = col("texto_fuerte")
            elif c in (COL_SECUENCIA, COL_FECHA):
                color = col("texto_tenue")
            elif c == COL_ACCION:
                if texto and texto != SIN_ACCION:
                    fuente = _fuente(tabla.font(), 13, QFont.Weight.DemiBold)
                    color = col("acento")
                else:
                    color = col("texto_suave")
            p.setFont(fuente)
            p.setPen(color)
            elidido = QFontMetricsF(fuente).elidedText(texto, Qt.TextElideMode.ElideRight, izq.width())
            p.drawText(izq, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elidido)
        p.restore()


class TablaErrores(QTableWidget):
    """``QTableWidget`` con aspecto ligero. ``desvanecer_filas`` anima la salida de las filas resueltas."""

    def __init__(self, columnas: int, parent: QWidget | None = None) -> None:
        super().__init__(0, columnas, parent)
        self.setObjectName("tablaSync")
        self.fila_hover = -1
        self._fade: dict[int, float] = {}
        self._anim: QVariantAnimation | None = None
        self.setMouseTracking(True)
        self.setShowGrid(False)
        self.setFrameShape(QTableWidget.Shape.NoFrame)
        self.setAlternatingRowColors(False)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.verticalHeader().setDefaultSectionSize(46)
        self.verticalHeader().setMinimumSectionSize(46)
        self.setItemDelegate(_FilaDelegate(self))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def desvanecido(self, fila: int) -> float:
        return self._fade.get(fila, 0.0)

    def desvanecer_filas(self, filas: list[int], al_terminar) -> None:
        """Atenúa las filas dadas (0→1) y luego llama a ``al_terminar`` (que reconstruye la tabla)."""
        if not filas or not widgets.ANIMAR:
            al_terminar()
            return
        widgets._detener(self._anim)

        def paso(v: float) -> None:
            self._fade = {f: v for f in filas}
            self.viewport().update()

        def fin() -> None:
            self._fade = {}
            al_terminar()

        self._anim = widgets.animar(self, 0.0, 1.0, 320, paso, fin)

    def mouseMoveEvent(self, e) -> None:
        fila = self.rowAt(int(e.position().y()))
        if fila != self.fila_hover:
            self.fila_hover = fila
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self.fila_hover = -1
        self.viewport().update()
        super().leaveEvent(e)


# ------------------------------------------------------------------ estado vacío
class _Marca(QWidget):
    """Círculo con check que se dibuja al aparecer."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = 1.0
        self._anim: QVariantAnimation | None = None
        self.setFixedSize(84, 84)

    def animar(self) -> None:
        widgets._detener(self._anim)
        self._anim = widgets.animar(self, 0.0, 1.0, 520, self._paso)

    def _paso(self, v: float) -> None:
        self._t = v
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        verde = col("acento")
        esc = 0.8 + 0.2 * min(1.0, self._t * 1.4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alfa(verde, 0.14))
        p.drawEllipse(c, 40 * esc, 40 * esc)
        p.setBrush(con_alfa(verde, 0.22))
        p.drawEllipse(c, 29 * esc, 29 * esc)
        trazo = QPainterPath()
        trazo.moveTo(c.x() - 11, c.y() + 1)
        trazo.lineTo(c.x() - 3, c.y() + 9)
        trazo.lineTo(c.x() + 12, c.y() - 8)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(verde, 3.6, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        visible = QPainterPath()
        t = max(0.0, (self._t - 0.25) / 0.75)
        pasos = max(2, int(24 * t))
        if t > 0:
            visible.moveTo(trazo.pointAtPercent(0))
            for k in range(1, pasos + 1):
                visible.lineTo(trazo.pointAtPercent(min(1.0, t * k / pasos)))
            p.drawPath(visible)


class EstadoVacio(QWidget):
    """«Todo está en orden»: marca con check, título y descripción."""

    def __init__(self, titulo: str, descripcion: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("vacioSync")
        self.marca = _Marca()
        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setObjectName("seccion")
        self.lbl_titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_desc = QLabel(descripcion)
        self.lbl_desc.setObjectName("subtitulo")
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.addStretch(1)
        lay.addWidget(self.marca, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)
        lay.addWidget(self.lbl_titulo)
        lay.addWidget(self.lbl_desc)
        lay.addStretch(1)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.marca.animar()


# ------------------------------------------------------------------ entrada escalonada
def entrada_escalonada(piezas: list[QWidget], retardo_ms: int = 70, duracion_ms: int = 320) -> None:
    """Fundido de entrada de las tarjetas, una tras otra. Al terminar quita el efecto (no queda ningún filtro
    gráfico encendido). Sin animaciones no hace nada."""
    if not widgets.ANIMAR:
        return
    for i, w in enumerate(piezas):
        efecto, _ = motion.opacidad(w)
        efecto.setOpacity(0.0)

        def arrancar(w=w) -> None:
            def fin() -> None:
                w.setGraphicsEffect(None)

            motion.desvanecer(w, 0.0, 1.0, duracion_ms, fin)

        QTimer.singleShot(i * retardo_ms, arrancar)
