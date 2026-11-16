"""Piezas visuales de la pantalla Sincronización (centro de control Bluetooth).

Todo se pinta con ``QPainter`` leyendo ``tema.colores()`` en cada ``paintEvent``: cambiar de tema claro a oscuro
no exige reconstruir nada. Las animaciones pasan por ``widgets.animar`` o por ciclos que solo corren mientras el
widget es visible, y se apagan con ``APP_SIN_ANIMACIONES=1`` (``widgets.ANIMAR``). Regla heredada de ``widgets``:
el **dato** (``valor()``, ``texto()``, ``estado()``) queda disponible al instante; solo el dibujo se anima.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from PyQt6.QtCore import QElapsedTimer, QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
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
from PyQt6.QtWidgets import (
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QStylePainter,
    QTableWidget,
    QVBoxLayout,
    QLabel,
    QWidget,
)
from PyQt6 import sip

from .. import i18n, tema
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


# ------------------------------------------------------------------ interpolación compartida
class Interpolador(QObject):
    """Valores con nombre (color, opacidad, escala…) que viajan juntos hacia nuevos destinos con **una sola** animación.

    ``ir_a`` parte siempre del valor actual, de modo que cambiar de destino a mitad de camino no produce saltos, y no
    crea nada si los destinos ya son los vigentes (los refrescos de datos no recrean animaciones)."""

    def __init__(self, padre: QWidget, al_cambiar, ms: int = motion.Dur.ESTADO,
                 curva: QEasingCurve.Type | QEasingCurve = QEasingCurve.Type.OutCubic) -> None:
        super().__init__(padre)
        self._padre, self._cb, self._ms, self._curva = padre, al_cambiar, ms, curva
        self._v: dict[str, float] = {}
        self._ini: dict[str, float] = {}
        self._fin: dict[str, float] = {}
        self._anim: QVariantAnimation | None = None

    def __call__(self, clave: str, defecto: float = 0.0) -> float:
        return self._v.get(clave, defecto)

    def destino(self, clave: str, defecto: float = 0.0) -> float:
        return self._fin.get(clave, defecto)

    def fijar(self, **valores: float) -> None:
        """Pone valores al instante (sin transición)."""
        widgets._detener(self._anim)
        self._v.update(valores)
        self._fin.update(valores)
        self._cb()

    def ir_a(self, ms: int | None = None, curva=None, **destinos: float) -> None:
        if all(abs(self._fin.get(k, float("inf")) - d) < 1e-6 for k, d in destinos.items()):
            return
        self._fin.update(destinos)
        self._ini = {k: self._v.get(k, self._fin[k]) for k in self._fin}
        for k in self._fin:
            self._v.setdefault(k, self._ini[k])
        widgets._detener(self._anim)
        self._anim = widgets.animar(self._padre, 0.0, 1.0, motion.dur(self._ms if ms is None else ms), self._paso,
                                    None, self._curva if curva is None else curva)

    def _paso(self, t: float) -> None:
        for k, f in self._fin.items():
            i = self._ini.get(k, f)
            self._v[k] = i + (f - i) * t
        self._cb()

    def detener(self) -> None:
        widgets._detener(self._anim)


def ruta_parcial(puntos: list[QPointF], t: float) -> QPainterPath:
    """Los primeros ``t`` (0–1) de una polilínea, para animar el «dibujo» de un check o una marca."""
    ruta = QPainterPath()
    if t <= 0 or len(puntos) < 2:
        return ruta
    largos = [math.hypot(b.x() - a.x(), b.y() - a.y()) for a, b in zip(puntos, puntos[1:])]
    resto = sum(largos) * min(1.0, t)
    ruta.moveTo(puntos[0])
    for (a, b), largo in zip(zip(puntos, puntos[1:]), largos):
        if resto >= largo:
            ruta.lineTo(b)
            resto -= largo
        else:
            f = resto / largo if largo else 0.0
            ruta.lineTo(QPointF(a.x() + (b.x() - a.x()) * f, a.y() + (b.y() - a.y()) * f))
            break
    return ruta


# ------------------------------------------------------------------ píldora de estado
class Pildora(QWidget):
    """Punto de color semántico + texto. En ``ok`` y ``aviso`` el punto «respira»; al cambiar el tono el color se
    interpola y al cambiar el texto se hace un cross-fade (con el ancho de la píldora acompañando)."""

    def __init__(self, texto: str = "", tono: str = "pausa", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._texto, self._tono, self._previo, self._mez, self._fase = texto, tono, tono, 1.0, 0.0
        self._txt_previo, self._t_txt = texto, 1.0
        self._anim_color: QVariantAnimation | None = None
        self._anim_txt: QVariantAnimation | None = None
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
        if texto != self._texto:
            self._txt_previo, self._texto = self._texto, texto
            widgets._detener(self._anim_txt)
            if self.isVisible():
                self._t_txt = 0.0
                self._anim_txt = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.ESTADO), self._paso_txt)
            else:
                self._t_txt = 1.0
        if cambio:
            self._previo, self._tono = self._tono, tono
            widgets._detener(self._anim_color)
            self._mez = 0.0
            self._anim_color = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.ESTADO), self._paso_color)
        self._arrancar()
        self.updateGeometry()
        self.update()

    def _paso_txt(self, v: float) -> None:
        self._t_txt = v
        self.updateGeometry()
        self.update()

    def _paso_color(self, v: float) -> None:
        self._mez = v
        self.update()

    def _latir(self, v: float) -> None:
        self._fase = v
        self.update()

    def _arrancar(self) -> None:
        _marcha(self._respira, self._tono in ("ok", "aviso") and self.isVisible() and motion.decorativo())

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
        self._anim_hover = widgets.animar(self, self._hover, destino, motion.Dur.HOVER, self._paso_hover)

    def _paso_hover(self, v: float) -> None:
        self._hover = v
        self.update()

    def _ancho_texto(self, texto: str) -> float:
        return QFontMetricsF(_fuente(self.font(), 12, QFont.Weight.DemiBold)).horizontalAdvance(texto)

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        w = self._ancho_texto(self._txt_previo) * (1 - self._t_txt) + self._ancho_texto(self._texto) * self._t_txt
        return QSize(int(w) + 14 + 12 + 10 + 4, 30)

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
        if self._tono in ("ok", "aviso") and motion.decorativo():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alfa(color, 0.35 * (1 - self._fase)))
            r = 4 + 5 * self._fase
            p.drawEllipse(centro, r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(centro, 4, 4)
        p.setFont(_fuente(self.font(), 12, QFont.Weight.DemiBold))
        zona = QRectF(caja.left() + 28, caja.top(), caja.width() - 34, caja.height())
        alin = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        base = col("texto")
        if self._t_txt < 1.0:
            p.setPen(con_alfa(base, 1 - self._t_txt))
            p.drawText(zona.translated(0, -3 * self._t_txt), alin, self._txt_previo)
            p.setPen(con_alfa(base, self._t_txt))
            p.drawText(zona.translated(0, 3 * (1 - self._t_txt)), alin, self._texto)
        else:
            p.setPen(base)
            p.drawText(zona, alin, self._texto)


# ------------------------------------------------------------------ botones con movimiento
def _icono_refrescar(p: QPainter, color: QColor, angulo: float) -> None:
    p.save()
    p.translate(8, 8)
    p.rotate(angulo)
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
    p.restore()


def _icono_cargando(p: QPainter, color: QColor, angulo: float) -> None:
    p.save()
    p.translate(8, 8)
    p.rotate(angulo)
    r = 5.4
    p.setPen(QPen(con_alfa(color, 0.22), 1.8))
    p.drawEllipse(QPointF(0, 0), r, r)
    p.setPen(QPen(color, 1.9, cap=Qt.PenCapStyle.RoundCap))
    p.drawArc(QRectF(-r, -r, 2 * r, 2 * r), 90 * 16, -100 * 16)
    p.restore()


def _icono_pausa_play(p: QPainter, color: QColor, m: float) -> None:
    """Pausa (m=0) y reproducir (m=1) que se transforman una en otra (cross-fade con escala)."""
    p.save()
    p.translate(8, 8)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    if m < 0.999:
        p.save()
        p.setOpacity((1 - m) ** 1.4)
        e = 1 - 0.35 * m
        p.scale(e, e)
        p.drawRoundedRect(QRectF(-4.6, -5.2, 3.1, 10.4), 1.2, 1.2)
        p.drawRoundedRect(QRectF(1.5, -5.2, 3.1, 10.4), 1.2, 1.2)
        p.restore()
    if m > 0.001:
        p.save()
        p.setOpacity(m ** 1.4)
        e = 0.65 + 0.35 * m
        p.scale(e, e)
        tri = QPainterPath()
        tri.moveTo(-3.6, -5.6)
        tri.lineTo(5.6, 0)
        tri.lineTo(-3.6, 5.6)
        tri.closeSubpath()
        p.drawPath(tri)
        p.restore()
    p.restore()


def _icono_check(p: QPainter, color: QColor, t: float) -> None:
    p.setPen(QPen(color, 2.0, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(ruta_parcial([QPointF(3.2, 8.6), QPointF(6.6, 12), QPointF(12.8, 4.6)], t))


def _icono_alerta(p: QPainter, color: QColor, t: float) -> None:
    p.save()
    p.setOpacity(min(1.0, t * 1.5))
    p.setPen(QPen(color, 2.0, cap=Qt.PenCapStyle.RoundCap))
    p.drawLine(QPointF(8, 3.2), QPointF(8, 9.2))
    p.drawPoint(QPointF(8, 12.4))
    p.restore()


class BotonPremium(QPushButton):
    """Botón con estados animados: hover y pulsación se funden (el estilo de la hoja de estilos se dibuja en normal,
    hover y pulsado y se mezcla con opacidad), la pulsación comprime y se recupera con un spring, el texto cambia con
    cross-fade y el icono puede girar (cargando), mostrar éxito (check que se dibuja) o error.

    Estados: ``normal``, ``cargando``, ``exito``, ``error`` (y ``disabled`` por Qt). Nada de esto bloquea el clic:
    ``bloquea`` solo se usa donde el comportamiento previo ya deshabilitaba el botón mientras trabaja.
    """

    def __init__(self, texto: str = "", parent: QWidget | None = None, icono: str | None = None,
                 bloquea: bool = False) -> None:
        super().__init__(texto, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._icono_tipo = icono          # None | "refrescar" | "pausaplay"
        self._bloquea = bloquea
        self._estado = "normal"
        self._angulo = 0.0
        self._viejo: QPixmap | None = None
        self._m_hover = Interpolador(self, self.update, motion.Dur.HOVER)
        self._m_pres = Interpolador(self, self.update, motion.Dur.PRESION)
        self._m_icono = Interpolador(self, self._poner_icono, motion.Dur.ESTADO)
        self._m_texto = Interpolador(self, self.update, motion.Dur.ESTADO)
        self._m_pres.fijar(p=0.0)
        self._m_hover.fijar(h=0.0)
        self._m_icono.fijar(pausado=0.0, chk=0.0)
        self._m_texto.fijar(cruce=0.0)
        self._giro = ciclo(self, 900, self._girar)
        self._anim_resultado: QVariantAnimation | None = None
        self._anim_ret: QVariantAnimation | None = None
        if icono:
            self._poner_icono()

    # --- estado
    def estado(self) -> str:
        return self._estado

    def girando(self) -> bool:
        return self._estado == "cargando"

    def set_reproduccion(self, pausado: bool) -> None:
        """Pausa ↔ reproducir: el icono se transforma. ``pausado`` = el servicio está en pausa (muestra «play»)."""
        self._icono_tipo = "pausaplay"
        self._m_icono.ir_a(pausado=1.0 if pausado else 0.0)

    def set_texto(self, texto: str) -> None:
        """Cambia el texto con cross-fade (el dato nuevo ya está en ``text()``)."""
        if texto == self.text():
            return
        if widgets.ANIMAR and self.isVisible() and not self.size().isEmpty():
            self._viejo = self.grab()
            self._m_texto.fijar(cruce=1.0)
            super().setText(texto)
            self._m_texto.ir_a(cruce=0.0)
        else:
            super().setText(texto)

    def iniciar(self) -> None:
        widgets._detener(self._anim_resultado)
        widgets._detener(self._anim_ret)
        self._estado = "cargando"
        self._m_icono.fijar(chk=0.0)
        if self._bloquea:
            self.setEnabled(False)
        _marcha(self._giro, True)
        self._poner_icono()

    def detener(self, resultado: str | None = None) -> None:
        """Termina el trabajo. ``resultado`` ``exito``/``error`` muestra un instante la marca (check dibujado / alerta)
        y vuelve al icono normal; sin resultado el icono gira hasta su posición de reposo."""
        widgets._detener(self._anim_resultado)
        self._giro.stop()
        if self._bloquea:
            self.setEnabled(True)
        if resultado in ("exito", "error") and widgets.ANIMAR:
            self._estado = resultado
            self._m_icono.fijar(chk=0.0)
            self._m_icono.ir_a(ms=motion.Dur.ESTADO, chk=1.0)
            self._anim_resultado = widgets.animar(self, 0.0, 1.0, 1100, lambda _v: None, self._volver_normal)
            self._poner_icono()
            return
        self._estado = "normal"
        self._reposar_giro()

    def _volver_normal(self) -> None:
        self._estado = "normal"
        self._m_icono.fijar(chk=0.0)
        self._poner_icono()

    def _reposar_giro(self) -> None:
        """El icono termina su vuelta con desaceleración en lugar de quedarse a medio giro."""
        resto = (-self._angulo) % 360.0
        widgets._detener(self._anim_ret)
        if resto < 1.0 or not widgets.ANIMAR:
            self._angulo = 0.0
            self._poner_icono()
            return
        inicio = self._angulo

        def paso(v: float) -> None:
            self._angulo = v % 360.0
            self._poner_icono()

        self._anim_ret = widgets.animar(self, inicio, inicio + resto, motion.Dur.ENTRADA, paso, None,
                                        QEasingCurve.Type.OutCubic)

    def _girar(self, v: float) -> None:
        self._angulo = 360.0 * v
        self._poner_icono()

    # --- interacción
    def enterEvent(self, e) -> None:
        self._m_hover.ir_a(h=1.0)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._m_hover.ir_a(h=0.0)
        self._m_pres.ir_a(p=0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._m_pres.ir_a(ms=motion.Dur.PRESION, curva=QEasingCurve.Type.OutCubic, p=1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._m_pres.ir_a(ms=motion.Dur.ESTADO, curva=motion.curva_resorte(2.2), p=0.0)
        super().mouseReleaseEvent(e)

    def changeEvent(self, e) -> None:
        super().changeEvent(e)
        if e.type() in (QEvent.Type.PaletteChange, QEvent.Type.EnabledChange) and self._icono_tipo:
            self._poner_icono()

    def hideEvent(self, e) -> None:
        self._giro.stop()
        super().hideEvent(e)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self._estado == "cargando":
            _marcha(self._giro, True)

    # --- dibujo
    def _tinta(self) -> QColor:
        return QColor(self.palette().buttonText().color())

    def _poner_icono(self) -> None:
        if not self._icono_tipo and self._estado == "normal":
            if not self.icon().isNull():
                self.setIcon(QIcon())
            return
        dpr = 2
        px = QPixmap(16 * dpr, 16 * dpr)
        px.setDevicePixelRatio(dpr)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._tinta()
        if self._estado == "exito":
            _icono_check(p, color, self._m_icono("chk"))
        elif self._estado == "error":
            _icono_alerta(p, color, self._m_icono("chk"))
        elif self._estado == "cargando":
            (_icono_refrescar if self._icono_tipo == "refrescar" else _icono_cargando)(p, color, self._angulo)
        elif self._icono_tipo == "refrescar":
            _icono_refrescar(p, color, self._angulo)
        elif self._icono_tipo == "pausaplay":
            _icono_pausa_play(p, color, self._m_icono("pausado"))
        p.end()
        self.setIcon(QIcon(px))

    def paintEvent(self, _e) -> None:
        pr = QStylePainter(self)
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        activo = bool(opt.state & QStyle.StateFlag.State_Enabled)
        reposo = QStyleOptionButton(opt)
        reposo.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_Sunken)
        pres = self._m_pres("p") if activo else 0.0
        hov = max(0.0, min(1.0, self._m_hover("h"))) if activo else 0.0
        c = QPointF(self.width() / 2, self.height() / 2)
        pr.translate(c)
        esc = 1.0 - 0.04 * pres
        pr.scale(esc, esc)
        pr.translate(-c)
        pr.drawControl(QStyle.ControlElement.CE_PushButton, reposo)
        if hov > 0.004:
            sobre = QStyleOptionButton(reposo)
            sobre.state |= QStyle.StateFlag.State_MouseOver
            pr.setOpacity(hov)
            pr.drawControl(QStyle.ControlElement.CE_PushButton, sobre)
        if pres > 0.004:
            hundido = QStyleOptionButton(reposo)
            hundido.state |= QStyle.StateFlag.State_Sunken | QStyle.StateFlag.State_MouseOver
            pr.setOpacity(pres)
            pr.drawControl(QStyle.ControlElement.CE_PushButton, hundido)
        cruce = self._m_texto("cruce")
        if self._viejo is not None and cruce > 0.01:
            pr.setOpacity(max(0.0, min(1.0, cruce)))
            pr.drawPixmap(0, 0, self._viejo)
        elif self._viejo is not None:
            self._viejo = None


class BotonActualizar(BotonPremium):
    """«Actualizar»: se comprime al pulsar, el icono gira mientras trabaja (y queda deshabilitado) y, al terminar,
    completa la vuelta con desaceleración. El texto cambia a «Actualizando…» con cross-fade si se le da uno."""

    def __init__(self, texto: str = "Actualizar", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent, icono="refrescar", bloquea=True)
        self.setObjectName("accionSync")
        self._texto_base = texto

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


# Partículas ambientales (ángulo inicial, radio relativo, tamaño, fase): posiciones fijas y discretas, no aleatorias,
# para que la composición sea estable entre repintados y entre arranques.
_PARTICULAS = ((0.3, 1.30, 1.7, 0.00), (1.1, 1.55, 1.2, 0.37), (1.9, 1.40, 2.0, 0.71), (2.7, 1.68, 1.3, 0.15),
               (3.6, 1.34, 1.6, 0.52), (4.4, 1.62, 1.9, 0.88), (5.3, 1.47, 1.2, 0.26))


class IconoBluetooth(QWidget):
    """Círculo con la runa de Bluetooth, estilo radar de conexión.

    * **activo**: halo azul que respira, ondas concéntricas que se expanden y se desvanecen, partículas ambientales
      discretas y pulso en el indicador de actividad.
    * **buscando** (conectando): arco de carga que gira.
    * **pausado / detenido**: el halo, las ondas y las partículas se apagan progresivamente (no de golpe) y el círculo
      pasa al estado inactivo con su insignia de pausa. **error**: insignia propia.

    Todo cambio de modo es continuo: la luz, el color y las ondas se interpolan con un ``Interpolador``. Los ciclos solo
    corren mientras algo se ve (visible y, en pausa, hasta que la luz llega a cero). En movimiento reducido no hay
    ondas, partículas ni respiración; el arco de «buscando» se conserva porque es un indicador funcional."""

    MODOS = ("activo", "buscando", "pausado", "error", "detenido")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modo, self._modo_prev = "pausado", "pausado"
        self._fase, self._orbita, self._entrada = 0.0, 0.0, 1.0
        self._anim_entrada: QVariantAnimation | None = None
        self._ciclo = ciclo(self, 2400, self._girar)
        self._ciclo_orbita = ciclo(self, 20000, self._girar_orbita)
        self._m = Interpolador(self, self._al_cambiar, motion.Dur.EXPANSION)
        self._m.fijar(luz=0.0, ond=0.0, mez=1.0)
        self.setMinimumSize(176, 176)

    def modo(self) -> str:
        return self._modo

    def luz(self) -> float:
        """Intensidad actual del halo (0–1); ``luz()`` > 0 mientras el halo se apaga tras una pausa."""
        return self._m("luz")

    def set_modo(self, modo: str) -> None:
        if modo not in self.MODOS:
            raise ValueError(modo)
        if modo != self._modo:
            self._modo_prev, self._modo = self._modo, modo
            self._m.fijar(mez=0.0)
            self._m.ir_a(luz={"activo": 1.0, "buscando": 0.8}.get(modo, 0.0), ond=1.0 if modo == "activo" else 0.0,
                         mez=1.0)
            widgets._detener(self._anim_entrada)
            self._anim_entrada = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.EXPANSION), self._paso_entrada,
                                                curva=motion.curva_resorte(1.5))
        self._arrancar()
        self.update()

    def reproducir_entrada(self) -> None:
        """Entrada de la pantalla: el círculo hace scale-in y la luz se enciende desde cero."""
        luz, ond = self._m.destino("luz"), self._m.destino("ond")
        self._m.fijar(luz=0.0, ond=0.0)
        self._m.ir_a(ms=motion.Dur.EXPANSION + 200, luz=luz, ond=ond)
        widgets._detener(self._anim_entrada)
        self._entrada = 0.0
        self._anim_entrada = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.EXPANSION), self._paso_entrada,
                                            curva=motion.curva_resorte(1.6))

    def _paso_entrada(self, v: float) -> None:
        self._entrada = v
        self.update()

    def _girar(self, v: float) -> None:
        self._fase = v
        self.update()

    def _girar_orbita(self, v: float) -> None:
        self._orbita = v
        self.update()

    def _al_cambiar(self) -> None:
        self.update()
        self._arrancar()

    def _arrancar(self) -> None:
        visible = self.isVisible()
        luz, ond = self._m("luz"), self._m("ond")
        spinner = self._modo == "buscando"
        _marcha(self._ciclo, visible and (spinner or (motion.decorativo() and (luz > 0.02 or ond > 0.02))))
        _marcha(self._ciclo_orbita, visible and motion.decorativo() and ond > 0.02)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._arrancar()

    def hideEvent(self, e) -> None:
        self._ciclo.stop()
        self._ciclo_orbita.stop()
        super().hideEvent(e)

    @staticmethod
    def _color_de(modo: str) -> QColor:
        return {"activo": AZUL, "buscando": AZUL, "error": col("error")}.get(modo, col("texto_suave"))

    @staticmethod
    def _opacidad_de(modo: str) -> float:
        return {"pausado": 0.62, "detenido": 0.45}.get(modo, 1.0)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        radio = min(self.width(), self.height()) / 2 - 4
        nucleo = radio * 0.5 * (0.85 + 0.15 * min(self._entrada, 1.25))
        modo = self._modo
        luz, ond, mez = self._m("luz"), max(0.0, self._m("ond")), max(0.0, min(1.0, self._m("mez", 1.0)))
        base = mezclar(self._color_de(self._modo_prev), self._color_de(modo), mez)
        opac = self._opacidad_de(self._modo_prev) * (1 - mez) + self._opacidad_de(modo) * mez
        deco = motion.decorativo()
        resp = 0.5 + 0.5 * math.sin(2 * math.pi * self._fase) if deco else 0.5
        p.setPen(Qt.PenStyle.NoPen)
        if luz > 0.01:   # halo azul que respira
            hr = nucleo * (1.75 + 0.18 * resp)
            halo = QRadialGradient(c, hr)
            halo.setColorAt(0.0, con_alfa(base, 0.34 * luz * (0.62 + 0.38 * resp)))
            halo.setColorAt(0.55, con_alfa(base, 0.12 * luz))
            halo.setColorAt(1.0, con_alfa(base, 0.0))
            p.setBrush(halo)
            p.drawEllipse(c, hr, hr)
        if ond > 0.01 and deco:   # ondas concéntricas: nacen en el centro y se desvanecen al expandirse
            for i in range(3):
                f = (self._fase + i / 3) % 1.0
                r = nucleo + (radio - nucleo) * f
                p.setBrush(con_alfa(base, 0.10 * (1 - f) * ond))
                p.drawEllipse(c, r, r)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(con_alfa(base, 0.45 * (1 - f) * ond), 1.6))
                p.drawEllipse(c, r, r)
                p.setPen(Qt.PenStyle.NoPen)
        if ond > 0.02 and deco:   # partículas ambientales
            for k, (a0, rel, tam, ph) in enumerate(_PARTICULAS):
                ang = a0 + 2 * math.pi * self._orbita * (1 if k % 2 == 0 else -1)
                vivo = (self._fase + ph) % 1.0
                rr = nucleo * rel * (1 + 0.05 * math.sin(2 * math.pi * vivo))
                q = QPointF(c.x() + rr * math.cos(ang), c.y() + rr * math.sin(ang))
                a = 0.55 * ond * math.sin(math.pi * vivo)
                g = QRadialGradient(q, tam * 3.2)
                g.setColorAt(0.0, con_alfa(base, a * 0.5))
                g.setColorAt(1.0, con_alfa(base, 0.0))
                p.setBrush(g)
                p.drawEllipse(q, tam * 3.2, tam * 3.2)
                p.setBrush(con_alfa(mezclar(base, QColor("#FFFFFF"), 0.4), a))
                p.drawEllipse(q, tam, tam)
        if modo == "activo" and ond > 0.01:
            nucleo *= 1 + 0.03 * resp * ond
        if modo == "buscando":
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
        self._insignia(p, QPointF(c.x() + nucleo * 0.74, c.y() + nucleo * 0.74), nucleo * 0.3 * min(1.0, 0.4 + self._entrada))

    def _insignia(self, p: QPainter, c: QPointF, r: float) -> None:
        modo = self._modo
        if modo == "buscando":
            return
        color = {"activo": col("acento"), "error": col("error")}.get(modo, col("texto_suave"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col("tarjeta"))
        p.drawEllipse(c, r + 3, r + 3)
        if modo == "activo" and motion.decorativo():   # indicador de actividad con pulso suave
            p.setBrush(con_alfa(color, 0.35 * (1 - self._fase) * self._m("ond")))
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
    return i18n.miles(int(n))


class Odometro(QWidget):
    """Cifra grande cuyos dígitos giran como un odómetro al cambiar. ``valor()``/``texto()`` son el dato final al
    instante. Un cambio pequeño es rápido; uno grande dura más y los dígitos arrancan de derecha a izquierda. No se
    reinicia si el valor recibido es el mismo."""

    ESCALON = 0.16   # retardo relativo entre columnas (de la unidad hacia la izquierda)

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

    @staticmethod
    def duracion_para(delta: int) -> int:
        """Más cambio, más tiempo (sin pasar de ~0,8 s): 1–2 → 240 ms, decenas → ~420 ms, miles → ~700 ms."""
        d = abs(int(delta))
        if d <= 2:
            return 240
        return int(min(780, 330 + 120 * math.log10(d)))

    def set_valor(self, valor: int) -> None:
        valor = int(valor)
        if valor == self._valor:
            return
        self._dir = 1 if valor > self._valor else -1
        delta = valor - self._valor
        self._prev = self._txt   # lo que se veía queda como «anterior»
        self._valor, self._txt = valor, formato_miles(valor)
        widgets._detener(self._anim)
        self._p = 0.0
        self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(self.duracion_para(delta)), self._paso,
                                    curva=QEasingCurve.Type.InOutCubic)
        self.updateGeometry()

    def _paso(self, v: float) -> None:
        self._p = v
        if v >= 1.0:
            self._prev = self._txt      # terminó: sin columnas fantasma (si no, «1.280» → «6» quedaba corrido a la derecha)
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
        paso_y = fm.height() * 0.95
        base = (alto + fm.ascent() - fm.descent()) / 2
        total = 1 + self.ESCALON * min(n - 1, 4)
        x = 0.0
        for idx, (a, b) in enumerate(zip(viejo, nuevo)):
            ancho = max(fm.horizontalAdvance(a), fm.horizontalAdvance(b))
            if a == b or self._p >= 1.0:
                p.setPen(color)
                p.drawText(QPointF(x, base), b)
                x += ancho
                continue
            desde_derecha = min(n - 1 - idx, 4)
            loc = max(0.0, min(1.0, self._p * total - self.ESCALON * desde_derecha))
            p.save()
            p.setClipRect(QRectF(x, 0, ancho + 1, alto))
            if a.isdigit() and b.isdigit():
                va, vb = int(a), int(b)
                pasos = (vb - va) % 10 if self._dir > 0 else -((va - vb) % 10)
                pos = va + pasos * loc
                k0 = math.floor(pos)
                frac = pos - k0
                p.setPen(con_alfa(color, 1 - frac * 0.85))
                p.drawText(QPointF(x, base - frac * paso_y), str((k0) % 10))
                p.setPen(con_alfa(color, 0.15 + frac * 0.85))
                p.drawText(QPointF(x, base + (1 - frac) * paso_y), str((k0 + 1) % 10))
            else:   # aparece o desaparece una columna (p. ej. 99 → 100)
                p.setPen(con_alfa(color, 1 - loc))
                p.drawText(QPointF(x, base - self._dir * loc * paso_y), a)
                p.setPen(con_alfa(color, loc))
                p.drawText(QPointF(x, base + self._dir * (1 - loc) * paso_y), b)
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
    """Android → Bluetooth → PC servidor → Oracle.

    Cada enlace es ``off``, ``enlazado`` o ``activo``. Los **paquetes** luminosos (con estela y glow) solo nacen de
    eventos reales: ``emitir_lecturas(n)`` cuando el servicio recibe lecturas, ``confirmar_escritura(n)`` cuando Oracle
    confirma procesadas; mientras un enlace está ``activo`` se mantiene además un goteo ambiental cuya cadencia sale de
    la tasa real de lecturas (``velocidad``). Al llegar a un nodo el paquete se desvanece y el nodo reacciona (pulso).

    Un enlace inactivo se atenúa, uno pausado pasa a gris y los paquetes que lo cruzaban se apagan; un error tiñe de
    rojo el tramo afectado (nodo 1 → enlace 0; nodos 2 y 3 → enlace 2), con destello y una insignia en el nodo. Todos los
    cambios de color y nivel se interpolan. Un único reloj de ~30 fps corre **solo** mientras hay algo que mover y el
    widget es visible; con movimiento reducido no hay paquetes ni ciclos continuos (los indicadores de estado sí)."""

    elegido = pyqtSignal(int)
    MAX_PAQUETES = 24
    TRAMO_ERROR = {1: (0,), 2: (2,), 3: (2,)}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nodos = [{"tono": "pausa", "estado": "", "detalle": ""} for _ in NODOS]
        self._enlaces = ["off", "off", "off"]
        self._etiquetas = ["", "", ""]
        self._velocidad, self._error, self._alerta = 1.0, None, 1.0
        self._hover: int | None = None
        self._anim_alerta: QVariantAnimation | None = None
        self._anim_rev: QVariantAnimation | None = None
        self._rev = 99.0                       # revelado de entrada (izquierda → derecha); 99 = ya completo
        self._paquetes: list[list[float]] = []   # [enlace, t, velocidad, tamaño, vida]
        self._cola: list[list[float]] = []       # [segundos que faltan, enlace]
        self._pulsos = [0.0] * 4                 # destello por nodo (1 → 0)
        self._escritura = 0.0                    # destello de «escritura confirmada» en Oracle
        self._ambiente = [0.0, 0.0, 0.0]
        self._fase = 0.0
        self._m = Interpolador(self, self.update, motion.Dur.ESTADO)
        for i in range(4):
            self._m.fijar(**{f"e{i}": 0.0, f"a{i}": 0.0, f"h{i}": 0.0, f"x{i}": 0.0})
        for i in range(3):
            self._m.fijar(**{f"n{i}": 0.0, f"r{i}": 0.0})
        self._reloj = QTimer(self)
        self._reloj.setInterval(33)
        self._reloj.timeout.connect(self._avanzar)
        self._cron = QElapsedTimer()
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

    def paquetes_vivos(self) -> int:
        return len(self._paquetes) + len(self._cola)

    def reloj_activo(self) -> bool:
        return self._reloj.isActive()

    def set_modelo(self, nodos: list[dict], enlaces: list[str], etiquetas: list[str],
                   velocidad: float = 1.0, error: int | None = None) -> None:
        nuevo_error = error is not None and error != self._error
        self._nodos, self._enlaces, self._etiquetas = [dict(n) for n in nodos], list(enlaces), list(etiquetas)
        self._velocidad, self._error = velocidad, error
        nivel = {"off": 0.0, "enlazado": 0.55, "activo": 1.0}
        destinos: dict[str, float] = {}
        for i, estado in enumerate(self._enlaces):
            destinos[f"n{i}"] = nivel.get(estado, 0.0)
            destinos[f"r{i}"] = 1.0 if error is not None and i in self.TRAMO_ERROR.get(error, ()) else 0.0
        for i in range(4):
            vecino_activo = any(self._enlaces[j] == "activo" for j in (i - 1, i) if 0 <= j < 3)
            destinos[f"a{i}"] = 1.0 if vecino_activo else 0.0
            destinos[f"e{i}"] = 1.0 if error == i else 0.0
            destinos[f"x{i}"] = 1.0 if self._nodos[i].get("ocupado") else 0.0
        self._m.ir_a(**destinos)
        if nuevo_error:   # alerta breve: el nodo vibra una vez
            widgets._detener(self._anim_alerta)
            self._alerta = 0.0
            self._anim_alerta = widgets.animar(self, 0.0, 1.0, 460, self._paso_alerta)
            if error is not None:
                self._pulsos[error] = 1.0
        self._arrancar()
        self.update()

    # --- eventos reales
    def pulso(self, nodo: int) -> None:
        """Destello de un nodo (se conectó, recibió, procesó…)."""
        if widgets.ANIMAR and 0 <= nodo < 4:
            self._pulsos[nodo] = 1.0
            self._arrancar()

    def emitir_lecturas(self, n: int) -> None:
        """Llegaron ``n`` lecturas reales del celular: viajan Android → Bluetooth → PC (hasta 8 a la vez)."""
        self.pulso(0)
        if not widgets.ANIMAR or n <= 0:
            return
        if motion.decorativo():
            for k in range(min(int(n), 8)):
                self._cola.append([0.07 * k, 0.0])
        self._arrancar()

    def confirmar_escritura(self, n: int) -> None:
        """Oracle confirmó ``n`` lecturas procesadas: viajan PC → Oracle y Oracle destella."""
        if not widgets.ANIMAR or n <= 0:
            return
        if motion.decorativo():
            for k in range(min(int(n), 5)):
                self._cola.append([0.09 * k, 2.0])
        else:
            self._pulsos[3] = 1.0
            self._escritura = 1.0
        self._arrancar()

    def revelar(self, retardo_ms: int = 0) -> None:
        """Entrada de la pantalla: nodos y enlaces se revelan de izquierda a derecha (tras ``retardo_ms``; mientras
        espera el flujo permanece oculto para que no parpadee)."""
        widgets._detener(self._anim_rev)
        if not widgets.ANIMAR:
            self._rev = 99.0
            return
        self._rev = 0.0

        def arrancar() -> None:
            if sip.isdeleted(self):
                return
            self._anim_rev = widgets.animar(self, 0.0, 4.3, motion.dur(1150), self._paso_rev, None,
                                            QEasingCurve.Type.InOutSine)

        if retardo_ms > 0:
            QTimer.singleShot(retardo_ms, arrancar)
        else:
            arrancar()
        self.update()

    def _paso_rev(self, v: float) -> None:
        self._rev = v if v < 4.3 else 99.0
        self.update()

    def _paso_alerta(self, v: float) -> None:
        self._alerta = v
        self.update()

    # --- reloj
    def _necesita_reloj(self) -> bool:
        if not (widgets.ANIMAR and self.isVisible()):
            return False
        if self._paquetes or self._cola or any(p > 0.001 for p in self._pulsos) or self._escritura > 0.001:
            return True
        if not motion.decorativo():
            return False
        return "activo" in self._enlaces or any(self._m(f"x{i}") > 0.02 or self._m(f"a{i}") > 0.02 for i in range(4))

    def _arrancar(self) -> None:
        if self._necesita_reloj():
            if not self._reloj.isActive():
                self._cron.start()
                self._reloj.start()
        else:
            self._reloj.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._arrancar()

    def hideEvent(self, e) -> None:
        self._reloj.stop()
        super().hideEvent(e)

    def _lanzar(self, enlace: int) -> None:
        if len(self._paquetes) >= self.MAX_PAQUETES:
            return
        k = len(self._paquetes) + int(self._fase * 7)
        tam = (0.85, 1.0, 1.2, 0.95, 1.1)[k % 5]
        vel = (0.62 + 0.30 * min(2.5, self._velocidad) / 2.5) * (0.92 + 0.08 * (k % 3))
        self._paquetes.append([float(enlace), 0.0, vel, tam, 1.0])

    def _avanzar(self) -> None:
        dt = min(0.1, self._cron.restart() / 1000.0)
        self._fase = (self._fase + dt / 1.6) % 1.0
        for item in list(self._cola):
            item[0] -= dt
            if item[0] <= 0:
                self._cola.remove(item)
                self._lanzar(int(item[1]))
        if motion.decorativo():   # goteo ambiental del enlace activo, a la cadencia del tráfico real
            ritmo = 0.8 + 0.7 * min(2.5, self._velocidad)
            for i in range(3):
                if self._enlaces[i] == "activo":
                    self._ambiente[i] += dt * ritmo / 1.4
                    if self._ambiente[i] >= 1.0:
                        self._ambiente[i] = 0.0
                        self._lanzar(i)
        vivos: list[list[float]] = []
        for pk in self._paquetes:
            i = int(pk[0])
            if self._enlaces[i] != "activo" and self._m(f"n{i}") < 0.9:   # el enlace se apagó: el paquete se apaga
                pk[4] -= dt / 0.22
                if pk[4] <= 0:
                    continue
            pk[1] += dt * pk[2]
            if pk[1] >= 1.0:   # llegó al nodo siguiente
                self._pulsos[i + 1] = 1.0
                if i < 2 and self._enlaces[i + 1] == "activo":
                    self._lanzar(i + 1)   # sigue su camino al siguiente tramo
                if i == 2:
                    self._escritura = 1.0
                continue
            vivos.append(pk)
        self._paquetes = vivos
        self._pulsos = [max(0.0, v - dt / 0.75) for v in self._pulsos]
        self._escritura = max(0.0, self._escritura - dt / 0.9)
        self.update()
        self._arrancar()

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
            self._m.ir_a(ms=motion.Dur.HOVER, **{f"h{k}": 1.0 if k == i else 0.0 for k in range(4)})
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = None
        self._m.ir_a(ms=motion.Dur.HOVER, **{f"h{k}": 0.0 for k in range(4)})
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

    @staticmethod
    def _tramo(rev: float, inicio: float, largo: float) -> float:
        return max(0.0, min(1.0, (rev - inicio) / largo))

    def _enlace(self, p: QPainter, i: int) -> None:
        a, b = self._centro_icono(i), self._centro_icono(i + 1)
        x1, x2, y = a.x() + 34, b.x() - 34, a.y()
        trazo = self._tramo(self._rev, i * 0.9 + 0.45, 0.9)       # animación de trazado de la conexión
        if trazo <= 0:
            return
        xf = x1 + (x2 - x1) * trazo
        nivel = max(0.0, min(1.0, self._m(f"n{i}")))
        rojo = max(0.0, min(1.0, self._m(f"r{i}")))
        color = mezclar(AZUL if i < 2 else col("acento"), col("error"), rojo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(col("borde_fuerte"), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(x1, y), QPointF(xf, y))
        if nivel > 0.01 or rojo > 0.01:
            alfa = max(nivel, rojo * 0.8)
            g = QLinearGradient(x1, y, x2, y)
            g.setColorAt(0.0, con_alfa(color, 0.35 * alfa))
            g.setColorAt(0.5, con_alfa(color, 0.55 * alfa + 0.4 * alfa * max(0.0, nivel - 0.55) / 0.45))
            g.setColorAt(1.0, con_alfa(color, 0.35 * alfa))
            p.setPen(QPen(g, 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y), QPointF(xf, y))
        if rojo > 0.01 and self._pulsos[self._error or 0] > 0.01 and self._error in self.TRAMO_ERROR \
                and i in self.TRAMO_ERROR[self._error]:   # destello corto del tramo afectado
            p.setPen(QPen(con_alfa(col("error"), 0.55 * self._pulsos[self._error]), 7, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x1, y), QPointF(xf, y))
        if widgets.ANIMAR:
            for pk in self._paquetes:
                if int(pk[0]) == i:
                    self._paquete(p, pk, x1, x2, y, color)
        texto = self._etiquetas[i]
        if texto and trazo >= 1.0:
            p.setFont(_fuente(self.font(), 10, QFont.Weight.DemiBold))
            fm = QFontMetricsF(p.font())
            w = min(fm.horizontalAdvance(texto) + 16, x2 - x1)
            caja = QRectF((x1 + x2) / 2 - w / 2, y - 26, w, 18)
            p.setPen(QPen(col("borde"), 1))
            p.setBrush(col("tarjeta"))
            p.drawRoundedRect(caja, 9, 9)
            p.setPen(col("texto_tenue"))
            p.drawText(caja, Qt.AlignmentFlag.AlignCenter, fm.elidedText(texto, Qt.TextElideMode.ElideRight, w - 8))

    def _paquete(self, p: QPainter, pk: list[float], x1: float, x2: float, y: float, color: QColor) -> None:
        t, tam, vida = pk[1], pk[3], pk[4]
        env = min(1.0, t * 7) * min(1.0, (1 - t) * 6) * max(0.0, vida)   # nace y se desvanece al llegar al nodo
        if env <= 0.01:
            return
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(5, 0, -1):     # estela luminosa
            tt = t - k * 0.024
            if tt < 0:
                continue
            x = x1 + (x2 - x1) * tt
            p.setBrush(con_alfa(color, env * 0.30 * (1 - k / 6)))
            r = 3.4 * tam * (1 - k * 0.12)
            p.drawEllipse(QPointF(x, y), r, r)
        x = x1 + (x2 - x1) * t
        halo = QRadialGradient(QPointF(x, y), 12 * tam)
        halo.setColorAt(0.0, con_alfa(color, 0.45 * env))
        halo.setColorAt(1.0, con_alfa(color, 0.0))
        p.setBrush(halo)
        p.drawEllipse(QPointF(x, y), 12 * tam, 12 * tam)
        p.setBrush(mezclar(color, QColor("#FFFFFF"), 0.55 * env + 0.1))
        p.drawRoundedRect(QRectF(x - 4.5 * tam, y - 2.4 * tam, 9 * tam, 4.8 * tam), 2.4, 2.4)

    def _nodo(self, p: QPainter, i: int) -> None:
        n = self._nodos[i]
        aparece = self._tramo(self._rev, i * 0.9, 0.8)
        if aparece <= 0:
            return
        caja = self._tarjeta(i)
        error = self._error == i
        e = max(0.0, min(1.0, self._m(f"e{i}")))
        if error and self._alerta < 1.0:
            caja = caja.translated(math.sin(self._alerta * math.pi * 7) * 5 * (1 - self._alerta), 0)
        color = self._color_nodo(i)
        hov = max(0.0, min(1.0, self._m(f"h{i}")))
        act = max(0.0, min(1.0, self._m(f"a{i}")))
        p.save()
        p.setOpacity(aparece)
        if aparece < 1.0:    # entrada: el nodo crece desde su centro
            c0 = caja.center()
            p.translate(c0)
            p.scale(0.92 + 0.08 * aparece, 0.92 + 0.08 * aparece)
            p.translate(-c0)
        p.setBrush(mezclar(mezclar(col("tarjeta_alt"), color, 0.07 * e), col("tarjeta"), 0.35 * hov))
        borde = mezclar(mezclar(col("borde"), col("borde_fuerte"), hov), col("error"), e)
        p.setPen(QPen(borde, 1 + 0.5 * e))
        p.drawRoundedRect(caja, 18, 18)
        c = QPointF(caja.center().x(), caja.top() + 46)
        p.setPen(Qt.PenStyle.NoPen)
        if act > 0.01:   # iluminación contextual del nodo activo
            r = 27 + 16 * act
            luz = QRadialGradient(c, r)
            luz.setColorAt(0.0, con_alfa(color, 0.20 * act))
            luz.setColorAt(1.0, con_alfa(color, 0.0))
            p.setBrush(luz)
            p.drawEllipse(c, r, r)
        pulso = self._pulsos[i]
        if pulso > 0.01:
            r = 27 + 15 * (1 - pulso) if motion.decorativo() else 29
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(con_alfa(color, 0.55 * pulso), 2))
            p.drawEllipse(c, r, r)
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alfa(color, 0.16 + 0.12 * pulso))
        p.drawEllipse(c, 27, 27)
        {0: _icono_android, 1: _icono_bt, 2: _icono_pc, 3: _icono_oracle}[i](p, c, color)
        self._extras_nodo(p, i, c, color)
        if e > 0.01:      # insignia de error en el nodo
            q = QPointF(c.x() + 22, c.y() - 22)
            s = min(1.0, e * 1.4)
            p.setPen(QPen(col("tarjeta"), 2))
            p.setBrush(col("error"))
            p.drawEllipse(q, 8 * s, 8 * s)
            p.setPen(QPen(QColor("#FFFFFF"), 1.8 * s, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(q.x(), q.y() - 3.4 * s), QPointF(q.x(), q.y() + 0.8 * s))
            p.drawPoint(QPointF(q.x(), q.y() + 3.4 * s))
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
        p.restore()

    def _extras_nodo(self, p: QPainter, i: int, c: QPointF, color: QColor) -> None:
        """Actividad propia de cada nodo: punto vivo en Android, ondas de comunicación en Bluetooth, arco de proceso en
        el PC y destello de escritura en Oracle."""
        deco = motion.decorativo()
        act = max(0.0, min(1.0, self._m(f"a{i}")))
        if i == 0 and self._nodos[0]["tono"] == "ok":       # dispositivo conectado
            q = QPointF(c.x() + 19, c.y() - 19)
            p.setPen(QPen(col("tarjeta"), 2))
            p.setBrush(col("acento"))
            p.drawEllipse(q, 5, 5)
        elif i == 1 and act > 0.02 and deco:                # ondas de comunicación
            p.setBrush(Qt.BrushStyle.NoBrush)
            for k in range(2):
                f = (self._fase + k / 2) % 1.0
                r = 27 + 14 * f
                p.setPen(QPen(con_alfa(AZUL, 0.40 * (1 - f) * act), 1.6))
                p.drawEllipse(c, r, r)
        elif i == 2:                                        # procesamiento
            x = max(0.0, min(1.0, self._m("x2")))
            if x > 0.02:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(con_alfa(color, 0.9 * x), 2.4, cap=Qt.PenCapStyle.RoundCap))
                r = 31
                inicio = int((90 - 360 * self._fase) * 16) if deco else 90 * 16
                p.drawArc(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), inicio, -110 * 16)
        elif i == 3 and self._escritura > 0.01:             # escritura confirmada: destello discreto + indicador
            e = self._escritura
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alfa(col("acento"), 0.22 * e))
            p.drawEllipse(c, 27 + 4 * (1 - e), 27 + 4 * (1 - e))
            q = QPointF(c.x() + 21, c.y() + 19)
            p.setBrush(con_alfa(col("acento"), min(1.0, e * 1.6)))
            p.drawEllipse(q, 5.5, 5.5)
            p.setPen(QPen(QColor("#FFFFFF"), 1.5, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(ruta_parcial([QPointF(q.x() - 2.4, q.y()), QPointF(q.x() - 0.6, q.y() + 2), QPointF(q.x() + 2.6, q.y() - 2)],
                                    min(1.0, (1 - e) * 4)))


# ------------------------------------------------------------------ etapas de la sincronización
ETAPAS = ("Esperando dispositivo", "Dispositivo conectado", "Recibiendo lecturas", "Procesando información",
          "Sincronización completada")


class Etapas(QWidget):
    """Cinco etapas que reflejan el estado real. ``set_estado(actual, hechas, error)``: las primeras ``hechas`` llevan
    check, ``actual`` es la que está en curso y ``error`` (si lo hay) se pinta en rojo y vibra una vez.

    Todo es continuo: la línea se llena de izquierda a derecha y cada check se **dibuja** cuando el llenado llega a su
    paso; el paso activo crece muy poco, lleva halo y un arco que gira; al completarse su color pasa a verde y al fallar
    a rojo con icono de alerta. Nada avanza por temporizador: solo cambian los destinos cuando cambia el estado."""

    def __init__(self, nombres: list[str] | tuple[str, ...] = ETAPAS, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nombres = list(nombres)
        self._actual: int | None = None
        self._hechas, self._error = 0, None
        self._fase, self._alerta = 0.0, 1.0
        self._m = Interpolador(self, self.update, 520)
        self._m.fijar(lleno=0.0, **{f"{k}{i}": 0.0 for i in range(len(self._nombres)) for k in "hae"})
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
        n = len(self._nombres)
        destinos = {"lleno": float(min(n - 1, error if error is not None else hechas))}
        for i in range(n):
            destinos[f"h{i}"] = 1.0 if i < hechas else 0.0
            destinos[f"a{i}"] = 1.0 if (i == actual and i >= hechas) else 0.0
            destinos[f"e{i}"] = 1.0 if i == error else 0.0
        self._m.ir_a(**destinos)
        if nuevo_error:
            widgets._detener(self._anim_alerta)
            self._alerta = 0.0
            self._anim_alerta = widgets.animar(self, 0.0, 1.0, 430, self._paso_alerta)
        _marcha(self._halo, actual is not None and self.isVisible() and motion.decorativo())
        self.update()

    def _paso_alerta(self, v: float) -> None:
        self._alerta = v
        self.update()

    def _latir(self, v: float) -> None:
        self._fase = v
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        _marcha(self._halo, self._actual is not None and motion.decorativo())

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
        lleno = max(0.0, self._m("lleno"))
        p.setPen(QPen(col("borde_fuerte"), 3, cap=Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(xs[0], cy), QPointF(xs[-1], cy))
        lleno_x = xs[0] + (xs[-1] - xs[0]) * min(1.0, lleno / max(1, n - 1))
        erro = max((self._m(f"e{i}") for i in range(n)), default=0.0)
        if lleno_x > xs[0]:
            color_linea = mezclar(col("acento"), col("error"), max(0.0, min(1.0, erro)))
            p.setPen(QPen(color_linea, 3, cap=Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(xs[0], cy), QPointF(lleno_x, cy))
            frac = lleno - math.floor(lleno)
            if 0.02 < frac < 0.98 and widgets.ANIMAR:   # la línea «se ilumina» en la punta mientras avanza
                halo = QRadialGradient(QPointF(lleno_x, cy), 14)
                halo.setColorAt(0.0, con_alfa(color_linea, 0.55))
                halo.setColorAt(1.0, con_alfa(color_linea, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(lleno_x, cy), 14, 14)
        for i, nombre in enumerate(self._nombres):
            h = max(0.0, min(1.0, self._m(f"h{i}")))
            a = max(0.0, min(1.0, self._m(f"a{i}")))
            e = max(0.0, min(1.0, self._m(f"e{i}")))
            # el check se completa cuando el llenado de la línea llega a este paso (continuidad entre pasos)
            hecho = min(h, max(0.0, min(1.0, lleno - i + 1)))
            cx = xs[i]
            if self._error == i and self._alerta < 1.0:
                cx += math.sin(self._alerta * math.pi * 7) * 5 * (1 - self._alerta)
            radio = r * (1 + 0.12 * a)
            if a > 0.01 and motion.decorativo():     # halo del paso activo y arco que gira
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(con_alfa(AZUL, 0.32 * (1 - self._fase) * a))
                p.drawEllipse(QPointF(cx, cy), radio + 9 * self._fase, radio + 9 * self._fase)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(con_alfa(AZUL, 0.85 * a), 2.2, cap=Qt.PenCapStyle.RoundCap))
                rr = radio + 4.5
                p.drawArc(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int((90 - 360 * self._fase) * 16), -80 * 16)
            elif a > 0.01:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(con_alfa(AZUL, 0.22 * a))
                p.drawEllipse(QPointF(cx, cy), radio + 5, radio + 5)
            reposo_f, reposo_b = col("tarjeta"), col("borde_fuerte")
            fondo = mezclar(mezclar(mezclar(reposo_f, AZUL, a), col("acento"), hecho), col("error"), e)
            borde = mezclar(mezclar(mezclar(reposo_b, AZUL, a), col("acento"), hecho), col("error"), e)
            p.setBrush(fondo)
            p.setPen(QPen(borde, 2))
            p.drawEllipse(QPointF(cx, cy), radio, radio)
            blanco = QPen(QColor("#FFFFFF"), 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if e > 0.01:                                   # alerta (aparece con escala)
                p.setPen(blanco)
                s = min(1.0, e * 1.3)
                p.drawLine(QPointF(cx, cy - 5 * s), QPointF(cx, cy + 1.5 * s))
                p.drawPoint(QPointF(cx, cy + 5 * s))
            elif hecho > 0.01:                             # check que se dibuja
                p.setPen(blanco)
                p.drawPath(ruta_parcial([QPointF(cx - 5, cy + 0.5), QPointF(cx - 1.5, cy + 4), QPointF(cx + 5.5, cy - 4)],
                                        hecho))
            if a > 0.01 and hecho < 0.99 and e < 0.01:     # punto del paso en curso
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(con_alfa(QColor("#FFFFFF"), a * (1 - hecho)))
                p.drawEllipse(QPointF(cx, cy), 3.6 * a, 3.6 * a)
            elif a < 0.99 and hecho < 0.01 and e < 0.01:    # punto del paso pendiente
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(con_alfa(col("borde_fuerte"), 1 - a))
                p.drawEllipse(QPointF(cx, cy), 3, 3)
            enfasis = max(a, hecho)
            destacado = enfasis > 0.5 or e > 0.5
            p.setFont(_fuente(self.font(), 12, QFont.Weight.DemiBold if destacado else QFont.Weight.Normal))
            p.setPen(mezclar(mezclar(col("texto_suave"), col("texto_fuerte"), enfasis), col("error"), e))
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
        self._ultimo_hover = 0
        self._anim: QVariantAnimation | None = None
        self._anim_rev: QVariantAnimation | None = None
        self._rev = 1.0              # revelado de la línea (0 → 1) cuando llegan los primeros datos
        self._m = Interpolador(self, self.update, motion.Dur.HOVER, QEasingCurve.Type.OutCubic)
        self._m.fijar(hx=0.0, tip=0.0)
        self._brillo = 0.0
        self._ciclo_carga = ciclo(self, 1500, self._mover_brillo)
        self._titulos = {"vacio": "Sin actividad en este periodo", "ayuda": "Cuando lleguen lecturas, aparecerán aquí.",
                         "cargando": "Cargando…"}
        self._cargando = True
        self.setMinimumHeight(220)
        self.setMouseTracking(True)

    def _mover_brillo(self, v: float) -> None:
        self._brillo = v
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        _marcha(self._ciclo_carga, self._cargando and motion.decorativo())

    def hideEvent(self, e) -> None:
        self._ciclo_carga.stop()
        super().hideEvent(e)

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
        era_vacia = self.vacia()
        self._cargando = False
        self._ciclo_carga.stop()
        self._act = act
        self._hover = None
        self._m.ir_a(tip=0.0)
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

        if era_vacia and not self.vacia():
            # primera carga (o tras un periodo vacío): la línea se dibuja de izquierda a derecha, el área aparece con
            # fade y los puntos entran escalonados. Un cambio de periodo posterior solo interpola (no vuelve a empezar).
            # (los valores van directos a su dato real: lo que se anima es el revelado, no las cifras)
            widgets._detener(self._anim)
            self._vista = {k: list(self._meta[k]) for k in self._meta}
            widgets._detener(self._anim_rev)
            self._rev = 0.0
            self._anim_rev = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.GRAFICA + 140), self._paso_rev, None,
                                            QEasingCurve.Type.InOutCubic)
            self.update()
            return
        self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(motion.Dur.GRAFICA - 100), paso,
                                    curva=QEasingCurve.Type.InOutCubic)

    def _paso_rev(self, v: float) -> None:
        self._rev = v
        self.update()

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
                anterior = self._hover
                self._hover = i
                if i is not None:
                    self._ultimo_hover = i
                    if anterior is None:     # entra el cursor: el indicador aparece en su sitio y se funde
                        self._m.fijar(hx=float(i))
                        self._m.ir_a(tip=1.0)
                    else:                    # se desliza suavemente de un punto al siguiente
                        self._m.ir_a(ms=motion.Dur.HOVER + 30, hx=float(i), tip=1.0)
                else:
                    self._m.ir_a(tip=0.0)
                self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = None
        self._m.ir_a(tip=0.0)
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
            rev = self._rev
            p.save()
            if rev < 1.0:   # revelado: la línea se dibuja de izquierda a derecha
                p.setClipRect(QRectF(plot.left() - 10, 0, (plot.width() + 20) * rev, self.height()))
            if clave != "errores":
                area = QPainterPath(linea)
                area.lineTo(pts[-1].x(), plot.bottom())
                area.lineTo(pts[0].x(), plot.bottom())
                area.closeSubpath()
                g = QLinearGradient(0, plot.top(), 0, plot.bottom())
                fade = max(0.0, min(1.0, (rev - 0.15) / 0.85)) ** 1.5   # el área aparece con fade-in
                g.setColorAt(0.0, con_alfa(color, (0.28 if clave == "recibidas" else 0.16) * fade))
                g.setColorAt(1.0, con_alfa(color, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawPath(area)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
            p.drawPath(linea)
            p.restore()
            if rev < 1.0 and len(pts) <= 40:   # puntos que entran escalonados
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                for k, q in enumerate(pts):
                    s = max(0.0, min(1.0, (rev - 0.6 * k / max(1, len(pts) - 1)) / 0.4))
                    if 0 < s < 1.0 or (s >= 1.0 and rev < 0.98):
                        p.drawEllipse(q, 3.2 * math.sin(math.pi * s / 2) if s < 1.0 else 0.0,
                                      3.2 * math.sin(math.pi * s / 2) if s < 1.0 else 0.0)
        self._leyenda(p)
        if self._m("tip") > 0.01:
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
        n = len(self._etiquetas)
        if n == 0:
            return
        i = max(0, min(n - 1, self._ultimo_hover if self._hover is None else self._hover))
        tip = max(0.0, min(1.0, self._m("tip")))
        hx = max(0.0, min(float(n - 1), self._m("hx")))
        x = plot.left() + (plot.width() * hx / (n - 1) if n > 1 else plot.width() / 2)   # el indicador se desliza
        p.save()
        p.setOpacity(tip)
        p.setPen(QPen(col("borde_fuerte"), 1, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        p.translate(0, (1 - tip) * motion.desp(4))   # el tooltip entra con un desplazamiento mínimo
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
        p.restore()

    def _pintar_carga(self, p: QPainter) -> None:
        """Esqueleto de la gráfica mientras llegan los primeros datos: rejilla y una curva fantasma con shimmer."""
        plot = self._plot()
        for k in range(3):
            y = plot.bottom() - plot.height() * k / 2
            p.setPen(QPen(col("grid"), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        base = mezclar(col("tarjeta_alt"), col("texto_suave"), 0.14)
        brillo = mezclar(col("tarjeta_alt"), col("texto"), 0.30)
        gx = plot.left() - 200 + (plot.width() + 400) * self._brillo if motion.decorativo() else -1000
        g = QLinearGradient(gx, 0, gx + 200, 0)
        g.setColorAt(0.0, base)
        g.setColorAt(0.5, brillo)
        g.setColorAt(1.0, base)
        pts = [QPointF(plot.left() + plot.width() * k / 8,
                       plot.bottom() - plot.height() * (0.40 + 0.15 * math.sin(k * 0.9 + 0.5))) for k in range(9)]
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(g, 3, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.drawPath(self._suave(pts, plot))

    def _pintar_vacio(self, p: QPainter) -> None:
        if self._cargando:
            self._pintar_carga(p)
            return
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
    """Fila ligera: sin rejilla, separador fino, hover suave, estado como píldora y acción como enlace. Pinta además
    la entrada escalonada, el éxito de una fila resuelta (check + verde) y el destello de una que sigue en error."""

    def paint(self, p: QPainter, opt, idx) -> None:
        tabla: TablaErrores = self.parent()
        fila, c = idx.row(), idx.column()
        rect = QRectF(opt.rect)
        ent, ok, flash = tabla.entrada(fila), tabla.exito(fila), tabla.destello(fila)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(max(0.0, (1.0 - tabla.desvanecido(fila)) * ent))
        if ent < 1.0:
            p.translate(0, (1.0 - ent) * motion.desp(7))
        if tabla.selectionModel() and tabla.selectionModel().isRowSelected(fila, idx.parent()):
            p.fillRect(rect, con_alfa(col("acento"), 0.13))
        elif fila == tabla.fila_hover:
            p.fillRect(rect, con_alfa(col("texto"), 0.045))
        if ok > 0:
            p.fillRect(rect, con_alfa(col("acento"), 0.13 * ok))
        if flash > 0:
            p.fillRect(rect, con_alfa(col("error"), 0.20 * flash))
        p.setPen(QPen(col("grid"), 1))
        p.drawLine(rect.bottomLeft(), rect.bottomRight())
        texto = str(idx.data(Qt.ItemDataRole.DisplayRole) or "")
        izq = rect.adjusted(14, 0, -8, 0)
        if c == COL_ESTADO and texto:
            etiqueta = i18n.t("Resuelta") if ok > 0.5 else texto
            p.setFont(_fuente(tabla.font(), 11, QFont.Weight.DemiBold))
            fm = QFontMetricsF(p.font())
            w = fm.horizontalAdvance(max(texto, i18n.t("Resuelta"), key=len)) + 26
            caja = QRectF(izq.left(), rect.center().y() - 11, min(w, izq.width()), 22)
            color = mezclar(col("error"), col("acento"), ok)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(con_alfa(color, 0.14))
            p.drawRoundedRect(caja, 11, 11)
            centro = QPointF(caja.left() + 11, caja.center().y())
            if ok > 0.01:     # el punto rojo se convierte en un check que se dibuja
                p.setPen(QPen(color, 1.8, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(ruta_parcial([QPointF(centro.x() - 3.6, centro.y() + 0.2), QPointF(centro.x() - 1.0, centro.y() + 2.8),
                                         QPointF(centro.x() + 3.8, centro.y() - 2.6)], min(1.0, ok * 1.6)))
            else:
                p.setBrush(color)
                p.drawEllipse(centro, 3, 3)
            p.setPen(color)
            p.drawText(caja.adjusted(21, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, etiqueta)
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


def _suave(v: float) -> float:
    v = max(0.0, min(1.0, v))
    return v * v * (3 - 2 * v)


class TablaErrores(QTableWidget):
    """``QTableWidget`` con aspecto ligero y movimiento por fila:

    * ``animar_entrada(filas)``: fade-in + entrada vertical mínima, escalonada (solo para filas nuevas).
    * ``desvanecer_filas(filas, al_terminar, exito=False)``: con ``exito`` la fila pasa a verde con un check que se
      dibuja y luego se desvanece; sin él solo se atenúa. Al terminar llama a ``al_terminar`` (reconstruye la tabla).
    * ``resaltar_filas(filas)``: destello rojo breve para lecturas que siguen con error tras reprocesar.
    """

    def __init__(self, columnas: int, parent: QWidget | None = None) -> None:
        super().__init__(0, columnas, parent)
        self.setObjectName("tablaSync")
        self.fila_hover = -1
        self._fade: dict[int, float] = {}
        self._ok: dict[int, float] = {}
        self._ent: dict[int, float] = {}
        self._flash: dict[int, float] = {}
        self._anim: QVariantAnimation | None = None
        self._anim_ent: QVariantAnimation | None = None
        self._anim_flash: QVariantAnimation | None = None
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

    def entrada(self, fila: int) -> float:
        return self._ent.get(fila, 1.0)

    def exito(self, fila: int) -> float:
        return self._ok.get(fila, 0.0)

    def destello(self, fila: int) -> float:
        return self._flash.get(fila, 0.0)

    def animar_entrada(self, filas: list[int]) -> None:
        """Entrada escalonada de las filas dadas (stagger corto: nada de movimientos bruscos)."""
        widgets._detener(self._anim_ent)
        if not filas or not widgets.ANIMAR:
            self._ent = {}
            return
        fila_ms, escalon = 280, 34
        total = fila_ms + escalon * min(len(filas), 12)
        self._ent = {f: 0.0 for f in filas}

        def paso(v: float) -> None:
            t = v * total
            for rango, f in enumerate(filas):
                self._ent[f] = _suave((t - escalon * min(rango, 12)) / fila_ms)
            self.viewport().update()

        def fin() -> None:
            self._ent = {}
            self.viewport().update()

        self._anim_ent = widgets.animar(self, 0.0, 1.0, motion.dur(total), paso, fin, QEasingCurve.Type.Linear)

    def desvanecer_filas(self, filas: list[int], al_terminar, exito: bool = False) -> None:
        """Marca (verde + check) y atenúa las filas dadas (0→1) y luego llama a ``al_terminar``."""
        if not filas or not widgets.ANIMAR:
            al_terminar()
            return
        widgets._detener(self._anim)

        def paso(v: float) -> None:
            if exito:
                self._ok = {f: _suave(v / 0.4) for f in filas}
                self._fade = {f: _suave((v - 0.58) / 0.42) for f in filas}
            else:
                self._fade = {f: v for f in filas}
            self.viewport().update()

        def fin() -> None:
            self._fade, self._ok = {}, {}
            al_terminar()

        self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(820 if exito else 320), paso, fin,
                                    QEasingCurve.Type.Linear if exito else QEasingCurve.Type.OutCubic)

    def resaltar_filas(self, filas: list[int]) -> None:
        """Destello rojo corto: la lectura sigue con error."""
        widgets._detener(self._anim_flash)
        if not filas or not widgets.ANIMAR:
            self._flash = {}
            return

        def paso(v: float) -> None:
            self._flash = {f: math.sin(math.pi * min(1.0, v * 1.0)) ** 0.8 for f in filas}
            self.viewport().update()

        def fin() -> None:
            self._flash = {}
            self.viewport().update()

        self._anim_flash = widgets.animar(self, 0.0, 1.0, motion.dur(760), paso, fin, QEasingCurve.Type.Linear)

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


# ------------------------------------------------------------------ esqueleto de carga
class Esqueleto(QWidget):
    """Filas fantasma con un shimmer discreto mientras llegan los primeros datos de Oracle (en lugar de un indicador
    genérico). El brillo es un único degradado que se desplaza; solo corre mientras el widget está visible."""

    PROPORCIONES = (0.15, 0.07, 0.17, 0.26, 0.17, 0.10)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fase = 0.0
        self._ciclo = ciclo(self, 1500, self._mover)
        self.setMinimumHeight(150)

    def _mover(self, v: float) -> None:
        self._fase = v
        self.update()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        _marcha(self._ciclo, motion.decorativo())

    def hideEvent(self, e) -> None:
        self._ciclo.stop()
        super().hideEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = mezclar(col("tarjeta_alt"), col("texto_suave"), 0.10)
        brillo = mezclar(col("tarjeta_alt"), col("texto"), 0.20)
        ancho = float(self.width())
        gx = -260 + (ancho + 520) * self._fase if motion.decorativo() else -1000
        g = QLinearGradient(gx, 0, gx + 260, 0)
        g.setColorAt(0.0, base)
        g.setColorAt(0.5, brillo)
        g.setColorAt(1.0, base)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        filas = max(2, int(self.height() // 46))
        for f in range(filas):
            y = f * 46 + 17
            x = 14.0
            for prop in self.PROPORCIONES:
                w = max(24.0, (ancho - 28) * prop - 16)
                p.drawRoundedRect(QRectF(x, y, w, 12), 6, 6)
                x += (ancho - 28) * prop


# ------------------------------------------------------------------ estado vacío
class _Marca(QWidget):
    """Círculo con check: el círculo se expande con un leve rebote, una onda se desvanece hacia fuera y el check se
    dibuja al final."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._t = 1.0
        self._anim: QVariantAnimation | None = None
        self.setFixedSize(96, 96)

    def animar(self) -> None:
        widgets._detener(self._anim)
        self._anim = widgets.animar(self, 0.0, 1.0, motion.dur(760), self._paso, None, QEasingCurve.Type.Linear)

    def _paso(self, v: float) -> None:
        self._t = v
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        verde = col("acento")
        t = self._t
        expansion = QEasingCurve(motion.curva_resorte(1.4))
        esc = 0.55 + 0.45 * expansion.valueForProgress(min(1.0, t / 0.55))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(con_alfa(verde, 0.14))
        p.drawEllipse(c, 40 * esc, 40 * esc)
        p.setBrush(con_alfa(verde, 0.22))
        p.drawEllipse(c, 29 * esc, 29 * esc)
        if 0.3 < t < 1.0 and motion.decorativo():     # onda que se desvanece hacia fuera
            f = (t - 0.3) / 0.7
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(con_alfa(verde, 0.35 * (1 - f)), 1.6))
            p.drawEllipse(c, 40 + 8 * f, 40 + 8 * f)
        trazo = ruta_parcial([QPointF(c.x() - 11, c.y() + 1), QPointF(c.x() - 3, c.y() + 9), QPointF(c.x() + 12, c.y() - 8)],
                             max(0.0, (t - 0.35) / 0.55))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(verde, 3.6, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.drawPath(trazo)


class EstadoVacio(QWidget):
    """«Todo está en orden»: marca con check animada y textos que entran con fade."""

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
        if not widgets.ANIMAR or not motion.sin_efecto_en_ancestros(self):
            return
        for k, etiqueta in enumerate((self.lbl_titulo, self.lbl_desc)):
            efecto, _ = motion.opacidad(etiqueta)
            efecto.setOpacity(0.0)

            def arrancar(w=etiqueta) -> None:
                if not sip.isdeleted(w):
                    motion.desvanecer(w, 0.0, 1.0, motion.dur(motion.Dur.ENTRADA))

            QTimer.singleShot(motion.dur(320) + 110 * k, arrancar)


# ------------------------------------------------------------------ entrada escalonada
def entrada_escalonada(piezas: list[QWidget], retardo_ms: int = 70, duracion_ms: int = 320) -> None:
    """Entrada de varias piezas, una tras otra (fade-in + desplazamiento vertical mínimo). Al terminar quita el efecto:
    no queda ningún filtro gráfico encendido. Sin animaciones no hace nada."""
    for i, w in enumerate(piezas):
        motion.entrar(w, retardo=i * retardo_ms, dy=10, ms_=duracion_ms)
