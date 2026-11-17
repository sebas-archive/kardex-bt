"""Movimiento, scroll y feedback de la capa de interactividad.

Todo pasa por ``widgets.animar`` y respeta ``APP_SIN_ANIMACIONES=1`` (las pruebas y las capturas): el dato y el
estado final nunca dependen de una animación. Los tiempos siguen la regla del encargo: feedback < 100 ms, transiciones
de 150–300 ms, nada bloquea más de 500 ms.
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable

from PyQt6.QtCore import QAbstractAnimation, QEasingCurve, QEvent, QObject, QPointF, QRectF, Qt, QTimer, QVariantAnimation
from PyQt6 import sip
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QGraphicsDropShadowEffect,
    QGraphicsEffect,
    QGraphicsOpacityEffect,
    QLayout,
    QTableView,
    QTableWidget,
    QWidget,
)

from . import widgets

# Tokens de movimiento (ms) y curva por defecto.
RAPIDO, NORMAL, LENTO = 120, 200, 320
CURVA = QEasingCurve.Type.OutCubic
CURVA_SUAVE = QEasingCurve.Type.OutQuint
VERDE = "#10B981"
SOMBRA = "#0F172A"   # sombra de elevación (hover, arrastre): neutra, sin tinte de color
TINTA_SUAVE = "#8A8A8A"


def animar(dueno: QObject, inicio: float, fin: float, ms: int, paso: Callable[[float], None],
           fin_cb: Callable[[], None] | None = None,
           curva: QEasingCurve.Type | QEasingCurve = CURVA) -> QVariantAnimation | None:
    """Atajo de ``widgets.animar`` con los tokens de esta capa."""
    return widgets.animar(dueno, inicio, fin, ms, paso, fin_cb, curva)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- sistema de movimiento (Apple-like)
# Duraciones por naturaleza de la interacción: no todo dura lo mismo (hover ≪ entrada < pantalla < gráfica).
class Dur:
    HOVER, PRESION = 150, 130
    ENTRADA, SALIDA = 360, 240
    ESTADO, PANTALLA = 320, 420
    EXPANSION, GRAFICA = 440, 560


def curva_resorte(sobre: float = 1.15) -> QEasingCurve:
    """Ease-out con un rebasamiento muy sutil (spring-like) para expansión y recuperación tras una pulsación."""
    c = QEasingCurve(QEasingCurve.Type.OutBack)
    c.setOvershoot(sobre)
    return c


_reducido: bool | None = None


def reducido() -> bool:
    """Preferencia de movimiento reducido (``APP_MOVIMIENTO_REDUCIDO=1`` o «animaciones» apagadas en GNOME).

    Con ella activa se omiten partículas, ciclos continuos y desplazamientos grandes; las transiciones esenciales
    (color, opacidad, estado) siguen, más cortas. Se consulta una sola vez."""
    global _reducido
    if _reducido is None:
        forzado = os.environ.get("APP_MOVIMIENTO_REDUCIDO")
        if forzado is not None:
            _reducido = forzado == "1"
        else:
            try:
                r = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "enable-animations"],
                                   capture_output=True, text=True, timeout=0.6)
                _reducido = r.returncode == 0 and r.stdout.strip() == "false"
            except Exception:  # sin gsettings (otro escritorio, contenedor): se asume movimiento normal
                _reducido = False
    return _reducido


def fijar_reducido(valor: bool | None) -> None:
    """Fuerza (o, con ``None``, vuelve a consultar) la preferencia; lo usan las pruebas."""
    global _reducido
    _reducido = valor


def dur(base: int) -> int:
    """Duración efectiva: en movimiento reducido las transiciones esenciales se acortan."""
    return min(base, 160) if reducido() else base


def desp(distancia: float) -> float:
    """Desplazamiento efectivo: en movimiento reducido casi no hay recorrido."""
    return distancia * 0.2 if reducido() else distancia


def decorativo() -> bool:
    """¿Se permiten efectos decorativos y ciclos continuos (partículas, ondas, respiración)?"""
    return widgets.ANIMAR and not reducido()


def sin_efecto_en_ancestros(widget: QWidget) -> bool:
    """Qt dibuja mal efectos gráficos anidados: antes de fundir un hijo se comprueba que ningún padre tenga uno."""
    p = widget.parentWidget()
    while p is not None:
        if p.graphicsEffect() is not None:
            return False
        p = p.parentWidget()
    return True


# Canales de EfectoMovimiento: quién escribe en cada uno.
ENTRADA_C, HOVER_C, ARRASTRE_C = 0, 1, 2     # entrada/salida · hover y pulsación · levantar/asentar al arrastrar
CANALES = 3


class EfectoMovimiento(QGraphicsEffect):
    """Un único efecto reutilizable para entrada, hover y pulsación de una tarjeta: opacidad, desplazamiento vertical,
    escala alrededor del centro y una sombra ambiental suave (capas de rectángulos, sin desenfoque costoso).

    Se instala solo mientras hace falta y se quita al volver al reposo, de modo que una tarjeta quieta no paga nada.
    """

    PAD = 30

    def __init__(self, padre: QWidget, radio: float = 16, color: str = SOMBRA) -> None:
        super().__init__(padre)
        # Canales independientes: cada capa de movimiento escribe en el suyo y el dibujo los combina, de modo que dos
        # animaciones (entrada + hover, hover + arrastre) nunca compiten por la misma propiedad.
        self._op = 1.0
        self._dys = [0.0] * CANALES
        self._escs = [1.0] * CANALES
        self._sombras = [0.0] * CANALES
        self._radio = radio
        self._color = QColor(color)

    def opacidad(self) -> float:
        return self._op

    def set_opacidad(self, v: float) -> None:
        self._op = max(0.0, min(1.0, v))
        self.update()

    @property
    def _dy(self) -> float:
        return sum(self._dys)

    @property
    def _esc(self) -> float:
        total = 1.0
        for e in self._escs:
            total *= e
        return total

    @property
    def _sombra(self) -> float:
        return max(self._sombras)

    def set_dy(self, v: float, canal: int = ENTRADA_C) -> None:
        self._dys[canal] = v
        self.update()

    def set_escala(self, v: float, canal: int = ENTRADA_C) -> None:
        self._escs[canal] = v
        self.update()

    def sombra(self) -> float:
        return self._sombra

    def set_sombra(self, v: float, canal: int = ENTRADA_C) -> None:
        self._sombras[canal] = max(0.0, v)
        self.update()

    def en_reposo(self) -> bool:
        return (self._op >= 1.0 and all(abs(d) < 0.01 for d in self._dys)
                and all(abs(e - 1.0) < 0.0005 for e in self._escs) and all(s <= 0.001 for s in self._sombras))

    def boundingRectFor(self, rect: QRectF) -> QRectF:
        return rect.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD + 10)

    def draw(self, painter: QPainter) -> None:
        pix, off = self.sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates, QGraphicsEffect.PixmapPadMode.NoPad)
        if pix.isNull():
            return
        tam = pix.deviceIndependentSize()
        r = QRectF(off.x(), off.y(), tam.width(), tam.height())
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = r.center()
        painter.translate(c.x(), c.y() + self._dy)
        painter.scale(self._esc, self._esc)
        painter.translate(-c.x(), -c.y())
        painter.setOpacity(self._op)
        if self._sombra > 0.001:
            painter.setPen(Qt.PenStyle.NoPen)
            capas = 7
            for k in range(capas, 0, -1):      # de fuera hacia dentro: el centro de la sombra queda más denso
                crece = k * 2.6
                tono = QColor(self._color)
                tono.setAlphaF(min(1.0, self._sombra * 0.06 * (1 - (k - 1) / capas)))
                painter.setBrush(tono)
                painter.drawRoundedRect(r.adjusted(-crece, -crece + 6, crece, crece + 6), self._radio + crece,
                                        self._radio + crece)
        painter.drawPixmap(r.topLeft(), pix)
        painter.restore()


def efecto_movimiento(widget: QWidget, radio: float = 16, color: str = SOMBRA) -> EfectoMovimiento:
    """El efecto de movimiento del widget (lo crea si no hay ninguno; si hay otro tipo de efecto lo reemplaza)."""
    actual = widget.graphicsEffect()
    if isinstance(actual, EfectoMovimiento):
        return actual
    efecto = EfectoMovimiento(widget, radio, color)
    widget.setGraphicsEffect(efecto)
    return efecto


def soltar_efecto(widget: QWidget, efecto: QGraphicsEffect, forzar: bool = False) -> None:
    """Quita el efecto del widget. Un ``EfectoMovimiento`` que otra capa aún usa (hover, arrastre) se conserva."""
    if sip.isdeleted(widget) or sip.isdeleted(efecto) or widget.graphicsEffect() is not efecto:
        return
    if not forzar and isinstance(efecto, EfectoMovimiento) and not efecto.en_reposo():
        return
    widget.setGraphicsEffect(None)


def entrar(widget: QWidget, retardo: int = 0, dy: float = 14, escala: float = 1.0, ms_: int = Dur.ENTRADA,
           radio: float = 16, al_terminar: Callable[[], None] | None = None) -> None:
    """Entrada de un widget: fade-in + desplazamiento vertical (y expansión si ``escala`` < 1) tras ``retardo`` ms.

    Quita el efecto al terminar y es seguro si el widget se destruye (la vista se reconstruye con el tema/idioma)."""
    if not widgets.ANIMAR:
        return
    dy, ms_ = desp(dy), dur(ms_)
    detener(getattr(widget, "_entrada_anim", None))        # re-entrante: volver a la pantalla reemplaza la entrada previa
    token = object()
    widget._entrada_tok = token                              # type: ignore[attr-defined]
    efecto = efecto_movimiento(widget, radio)
    efecto.set_opacidad(0.0)
    efecto.set_dy(dy)
    efecto.set_escala(escala)

    def paso(v: float) -> None:
        if sip.isdeleted(efecto):
            return
        efecto.set_opacidad(min(1.0, v * 1.6))
        efecto.set_dy(dy * (1 - v))
        efecto.set_escala(escala + (1.0 - escala) * v)

    def fin() -> None:
        if getattr(widget, "_entrada_tok", None) is not token:
            return
        soltar_efecto(widget, efecto)
        if al_terminar is not None:
            al_terminar()

    def arrancar() -> None:
        if sip.isdeleted(widget) or getattr(widget, "_entrada_tok", None) is not token:
            return
        if not widget.isVisible():                           # se salió de la pantalla antes de que le tocara: no se anima
            efecto.set_opacidad(1.0)
            efecto.set_dy(0.0)
            efecto.set_escala(1.0)
            soltar_efecto(widget, efecto)
            return
        curva = curva_resorte(1.05) if escala < 1.0 else QEasingCurve.Type.OutCubic
        widget._entrada_anim = animar(widget, 0.0, 1.0, ms_, paso, fin, curva)   # type: ignore[attr-defined]

    if retardo > 0:
        QTimer.singleShot(retardo, arrancar)
    else:
        arrancar()


def preparar_entrada(widget: QWidget, radio: float = 16) -> None:
    """Deja un widget invisible (opacidad 0) a la espera de su ``entrar``: lo usan las baldosas que están fuera de la
    pantalla y se revelan al desplazarse. Sin animaciones no hace nada (el widget ya está en su estado final)."""
    if not widgets.ANIMAR:
        return
    efecto_movimiento(widget, radio).set_opacidad(0.0)


def cancelar_entrada(widget: QWidget) -> None:
    """Aborta una entrada pendiente o en curso y deja el widget en su estado final (sin efecto, sin opacidad parcial)."""
    detener(getattr(widget, "_entrada_anim", None))
    widget._entrada_tok = None                               # type: ignore[attr-defined]
    efecto = widget.graphicsEffect()
    if isinstance(efecto, EfectoMovimiento):
        efecto.set_opacidad(1.0)
        efecto.set_dy(0.0)
        efecto.set_escala(1.0)
        soltar_efecto(widget, efecto)


def salir(widget: QWidget, ms_: int = Dur.SALIDA - 60, dy: float = 0.0, escala: float = 0.96, radio: float = 16,
          al_terminar: Callable[[], None] | None = None) -> None:
    """Salida de un widget: se funde y se encoge un poco antes de desaparecer. Sin animaciones, ``al_terminar`` ya."""
    if not widgets.ANIMAR or not widget.isVisible():
        if al_terminar is not None:
            al_terminar()
        return
    ms_, dy = dur(ms_), desp(dy)
    detener(getattr(widget, "_entrada_anim", None))
    token = object()
    widget._entrada_tok = token                              # type: ignore[attr-defined]
    efecto = efecto_movimiento(widget, radio)
    op0, esc0 = efecto.opacidad(), efecto._escs[ENTRADA_C]

    def paso(v: float) -> None:
        if sip.isdeleted(efecto):
            return
        efecto.set_opacidad(op0 * (1 - v))
        efecto.set_dy(dy * v)
        efecto.set_escala(esc0 + (escala - esc0) * v)

    def fin() -> None:
        if getattr(widget, "_entrada_tok", None) is token and al_terminar is not None:
            al_terminar()

    widget._entrada_anim = animar(widget, 0.0, 1.0, ms_, paso, fin, QEasingCurve.Type.InCubic)   # type: ignore[attr-defined]


class InteraccionTarjeta(QObject):
    """Hover y pulsación de una tarjeta, sin mover el layout: elevación ligera con sombra ambiental, compresión al
    pulsar y recuperación tipo spring. El efecto solo existe mientras hay movimiento o el cursor está encima."""

    def __init__(self, tarjeta: QWidget, radio: float = 14, color: str = SOMBRA, elevacion: float = 3.0,
                 destino: QWidget | None = None) -> None:
        """``destino``: el widget que lleva el efecto (por defecto, la propia tarjeta). Una tarjeta dentro de una baldosa
        deja el efecto a la baldosa: así entrada, hover y arrastre comparten un único ``EfectoMovimiento``."""
        super().__init__(tarjeta)
        self._t, self._radio, self._color, self._elev = tarjeta, radio, color, elevacion
        self._d = destino if destino is not None else tarjeta
        self._dentro = False
        self._hover = 0.0
        self._pulso = 0.0
        self._a_hover: QVariantAnimation | None = None
        self._a_pulso: QVariantAnimation | None = None
        tarjeta.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        tarjeta.installEventFilter(self)

    def _efecto(self) -> EfectoMovimiento | None:
        actual = self._d.graphicsEffect()
        if actual is None:
            return efecto_movimiento(self._d, self._radio, self._color)
        return actual if isinstance(actual, EfectoMovimiento) else None   # hay otro efecto en curso: no se pisa

    def _aplicar(self) -> None:
        if sip.isdeleted(self._d):
            return
        efecto = self._efecto()
        if efecto is None:
            return
        if not self._dentro and self._hover <= 0.001 and self._pulso <= 0.001:
            efecto.set_dy(0.0, HOVER_C)
            efecto.set_escala(1.0, HOVER_C)
            efecto.set_sombra(0.0, HOVER_C)
            soltar_efecto(self._d, efecto)               # solo si ninguna otra capa (entrada, arrastre) lo usa
            return
        efecto.set_dy(-self._elev * self._hover, HOVER_C)
        efecto.set_escala(1.0 - 0.018 * self._pulso, HOVER_C)    # sin escala en reposo: el texto no se re-muestrea
        efecto.set_sombra(self._hover, HOVER_C)

    def _hover_a(self, destino: float) -> None:
        detener(self._a_hover)
        self._a_hover = animar(self._t, self._hover, destino, Dur.HOVER + 40, self._paso_hover)

    def _paso_hover(self, v: float) -> None:
        self._hover = v
        self._aplicar()

    def _pulso_a(self, destino: float, ms_: int, curva) -> None:
        detener(self._a_pulso)
        self._a_pulso = animar(self._t, self._pulso, destino, ms_, self._paso_pulso, None, curva)

    def _paso_pulso(self, v: float) -> None:
        self._pulso = v
        self._aplicar()

    def eventFilter(self, objeto, evento) -> bool:
        if not widgets.ANIMAR:
            return False
        tipo = evento.type()
        if tipo in (QEvent.Type.HoverEnter, QEvent.Type.Enter):
            if not self._dentro:
                self._dentro = True
                self._hover_a(1.0)
        elif tipo in (QEvent.Type.HoverLeave, QEvent.Type.Leave):
            if self._dentro:
                self._dentro = False
                self._hover_a(0.0)
        elif tipo == QEvent.Type.MouseButtonPress:
            self._pulso_a(1.0, dur(Dur.PRESION), QEasingCurve.Type.OutCubic)
        elif tipo == QEvent.Type.MouseButtonRelease:
            self._pulso_a(0.0, dur(Dur.ESTADO), curva_resorte(1.9))
        return False


def hacer_interactiva(tarjeta: QWidget, radio: float = 14, color: str = SOMBRA,
                      destino: QWidget | None = None) -> InteraccionTarjeta:
    """Instala (una sola vez) el hover/pulsación premium en una tarjeta (el efecto puede vivir en ``destino``)."""
    previa = getattr(tarjeta, "_interaccion", None)
    if previa is not None:
        return previa
    tarjeta._interaccion = InteraccionTarjeta(tarjeta, radio, color, destino=destino)  # type: ignore[attr-defined]
    return tarjeta._interaccion  # type: ignore[attr-defined]


def cruzar_texto(etiqueta, texto: str, ms_: int = Dur.ESTADO) -> None:
    """Cross-fade del texto de una etiqueta: sale (rápido), se cambia y entra. Sin cambio de texto no hace nada.

    Si la etiqueta no es visible, o un ancestro ya lleva un efecto gráfico, el texto cambia al instante."""
    if etiqueta.text() == texto:
        return
    if not widgets.ANIMAR or not etiqueta.isVisible() or not sin_efecto_en_ancestros(etiqueta):
        etiqueta.setText(texto)
        return
    detener(getattr(etiqueta, "_cruce", None))
    total = dur(ms_)
    mitad = max(60, total // 3)

    def entra() -> None:
        if sip.isdeleted(etiqueta):
            return
        etiqueta.setText(texto)
        etiqueta._cruce = desvanecer(etiqueta, 0.0, 1.0, total - mitad)

    etiqueta._cruce = desvanecer(etiqueta, 1.0, 0.0, mitad, entra)


def detener(anim: QVariantAnimation | None) -> None:
    widgets._detener(anim)


def opacidad(widget: QWidget) -> tuple[QGraphicsOpacityEffect, bool]:
    """Efecto de opacidad reutilizable (Qt solo admite uno por widget)."""
    efecto = widget.graphicsEffect()
    if isinstance(efecto, QGraphicsOpacityEffect):
        return efecto, False
    efecto = QGraphicsOpacityEffect(widget)
    efecto.setOpacity(1.0)
    widget.setGraphicsEffect(efecto)
    return efecto, True


def desvanecer(widget: QWidget, desde: float, hasta: float, ms: int = NORMAL,
               fin_cb: Callable[[], None] | None = None) -> QVariantAnimation | None:
    """Funde un widget entre dos opacidades (sin tocar su visibilidad).

    Un fundido que termina en opacidad plena quita su efecto: dejarlo puesto anidaba efectos con los de los hijos
    (p. ej. las cifras de una tarjeta KPI) y Qt los dibujaba en blanco.
    """
    # Un fundido nuevo sobre el mismo widget sustituye al anterior: sin esto, el primero al terminar borraba el efecto
    # mientras el segundo aún lo usaba («wrapped C/C++ object … has been deleted»).
    detener(getattr(widget, "_fundido", None))
    token = object()
    widget._fundido_token = token   # type: ignore[attr-defined]
    efecto, _ = opacidad(widget)
    efecto.setOpacity(desde)

    def paso(v: float) -> None:
        if not sip.isdeleted(efecto):
            efecto.setOpacity(v)

    def fin() -> None:
        if getattr(widget, "_fundido_token", None) is not token:   # lo reemplazó otro fundido: él se encarga
            return
        if hasta >= 1.0 and not sip.isdeleted(widget) and widget.graphicsEffect() is efecto:
            widget.setGraphicsEffect(None)
        if fin_cb is not None:
            fin_cb()

    anim = animar(widget, desde, hasta, ms, paso, fin)
    widget._fundido = anim   # type: ignore[attr-defined]
    return anim


def sombra(widget: QWidget, color: str = "#000000", blur: int = 0, dy: int = 0, alpha: int = 0) -> QGraphicsDropShadowEffect:
    """Sombra elevada; se crea perezosamente para no pagar el costo en widgets que nunca se tocan."""
    efecto = widget.graphicsEffect()
    if not isinstance(efecto, QGraphicsDropShadowEffect):
        efecto = QGraphicsDropShadowEffect(widget)
        efecto.setOffset(0, dy)
        efecto.setBlurRadius(blur)
        tono = QColor(color)
        tono.setAlpha(alpha)
        efecto.setColor(tono)
        widget.setGraphicsEffect(efecto)
    return efecto


def elevar(widget: QWidget, activo: bool, ms: int = NORMAL, color: str = SOMBRA) -> QVariantAnimation | None:
    """Hover de tarjeta: borde con glow (QSS) + sombra que crece y se tiñe del color primario."""
    efecto = sombra(widget, color, 0, 0, 0)
    if not widgets.ANIMAR:
        efecto.setBlurRadius(26 if activo else 0)
        efecto.setOffset(0, 6 if activo else 0)
        tono = QColor(color)
        tono.setAlpha(110 if activo else 0)
        efecto.setColor(tono)
        return None

    def paso(v: float) -> None:
        efecto.setBlurRadius(26 * v)
        efecto.setOffset(0, 7 * v)
        tono = QColor(color)
        tono.setAlpha(int(120 * v))
        efecto.setColor(tono)

    inicio = efecto.blurRadius() / 26 if efecto.blurRadius() else 0.0
    return animar(widget, inicio, 1.0 if activo else 0.0, ms, paso, curva=CURVA)


def sacudir(contenedor: QWidget, amplitud: int = 7, ms: int = 330) -> None:
    """Sacudida corta de un contenedor con layout (error de validación, confirmación bloqueada)."""
    lay = contenedor.layout()
    if lay is None or not widgets.ANIMAR:
        return
    base = lay.contentsMargins()
    if not hasattr(contenedor, "_sacudida"):
        contenedor._sacudida = None  # type: ignore[attr-defined]
    detener(getattr(contenedor, "_sacudida", None))

    def paso(v: float) -> None:
        lay.setContentsMargins(base.left() + int(v), base.top(), base.right() - int(v), base.bottom())

    # 0 → +a → −a → +a/2 → 0
    pasos = [0.0, 1.0, -1.0, 0.45, 0.0]
    grupo = QVariantAnimation(contenedor)
    grupo.setStartValue(0.0)
    grupo.setEndValue(float(len(pasos) - 1))
    grupo.setDuration(ms)
    grupo.setEasingCurve(QEasingCurve.Type.Linear)

    def cambiar(v: float) -> None:
        i = min(int(v), len(pasos) - 2)
        f = v - i
        paso(pasos[i] + (pasos[i + 1] - pasos[i]) * f)

    grupo.valueChanged.connect(cambiar)
    grupo.finished.connect(lambda: lay.setContentsMargins(base))
    grupo.finished.connect(grupo.deleteLater)
    contenedor._sacudida = grupo  # type: ignore[attr-defined]
    grupo.start()


def destello(widget: QWidget, color: str = VERDE, ms: int = 420) -> None:
    """Flash breve sobre el área copiada / el destino de un drop."""
    objetivo = widget.viewport() if isinstance(widget, QAbstractScrollArea) else widget
    capa = QWidget(objetivo)
    capa.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    capa.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    capa.setStyleSheet(f"background: rgba({_rgb(color)}, 0.28); border-radius: 6px;")
    capa.setGeometry(objetivo.rect())
    capa.show()
    capa.raise_()
    efecto, _ = opacidad(capa)
    efecto.setOpacity(0.9)
    animar(capa, 0.9, 0.0, ms, efecto.setOpacity, capa.deleteLater, QEasingCurve.Type.OutCubic)


def _rgb(color: str) -> str:
    tono = QColor(color)
    return f"{tono.red()}, {tono.green()}, {tono.blue()}"


class ScrollSuave(QObject):
    """Rueda con inercia: cada gesto se convierte en una animación corta de la barra (no un salto por muesca).

    Se instala solo en áreas de datos (QScrollArea, tablas). Las gráficas de pyqtgraph tienen su propio zoom con la
    rueda y no se tocan.
    """

    def __init__(self, area: QAbstractScrollArea) -> None:
        super().__init__(area)
        self._area = area
        self._anims: dict[object, QVariantAnimation] = {}
        area.viewport().installEventFilter(self)
        area.viewport().setCursor(area.viewport().cursor())

    def _barra(self, vertical: bool):
        return self._area.verticalScrollBar() if vertical else self._area.horizontalScrollBar()

    def _mover(self, vertical: bool, delta: int) -> bool:
        barra = self._barra(vertical)
        if barra.maximum() <= barra.minimum():
            return False
        paso = max(1, barra.singleStep()) * 3
        objetivo = barra.value() - delta * paso / 120
        objetivo = max(barra.minimum(), min(barra.maximum(), objetivo))
        if abs(objetivo - barra.value()) < 1:
            return False
        detener(self._anims.get(barra))
        inicio = barra.value()
        self._anims[barra] = animar(self._area, inicio, objetivo, 190, lambda v: barra.setValue(int(round(v))),
                                    None, QEasingCurve.Type.OutCubic)
        return True

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.Wheel and widgets.ANIMAR:
            dy = evento.angleDelta().y() or evento.pixelDelta().y()
            dx = evento.angleDelta().x() or evento.pixelDelta().x()
            movido = False
            if dy:
                movido = self._mover(True, dy) or movido
            if dx:
                movido = self._mover(False, dx) or movido
            if movido:
                evento.accept()
                return True
        return super().eventFilter(objeto, evento)


def instalar_scroll_suave(area: QAbstractScrollArea) -> ScrollSuave | None:
    """Instala la rueda con inercia una sola vez por área."""
    if not isinstance(area, (QTableView, QTableWidget)) and type(area).__module__.startswith("pyqtgraph"):
        return None
    previo = area.findChild(ScrollSuave)
    if previo is not None:
        return previo
    return ScrollSuave(area)     # hijo Qt del área: vive y muere con ella (sin referencias cruzadas en Python)


class ProgresoScroll(QWidget):
    """Indicador vertical del borde derecho: cuánto se ha recorrido la lista activa."""

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedWidth(4)
        self._valor = 0
        self._minimo = 0
        self._maximo = 0
        self._pagina = 0
        self._visible = 0.0
        self._anim: QVariantAnimation | None = None
        self.hide()

    def set_rango(self, valor: int, minimo: int, maximo: int, pagina: int = 0) -> None:
        self._valor, self._minimo, self._maximo, self._pagina = valor, minimo, maximo, pagina
        hay = maximo > minimo
        if hay and self.isHidden():
            self.show()
            self.raise_()
        objetivo = 1.0 if hay else 0.0
        if abs(self._visible - objetivo) > 0.01:
            detener(self._anim)
            self._anim = animar(self, self._visible, objetivo, RAPIDO, self._fundir)
        self.update()

    def _fundir(self, v: float) -> None:
        self._visible = v
        self.setVisible(v > 0.02)
        self.update()

    def paintEvent(self, _evento) -> None:
        if self._visible <= 0.01 or self._maximo <= self._minimo:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        alto = self.height()
        pista = QColor("#2E2E2E")
        pista.setAlpha(int(90 * self._visible))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(pista)
        p.drawRoundedRect(QRectF(1, 0, 2, alto), 1, 1)
        avance = (self._valor - self._minimo) / max(1, self._maximo - self._minimo)
        contenido = self._maximo - self._minimo + max(1, self._pagina)
        pulgar = max(26.0, alto * max(1, self._pagina) / max(1, contenido)) if self._pagina else max(26.0, alto * 0.22)
        y = (alto - pulgar) * avance
        tono = QColor(VERDE)
        tono.setAlpha(int(230 * self._visible))
        p.setBrush(tono)
        p.drawRoundedRect(QRectF(1, y, 2, pulgar), 1, 1)


def conectar_progreso(vista: QWidget, indicador: ProgresoScroll) -> None:
    """Conecta la primera área desplazable visible de una vista al indicador de progreso."""
    areas = vista.findChildren(QAbstractScrollArea)
    for area in areas:
        if area.verticalScrollBar().maximum() <= 0:
            continue
        barra = area.verticalScrollBar()
        barra.valueChanged.connect(lambda v, b=barra: indicador.set_rango(v, b.minimum(), b.maximum(), b.pageStep()))
        barra.rangeChanged.connect(lambda _mn, _mx, b=barra: indicador.set_rango(b.value(), b.minimum(), b.maximum(), b.pageStep()))
        indicador.set_rango(barra.value(), barra.minimum(), barra.maximum(), barra.pageStep())
        return


class MenuContexto:
    """Menú contextual con la misma piel del resto de la app (hover, atajo visible, separadores)."""

    @staticmethod
    def abrir(padre: QWidget, punto: QPointF, acciones: list[tuple[str, Callable[[], None] | None, str]]) -> None:
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QMenu

        menu = QMenu(padre)
        menu.setObjectName("menuContexto")
        for texto, fn, atajo in acciones:
            if texto == "-":
                menu.addSeparator()
                continue
            accion = QAction(texto, menu)
            if atajo:
                accion.setShortcut(atajo)
            if fn is not None:
                accion.triggered.connect(lambda _=False, f=fn: QTimer.singleShot(0, f))
            else:
                accion.setEnabled(False)
            menu.addAction(accion)
        punto = punto.toPoint() if hasattr(punto, "toPoint") else punto
        menu.exec(padre.mapToGlobal(punto))
