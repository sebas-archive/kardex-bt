"""La cápsula visual (NotificationWidget): se pinta a mano para que el tamaño, el contenido y la forma se animen
juntos sin parpadeos. Es un hijo de la ventana principal (no una ventana del sistema): no mueve nada del diseño.

Solo vive en el hilo de la interfaz. El dato (texto, tipo) queda fijado al instante; solo el dibujo se anima.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from .. import tema
from ..views import widgets
from .modelo import Notification, NotificationType

SOMBRA = 18          # margen del widget alrededor de la cápsula, donde se pinta la sombra
MARGEN_SUPERIOR = 14
ANCHO_MAX = 540
ANCHO_MIN = 190
RELLENO = 20
ICONO = 22
ESPACIO = 12
CIERRE = 22

COLOR_TIPO = {
    NotificationType.SUCCESS: "#34D399",
    NotificationType.ERROR: "#F87171",
    NotificationType.WARNING: "#FBBF24",
    NotificationType.INFO: "#60A5FA",
    NotificationType.LOADING: "#93C5FD",
}


def _tinte(c: str, a: float = 1.0) -> QColor:
    q = QColor(c)
    q.setAlphaF(max(0.0, min(1.0, a)))
    return q


def _acotar(x: float) -> float:
    return max(0.0, min(1.0, x))


class NotificationWidget(QWidget):
    """Cápsula tipo isla dinámica. ``presentar`` la abre, ``transformar`` cambia su contenido sin cerrarla y
    ``ocultar`` la contrae. ``oculta`` avisa cuando terminó de desaparecer (con el id que mostraba)."""

    oculta = pyqtSignal(int)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setObjectName("islaNotificacion")
        self.hide()
        self._noti: Notification | None = None
        self._viejo: tuple[NotificationType, str, str] | None = None   # contenido anterior (para fundir)
        self._dim_viejo = (ANCHO_MIN, 44)
        self._dim = (ANCHO_MIN, 44)          # (ancho, alto) de la cápsula del contenido actual
        self._p = 0.0                        # presencia 0..1 (0 = contraída y arriba, 1 = abierta)
        self._f = 1.0                        # fundido del contenido anterior al nuevo
        self._giro = 0.0
        self._encima = False
        self._cierre_visible = 0.0
        self._gen = 0
        self._saliendo = False
        self._anim_p: QVariantAnimation | None = None
        self._anim_f: QVariantAnimation | None = None
        self._anim_cierre: QVariantAnimation | None = None
        self._spinner = QVariantAnimation(self)
        self._spinner.setStartValue(0.0)
        self._spinner.setEndValue(360.0)
        self._spinner.setDuration(900)
        self._spinner.setLoopCount(-1)
        self._spinner.setEasingCurve(QEasingCurve.Type.Linear)
        self._spinner.valueChanged.connect(self._girar)
        self._vida = QTimer(self)
        self._vida.setTimerType(Qt.TimerType.PreciseTimer)
        self._vida.setSingleShot(True)
        self._vida.timeout.connect(self.ocultar)
        self._resta_ms = 0

    # ------------------------------------------------------------------ API
    @property
    def id_actual(self) -> int | None:
        return self._noti.id if self._noti is not None else None

    @property
    def activa(self) -> bool:
        return self._noti is not None

    @property
    def saliendo(self) -> bool:
        return self._saliendo

    @property
    def pausada(self) -> bool:
        return self._encima

    def texto(self) -> str:
        return self._noti.texto if self._noti is not None else ""

    def tiempo_restante_ms(self) -> int:
        return self._vida.remainingTime() if self._vida.isActive() else -1

    def presentar(self, noti: Notification) -> None:
        self._gen += 1
        self._saliendo = False
        self._noti = noti
        self._viejo = None
        self._f = 1.0
        self._dim = self._medir(noti.tipo, noti.texto, noti.detalle)
        self._p = 0.0
        self._poner_geometria()
        self._ajustar_spinner()
        self.show()
        self.raise_()
        self._animar_p(1.0, 360, QEasingCurve.Type.OutCubic)
        self._armar_vida(noti.duracion_ms)

    def transformar(self, noti: Notification) -> None:
        """Cambia el contenido de la cápsula abierta: se funde el contenido y el ancho se ajusta, sin cerrarla."""
        if self._noti is None or self._saliendo:
            return self.presentar(noti)
        anterior = self._noti
        self._viejo = (anterior.tipo, anterior.texto, anterior.detalle)
        self._dim_viejo = self._dim
        self._noti = noti
        self._dim = self._medir(noti.tipo, noti.texto, noti.detalle)
        self._f = 0.0
        self._ajustar_spinner()
        self._detener(self._anim_f)
        gen = self._gen
        self._anim_f = widgets.animar(self, 0.0, 1.0, 340, lambda v: self._set_f(v, gen),
                                      lambda: self._set_f(1.0, gen), QEasingCurve.Type.InOutCubic)
        if self._p < 1.0 and not self._saliendo:
            self._animar_p(1.0, 240, QEasingCurve.Type.OutCubic)
        self._armar_vida(noti.duracion_ms)
        self.update()

    def ocultar(self) -> None:
        if self._noti is None or self._saliendo:
            return
        self._saliendo = True
        self._vida.stop()
        self._gen += 1
        gen = self._gen
        self._animar_p(0.0, 300, QEasingCurve.Type.InOutCubic, lambda: self._terminar(gen))

    def cerrar_ya(self) -> None:
        """Sin animación (cierre de la ventana, pruebas): suelta todo."""
        self._gen += 1
        self._vida.stop()
        self._spinner.stop()
        for a in (self._anim_p, self._anim_f, self._anim_cierre):
            self._detener(a)
        self._saliendo = False
        self._noti = None
        self.hide()

    # ------------------------------------------------------------------ vida y hover
    def _armar_vida(self, ms: int | None) -> None:
        self._vida.stop()
        self._resta_ms = 0
        if ms is None:
            return
        if self._encima:
            self._resta_ms = ms
        else:
            self._vida.start(ms)

    def enterEvent(self, evento) -> None:
        self._encima = True
        if self._vida.isActive():
            self._resta_ms = self._vida.remainingTime()
            self._vida.stop()
        self._animar_cierre(1.0)
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._encima = False
        if self._resta_ms > 0 and self._noti is not None and not self._saliendo:
            self._vida.start(max(self._resta_ms, 1200))
        self._resta_ms = 0
        self._animar_cierre(0.0)
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and self._noti is not None:
            self.ocultar()
            evento.accept()
            return
        super().mousePressEvent(evento)

    def _animar_cierre(self, destino: float) -> None:
        self._detener(self._anim_cierre)
        self._anim_cierre = widgets.animar(self, self._cierre_visible, destino, 160, self._set_cierre)

    def _set_cierre(self, v: float) -> None:
        self._cierre_visible = v
        self.update()

    # ------------------------------------------------------------------ animaciones
    @staticmethod
    def _detener(anim: QVariantAnimation | None) -> None:
        widgets._detener(anim)

    def _animar_p(self, destino: float, ms: int, curva, al_terminar=None) -> None:
        self._detener(self._anim_p)
        self._anim_p = widgets.animar(self, self._p, destino, ms, self._set_p, al_terminar, curva)

    def _set_p(self, v: float) -> None:
        self._p = v
        self._poner_geometria()
        self.update()

    def _set_f(self, v: float, gen: int) -> None:
        if gen != self._gen:
            return
        self._f = v
        self._poner_geometria()
        self.update()

    def _girar(self, v) -> None:
        self._giro = float(v)
        self.update()

    def _ajustar_spinner(self) -> None:
        necesita = self._noti is not None and NotificationType.LOADING in (
            self._noti.tipo, self._viejo[0] if self._viejo else None)
        if necesita and widgets.ANIMAR:
            if self._spinner.state() != QVariantAnimation.State.Running:
                self._spinner.start()
        else:
            self._spinner.stop()

    def _terminar(self, gen: int) -> None:
        if gen != self._gen or self._noti is None:
            return
        id_ = self._noti.id
        self._spinner.stop()
        self._noti = None
        self._saliendo = False
        self.hide()
        self.oculta.emit(id_)

    # ------------------------------------------------------------------ medidas y geometría
    def _fuentes(self) -> tuple[QFont, QFont]:
        base = QFont(self.font())
        base.setPointSizeF(max(base.pointSizeF(), 10.0) + 0.5)
        base.setWeight(QFont.Weight.DemiBold)
        pequena = QFont(self.font())
        pequena.setPointSizeF(max(pequena.pointSizeF(), 10.0) - 1.0)
        return base, pequena

    def _ancho_maximo(self) -> int:
        padre = self.parentWidget()
        disponible = (padre.width() if padre is not None else ANCHO_MAX) - 2 * (SOMBRA + 16)
        return max(ANCHO_MIN, min(ANCHO_MAX, disponible))

    def _rect_texto_ancho(self) -> int:
        return self._ancho_maximo() - 2 * RELLENO - ICONO - ESPACIO - CIERRE - ESPACIO

    def _medir(self, tipo: NotificationType, texto: str, detalle: str) -> tuple[int, int]:
        fuente, pequena = self._fuentes()
        ancho_texto = self._rect_texto_ancho()
        fm, fp = QFontMetrics(fuente), QFontMetrics(pequena)
        caja = fm.boundingRect(0, 0, ancho_texto, 1000, int(Qt.TextFlag.TextWordWrap), texto)
        lineas_alto = min(caja.height(), fm.lineSpacing() * 2)
        ancho = caja.width()
        alto_texto = lineas_alto
        if detalle:
            caja_d = fp.boundingRect(0, 0, ancho_texto, 1000, int(Qt.TextFlag.TextWordWrap), detalle)
            alto_texto += min(caja_d.height(), fp.lineSpacing() * 2) + 2
            ancho = max(ancho, caja_d.width())
        w = RELLENO + ICONO + ESPACIO + ancho + ESPACIO + CIERRE + RELLENO - 6
        h = max(46, alto_texto + 24)
        return max(ANCHO_MIN, min(w, self._ancho_maximo())), h

    def _dim_visible(self) -> tuple[float, float]:
        if self._viejo is None or self._f >= 1.0:
            return float(self._dim[0]), float(self._dim[1])
        e = QEasingCurve(QEasingCurve.Type.InOutCubic).valueForProgress(self._f)
        return (self._dim_viejo[0] + (self._dim[0] - self._dim_viejo[0]) * e,
                self._dim_viejo[1] + (self._dim[1] - self._dim_viejo[1]) * e)

    def _poner_geometria(self) -> None:
        padre = self.parentWidget()
        if padre is None:
            return
        w, h = self._dim_visible()
        p = _acotar(self._p)
        # Contraída es una píldora pequeña; se estira al ancho del contenido al abrir.
        pildora = h
        ancho = pildora + (w - pildora) * p
        y = -(h + SOMBRA) + (MARGEN_SUPERIOR + h + SOMBRA - SOMBRA) * p
        x = (padre.width() - ancho) / 2 - SOMBRA
        self.setGeometry(round(x), round(y - 0), round(ancho + 2 * SOMBRA), round(h + 2 * SOMBRA))

    def recentrar(self) -> None:
        if self._noti is not None:
            self._dim = self._medir(self._noti.tipo, self._noti.texto, self._noti.detalle)
            self._poner_geometria()
            self.update()

    # ------------------------------------------------------------------ pintura
    def _colores(self) -> tuple[QColor, QColor, QColor]:
        oscuro = tema.es_oscuro()
        fondo = QColor("#0B1220") if oscuro else QColor("#111827")
        borde = QColor(255, 255, 255, 34) if oscuro else QColor(255, 255, 255, 18)
        texto = QColor("#FFFFFF")
        return fondo, borde, texto

    def paintEvent(self, _evento) -> None:
        if self._noti is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        capsula = QRectF(self.rect()).adjusted(SOMBRA, SOMBRA, -SOMBRA, -SOMBRA)
        if capsula.width() < 4 or capsula.height() < 4:
            return
        radio = capsula.height() / 2
        presencia = _acotar(self._p)
        fondo, borde, texto = self._colores()

        # sombra suave: capas translúcidas cada vez más grandes
        for i in range(SOMBRA - 4, 0, -2):
            a = int(26 * presencia * (1 - i / SOMBRA) ** 2)
            if a <= 0:
                continue
            ruta = QPainterPath()
            r = capsula.adjusted(-i, -i + 4, i, i + 4)
            ruta.addRoundedRect(r, radio + i, radio + i)
            p.fillPath(ruta, QColor(0, 0, 0, a))
        ruta = QPainterPath()
        ruta.addRoundedRect(capsula, radio, radio)
        p.fillPath(ruta, fondo)
        p.setPen(QPen(borde, 1))
        p.drawPath(ruta)

        # contenido: aparece al final de la apertura y desaparece al principio del cierre
        opacidad = _acotar((presencia - 0.45) / 0.55)
        if opacidad <= 0:
            return
        p.setClipPath(ruta)
        if self._viejo is not None and self._f < 1.0:
            op_viejo = _acotar(1 - self._f * 2.2) * opacidad
            op_nuevo = _acotar((self._f - 0.35) / 0.65) * opacidad
            tipo, txt, det = self._viejo
            self._dibujar(p, capsula, tipo, txt, det, op_viejo, texto, desplaza=-6 * self._f)
            self._dibujar(p, capsula, self._noti.tipo, self._noti.texto, self._noti.detalle, op_nuevo, texto,
                          desplaza=6 * (1 - self._f))
        else:
            self._dibujar(p, capsula, self._noti.tipo, self._noti.texto, self._noti.detalle, opacidad, texto)
        p.end()

    def _dibujar(self, p: QPainter, capsula: QRectF, tipo: NotificationType, texto: str, detalle: str,
                 opacidad: float, color_texto: QColor, desplaza: float = 0.0) -> None:
        if opacidad <= 0:
            return
        p.save()
        p.setOpacity(opacidad)
        fuente, pequena = self._fuentes()
        # icono (escala un poco al entrar)
        escala = 0.6 + 0.4 * _acotar((self._p - 0.5) / 0.5)
        centro = QPointF(capsula.left() + RELLENO + ICONO / 2, capsula.center().y())
        p.save()
        p.translate(centro)
        p.scale(escala, escala)
        self._icono(p, tipo)
        p.restore()
        # texto
        x = capsula.left() + RELLENO + ICONO + ESPACIO + desplaza + (1 - opacidad) * 8
        ancho = capsula.width() - (x - capsula.left()) - ESPACIO - CIERRE - 6
        fm, fp = QFontMetrics(fuente), QFontMetrics(pequena)
        alto_t = min(fm.boundingRect(0, 0, int(ancho), 1000, int(Qt.TextFlag.TextWordWrap), texto).height(),
                     fm.lineSpacing() * 2)
        alto_d = 0
        if detalle:
            alto_d = min(fp.boundingRect(0, 0, int(ancho), 1000, int(Qt.TextFlag.TextWordWrap), detalle).height(),
                         fp.lineSpacing() * 2) + 2
        y = capsula.center().y() - (alto_t + alto_d) / 2
        p.setPen(color_texto)
        p.setFont(fuente)
        p.drawText(QRectF(x, y, ancho, alto_t), int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignVCenter), texto)
        if detalle:
            p.setPen(_tinte("#FFFFFF", 0.62))
            p.setFont(pequena)
            p.drawText(QRectF(x, y + alto_t + 2, ancho, alto_d), int(Qt.TextFlag.TextWordWrap), detalle)
        p.restore()
        # botón de cerrar (solo al pasar el cursor)
        if self._cierre_visible > 0.01 and opacidad > 0.5:
            p.save()
            p.setOpacity(opacidad * self._cierre_visible * 0.8)
            c = QPointF(capsula.right() - RELLENO + 2, capsula.center().y())
            p.setPen(QPen(_tinte("#FFFFFF", 0.9), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            d = 4.5
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() - d, c.y() + d), QPointF(c.x() + d, c.y() - d))
            p.restore()

    def _icono(self, p: QPainter, tipo: NotificationType) -> None:
        color = _tinte(COLOR_TIPO[tipo])
        r = ICONO / 2 - 1
        trazo = QPen(color, 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        if tipo is NotificationType.LOADING:
            p.setPen(QPen(_tinte(COLOR_TIPO[tipo], 0.25), 2.4))
            p.drawEllipse(QPointF(0, 0), r - 1.5, r - 1.5)
            p.setPen(QPen(color, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            caja = QRectF(-(r - 1.5), -(r - 1.5), 2 * (r - 1.5), 2 * (r - 1.5))
            p.drawArc(caja, int(-self._giro * 16), 100 * 16)
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_tinte(COLOR_TIPO[tipo], 0.18))
        p.drawEllipse(QPointF(0, 0), r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(trazo)
        if tipo is NotificationType.SUCCESS:
            ruta = QPainterPath()
            ruta.moveTo(-4.5, 0.5)
            ruta.lineTo(-1.2, 3.8)
            ruta.lineTo(4.8, -3.2)
            p.drawPath(ruta)
        elif tipo is NotificationType.ERROR:
            p.drawLine(QPointF(-3.6, -3.6), QPointF(3.6, 3.6))
            p.drawLine(QPointF(-3.6, 3.6), QPointF(3.6, -3.6))
        elif tipo is NotificationType.WARNING:
            p.drawLine(QPointF(0, -4.6), QPointF(0, 1.4))
            p.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPoint(QPointF(0, 4.6))
        else:   # INFO
            p.drawLine(QPointF(0, -0.8), QPointF(0, 4.8))
            p.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPoint(QPointF(0, -4.6))
