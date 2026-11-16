"""Isla: el único canal de avisos de la aplicación, con la estética de la «Dynamic Island» de Apple.

Todo lo que la aplicación le dice a la persona (éxitos, errores, advertencias, información, procesos, confirmaciones y
estados de conexión) pasa por el gestor global de este módulo. Ninguna pantalla dibuja avisos por su cuenta:

    from .isla import isla
    isla.exito("Producto agregado", "SKU 1042")
    id_ = isla.cargando("Conectando con Oracle…")
    isla.actualizar(id_, "exito", "Oracle conectado")          # la misma cápsula se transforma
    isla.estado("bluetooth", "advertencia", "Bluetooth desconectado")   # persistente hasta que cambie
    isla.quitar_estado("bluetooth")
    isla.confirmar("¿Cerrar la sesión?", "", al_confirmar=salir)         # espera la decisión

Reglas: una sola cápsula visible a la vez, cola con prioridad (errores y confirmaciones primero), mensajes repetidos
agrupados («×2»), el cursor encima pausa el cierre y los estados persistentes (Oracle, Bluetooth) se actualizan en su
sitio en vez de repetirse. La cápsula vive dentro de la ventana, arriba al centro, y no reserva espacio en el diseño.
Se puede llamar desde cualquier hilo: la parte visual siempre corre en el hilo de la interfaz.
"""

from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import (QEasingCurve, QElapsedTimer, QEvent, QEventLoop, QObject, QPointF, QRectF, QSize, QSizeF, Qt, QThread,
                          QTimer, QVariantAnimation, pyqtSignal, pyqtSlot)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QCheckBox, QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from .. import tema
from ..i18n import t

EXITO, ERROR, ADVERTENCIA, INFO, CARGANDO, CONFIRMAR = "exito", "error", "advertencia", "info", "cargando", "confirmar"
TIPOS = (EXITO, ERROR, ADVERTENCIA, INFO, CARGANDO, CONFIRMAR)

DURACION_MS = {EXITO: 3000, INFO: 3000, ADVERTENCIA: 4000, ERROR: 5000}
PRIORIDAD = {ERROR: 3, CONFIRMAR: 3, ADVERTENCIA: 2, CARGANDO: 1, EXITO: 1, INFO: 0}
ACENTO = {EXITO: "#10B981", ERROR: "#F87171", ADVERTENCIA: "#FBBF24", INFO: "#A5B4FC", CARGANDO: "#34D399",
          CONFIRMAR: "#FBBF24"}

ENTRADA_MS, SALIDA_MS, TRANSFORMA_MS = 380, 300, 260
MARGEN_SUPERIOR = 14


def _animar() -> bool:
    from . import widgets
    return bool(widgets.ANIMAR)


@dataclass
class Mensaje:
    id: int
    tipo: str
    titulo: str
    descripcion: str = ""
    clave: str | None = None
    persistente: bool = False
    duracion_ms: int | None = None
    accion: tuple[str, Callable[[], None]] | None = None
    al_confirmar: Callable[[], None] | None = None
    al_cancelar: Callable[[], None] | None = None
    verbo: str = "Confirmar"
    cancelar: str = "Cancelar"
    peligro: bool = True
    entiendo: bool = False
    repeticiones: int = 1
    descartado: bool = False

    @property
    def pegajoso(self) -> bool:
        """Procesos y confirmaciones no caducan solos: esperan a que termine el proceso o decida la persona."""
        return self.tipo in (CARGANDO, CONFIRMAR)

    @property
    def prioridad(self) -> int:
        return PRIORIDAD[self.tipo]

    def duracion(self) -> int | None:
        if self.pegajoso or self.persistente:
            return None
        base = self.duracion_ms if self.duracion_ms is not None else DURACION_MS[self.tipo]
        return max(base, 8000) if self.accion else base

    def texto(self) -> str:
        return f"{self.titulo} {self.descripcion}".strip()

    def firma(self) -> tuple:
        return (self.tipo, self.titulo, self.descripcion)


# ----------------------------------------------------------------------------- icono
class _Icono(QWidget):
    """Icono de la cápsula: dibujado con trazos. Al cambiar de tipo el anterior se encoge y el nuevo crece."""

    LADO = 28

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(self.LADO, self.LADO)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tipo = INFO
        self._anterior: str | None = None
        self._mezcla = 1.0
        self._giro = 0.0
        self._anim_mezcla: QVariantAnimation | None = None
        self._anim_giro = QVariantAnimation(self)
        self._anim_giro.setStartValue(0.0)
        self._anim_giro.setEndValue(360.0)
        self._anim_giro.setDuration(900)
        self._anim_giro.setLoopCount(-1)
        self._anim_giro.valueChanged.connect(self._girar)

    def poner(self, tipo: str, animar: bool) -> None:
        if tipo == self._tipo:
            return
        self._anterior, self._tipo = self._tipo, tipo
        if animar:
            if self._anim_mezcla is not None:
                self._anim_mezcla.stop()
            self._mezcla = 0.0
            self._anim_mezcla = QVariantAnimation(self)
            self._anim_mezcla.setStartValue(0.0)
            self._anim_mezcla.setEndValue(1.0)
            self._anim_mezcla.setDuration(TRANSFORMA_MS)
            self._anim_mezcla.setEasingCurve(QEasingCurve.Type.OutBack)
            self._anim_mezcla.valueChanged.connect(self._mezclar)
            self._anim_mezcla.start()
        else:
            self._mezcla = 1.0
        self._sincronizar_giro()
        self.update()

    def _sincronizar_giro(self) -> None:
        if self._tipo == CARGANDO and _animar():
            if self._anim_giro.state() != QVariantAnimation.State.Running:
                self._anim_giro.start()
        else:
            self._anim_giro.stop()

    def _mezclar(self, v) -> None:
        self._mezcla = float(v)
        self.update()

    def _girar(self, v) -> None:
        self._giro = float(v)
        self.update()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._sincronizar_giro()

    def hideEvent(self, evento) -> None:
        self._anim_giro.stop()
        super().hideEvent(evento)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._mezcla < 1.0 and self._anterior is not None:
            self._dibujar(p, self._anterior, max(0.0, 1.0 - self._mezcla * 1.6))
        self._dibujar(p, self._tipo, min(1.0, max(0.0, self._mezcla)))
        p.end()

    def _dibujar(self, p: QPainter, tipo: str, escala: float) -> None:
        if escala <= 0.01:
            return
        color = QColor(ACENTO[tipo])
        c = QPointF(self.width() / 2, self.height() / 2)
        p.save()
        p.translate(c)
        p.scale(escala, escala)
        p.setOpacity(min(1.0, escala))
        r = 11.0
        if tipo == CARGANDO:
            p.setPen(QPen(QColor(color.red(), color.green(), color.blue(), 55), 2.4))
            p.drawEllipse(QPointF(0, 0), r - 1, r - 1)
            pluma = QPen(color, 2.4)
            pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pluma)
            p.drawArc(QRectF(-(r - 1), -(r - 1), 2 * (r - 1), 2 * (r - 1)), int(-self._giro * 16), 100 * 16)
            p.restore()
            return
        relleno = QColor(color.red(), color.green(), color.blue(), 46)
        p.setBrush(relleno)
        p.setPen(Qt.PenStyle.NoPen)
        if tipo != ADVERTENCIA:
            p.drawEllipse(QPointF(0, 0), r, r)
        pluma = QPen(color, 2.2)
        pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
        pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pluma)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if tipo == EXITO:
            p.drawEllipse(QPointF(0, 0), r - 1, r - 1)
            p.drawPolyline([QPointF(-4.5, 0.4), QPointF(-1.2, 3.6), QPointF(4.8, -3.2)])
        elif tipo == ERROR:
            p.drawEllipse(QPointF(0, 0), r - 1, r - 1)
            p.drawLine(QPointF(-3.6, -3.6), QPointF(3.6, 3.6))
            p.drawLine(QPointF(3.6, -3.6), QPointF(-3.6, 3.6))
        elif tipo == ADVERTENCIA:
            triangulo = QPainterPath()
            triangulo.moveTo(0, -10)
            triangulo.lineTo(10.5, 8)
            triangulo.lineTo(-10.5, 8)
            triangulo.closeSubpath()
            p.fillPath(triangulo, relleno)
            p.drawPath(triangulo)
            p.drawLine(QPointF(0, -3.2), QPointF(0, 2.2))
            p.drawPoint(QPointF(0, 5.2))
        elif tipo == INFO:
            p.drawEllipse(QPointF(0, 0), r - 1, r - 1)
            p.drawLine(QPointF(0, -0.5), QPointF(0, 4.6))
            p.drawPoint(QPointF(0, -4.2))
        else:  # CONFIRMAR: signo de interrogación
            p.drawEllipse(QPointF(0, 0), r - 1, r - 1)
            fuente = QFont(p.font())
            fuente.setPixelSize(14)
            fuente.setBold(True)
            p.setFont(fuente)
            p.drawText(QRectF(-r, -r, 2 * r, 2 * r), int(Qt.AlignmentFlag.AlignCenter), "?")
        p.restore()


# ----------------------------------------------------------------------------- cápsula
class Capsula(QWidget):
    """La cápsula visible. Se coloca sola arriba al centro de la ventana y anima entrada, salida y transformación."""

    cerrar_pedido = pyqtSignal()
    confirmado = pyqtSignal()
    cancelado = pyqtSignal()
    hover = pyqtSignal(bool)

    ANCHO_MIN, ALTO_MIN = 84.0, 30.0

    def __init__(self, ventana: QWidget) -> None:
        super().__init__(ventana)
        self._ventana = ventana
        self.setObjectName("islaCapsula")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self._m: Mensaje | None = None
        self._p = 0.0                      # progreso de entrada/salida (0 oculta, 1 completa)
        self._vis = QSizeF(0, 0)           # tamaño completo mostrado (se anima al transformar)
        self._anim: QVariantAnimation | None = None
        self._anim_tam: QVariantAnimation | None = None
        self._al_ocultar: Callable[[], None] | None = None
        self._saliendo = False

        self._contenido = QWidget(self)
        self._contenido.setObjectName("islaContenido")
        self._contenido.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._opacidad = QGraphicsOpacityEffect(self._contenido)
        self._opacidad.setOpacity(1.0)
        self._contenido.setGraphicsEffect(self._opacidad)

        self.icono = _Icono(self._contenido)
        self.lbl_titulo = QLabel()
        self.lbl_titulo.setObjectName("islaTitulo")
        self.lbl_desc = QLabel()
        self.lbl_desc.setObjectName("islaDesc")
        for etiqueta in (self.lbl_titulo, self.lbl_desc):
            etiqueta.setWordWrap(True)
            etiqueta.setTextFormat(Qt.TextFormat.PlainText)
            etiqueta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.lbl_veces = QLabel()
        self.lbl_veces.setObjectName("islaVeces")
        self.chk = QCheckBox()
        self.chk.setObjectName("islaEntiendo")
        self.btn_ok = QPushButton()
        self.btn_ok.setObjectName("islaOk")
        self.btn_no = QPushButton()
        self.btn_no.setObjectName("islaNo")
        self.btn_accion = QPushButton()
        self.btn_accion.setObjectName("islaAccion")
        self.btn_x = QPushButton("✕")
        self.btn_x.setObjectName("islaCerrar")
        self.btn_x.setToolTip(t("Cerrar"))
        for b in (self.btn_ok, self.btn_no, self.btn_accion, self.btn_x):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setAutoDefault(False)
        self.btn_x.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_ok.clicked.connect(self.confirmado)
        self.btn_no.clicked.connect(self.cancelado)
        self.btn_accion.clicked.connect(self._clic_accion)
        self.btn_x.clicked.connect(self.cerrar_pedido)

        textos = QVBoxLayout()
        textos.setContentsMargins(0, 0, 0, 0)
        textos.setSpacing(1)
        fila_titulo = QHBoxLayout()
        fila_titulo.setContentsMargins(0, 0, 0, 0)
        fila_titulo.setSpacing(6)
        fila_titulo.addWidget(self.lbl_titulo)
        fila_titulo.addWidget(self.lbl_veces)
        fila_titulo.addStretch(1)
        textos.addLayout(fila_titulo)
        textos.addWidget(self.lbl_desc)
        textos.addWidget(self.chk)
        self._lay = QHBoxLayout(self._contenido)
        self._lay.setContentsMargins(14, 10, 10, 10)
        self._lay.setSpacing(12)
        self._lay.addWidget(self.icono, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lay.addLayout(textos, 1)
        self._lay.addWidget(self.btn_accion, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lay.addWidget(self.btn_no, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lay.addWidget(self.btn_ok, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lay.addWidget(self.btn_x, 0, Qt.AlignmentFlag.AlignVCenter)
        self.chk.toggled.connect(lambda _v: self._sincronizar_ok())

        sombra = QGraphicsDropShadowEffect(self)
        sombra.setBlurRadius(34)
        sombra.setOffset(0, 8)
        sombra.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(sombra)
        self._accion_cb: Callable[[], None] | None = None
        self._aplicar_estilo()
        self.hide()

    # ------------------------------------------------------------------ estilo y tema
    def _oscuro(self) -> bool:
        return QColor(tema.colores()["fondo"]).lightness() < 128

    def _aplicar_estilo(self) -> None:
        self.setStyleSheet(
            "QLabel#islaTitulo { color: #FFFFFF; background: transparent; font-weight: 700; }"
            "QLabel#islaDesc { color: rgba(255,255,255,0.74); background: transparent; }"
            "QLabel#islaVeces { color: rgba(255,255,255,0.85); background: rgba(255,255,255,0.14); border-radius: 8px;"
            " padding: 0 6px; font-size: 11px; font-weight: 700; }"
            "QCheckBox#islaEntiendo { color: rgba(255,255,255,0.85); background: transparent; spacing: 6px; }"
            "QPushButton#islaOk, QPushButton#islaNo, QPushButton#islaAccion { border: none; border-radius: 14px;"
            " padding: 6px 16px; font-weight: 700; min-height: 16px; }"
            "QPushButton#islaNo { background: rgba(255,255,255,0.14); color: #FFFFFF; }"
            "QPushButton#islaNo:hover { background: rgba(255,255,255,0.24); }"
            "QPushButton#islaAccion { background: rgba(255,255,255,0.14); color: #34D399; }"
            "QPushButton#islaAccion:hover { background: rgba(255,255,255,0.24); }"
            "QPushButton#islaOk { background: #10B981; color: #04130E; }"
            "QPushButton#islaOk[peligro=\"true\"] { background: #F87171; color: #1A0505; }"
            "QPushButton#islaOk:disabled { background: rgba(255,255,255,0.14); color: rgba(255,255,255,0.4); }"
            "QPushButton#islaCerrar { background: transparent; color: rgba(255,255,255,0.55); border: none;"
            " border-radius: 11px; min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; padding: 0;"
            " font-size: 11px; }"
            "QPushButton#islaCerrar:hover { background: rgba(255,255,255,0.16); color: #FFFFFF; }"
        )
        for etiqueta, px, peso in ((self.lbl_titulo, 13, QFont.Weight.Bold), (self.lbl_desc, 12, QFont.Weight.Normal)):
            f = etiqueta.font()
            f.setPixelSize(px)
            f.setWeight(peso)
            etiqueta.setFont(f)

    def refrescar_tema(self) -> None:
        self.update()

    # ------------------------------------------------------------------ contenido
    def _sincronizar_ok(self) -> None:
        m = self._m
        self.btn_ok.setEnabled(not (m is not None and m.entiendo and not self.chk.isChecked()))

    def _clic_accion(self) -> None:
        cb, self._accion_cb = self._accion_cb, None
        self.cerrar_pedido.emit()
        if cb is not None:
            cb()

    def _cargar(self, m: Mensaje) -> None:
        self._m = m
        confirmar = m.tipo == CONFIRMAR
        self.icono.poner(m.tipo, animar=_animar() and self.isVisible())
        self.lbl_titulo.setText(m.titulo)
        self.lbl_desc.setText(m.descripcion)
        self.lbl_desc.setVisible(bool(m.descripcion))
        self.lbl_veces.setText(f"×{m.repeticiones}")
        self.lbl_veces.setVisible(m.repeticiones > 1)
        self.btn_ok.setText(m.verbo)
        self.btn_no.setText(m.cancelar)
        self.btn_ok.setProperty("peligro", "true" if m.peligro else "false")
        self.btn_ok.style().unpolish(self.btn_ok)
        self.btn_ok.style().polish(self.btn_ok)
        self.btn_ok.setVisible(confirmar)
        self.btn_no.setVisible(confirmar)
        self.chk.setText(t("Entiendo que esta acción no se puede deshacer"))
        self.chk.setVisible(confirmar and m.entiendo)
        self.chk.setChecked(False)
        self._sincronizar_ok()
        self._accion_cb = m.accion[1] if m.accion else None
        self.btn_accion.setText(m.accion[0] if m.accion else "")
        self.btn_accion.setVisible(m.accion is not None and not confirmar)
        self.btn_x.setVisible(not confirmar)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._medir()

    def _medir(self) -> QSize:
        """Calcula el tamaño de la cápsula: se ajusta al texto hasta un ancho máximo y a partir de ahí envuelve."""
        m = self._m
        maximo = max(260, min(560, self._ventana.width() - 2 * 24))
        fuerte = QFontMetrics(self.lbl_titulo.font())
        normal = QFontMetrics(self.lbl_desc.font())
        reservado = self._lay.contentsMargins().left() + self._lay.contentsMargins().right() + _Icono.LADO
        espacios = self._lay.spacing()
        for b in (self.btn_accion, self.btn_no, self.btn_ok, self.btn_x):
            if not b.isHidden():
                reservado += b.sizeHint().width() + espacios
        reservado += espacios
        veces = self.lbl_veces.sizeHint().width() + 6 if not self.lbl_veces.isHidden() else 0
        quiere = max(fuerte.horizontalAdvance(m.titulo) + veces, normal.horizontalAdvance(m.descripcion) if m.descripcion else 0)
        if m.entiendo and m.tipo == CONFIRMAR:
            quiere = max(quiere, QFontMetrics(self.chk.font()).horizontalAdvance(self.chk.text()) + 24)
        ancho_texto = int(min(quiere + 6, maximo - reservado))
        ancho_texto = max(ancho_texto, 120)
        self.lbl_titulo.setFixedWidth(max(60, min(fuerte.horizontalAdvance(m.titulo) + 6, ancho_texto - veces)))
        self.lbl_titulo.setFixedHeight(self.lbl_titulo.heightForWidth(self.lbl_titulo.width()))
        self.lbl_desc.setFixedWidth(ancho_texto)
        self.lbl_desc.setFixedHeight(self.lbl_desc.heightForWidth(ancho_texto) if m.descripcion else 0)
        self._lay.activate()
        tam = self._lay.sizeHint()
        self._contenido.setFixedSize(tam)
        return tam

    # ------------------------------------------------------------------ geometría
    def _aplicar(self) -> None:
        if self._m is None:
            return
        e = max(0.0, min(1.0, self._p))
        W, H = self._vis.width(), self._vis.height()
        w = self.ANCHO_MIN + (W - self.ANCHO_MIN) * e
        h = self.ALTO_MIN + (H - self.ALTO_MIN) * e
        y = MARGEN_SUPERIOR - (1.0 - e) * (H + MARGEN_SUPERIOR + 12)
        x = (self._ventana.width() - w) / 2
        self.setGeometry(round(x), round(y), max(1, round(w)), max(1, round(h)))
        cw, ch = self._contenido.width(), self._contenido.height()
        self._contenido.move(round((self.width() - cw) / 2), round((self.height() - ch) / 2))
        self._contenido_opacidad(max(0.0, min(1.0, (e - 0.45) / 0.55)))
        self.update()

    def _contenido_opacidad(self, valor: float) -> None:
        self._opacidad.setEnabled(valor < 0.999)
        self._opacidad.setOpacity(valor)

    def reubicar(self) -> None:
        """La ventana cambió de tamaño: la cápsula se vuelve a medir y se mantiene centrada."""
        if self._m is None or self.isHidden():
            return
        tam = self._medir()
        self._vis = QSizeF(tam.width(), tam.height())
        self._aplicar()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        oscuro = self._oscuro()
        fondo = QColor("#1B211F" if oscuro else "#0B0F0E")
        borde = QColor("#33403B" if oscuro else "#1C2623")
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radio = min(rect.height() / 2, 30.0)
        ruta = QPainterPath()
        ruta.addRoundedRect(rect, radio, radio)
        p.fillPath(ruta, fondo)
        p.setPen(QPen(borde, 1.0))
        p.drawPath(ruta)
        if self._m is not None and self._p > 0.6:
            color = QColor(ACENTO[self._m.tipo])
            color.setAlpha(int(70 * min(1.0, (self._p - 0.6) / 0.4)))
            p.setPen(QPen(color, 1.0))
            p.drawPath(ruta)
        p.end()

    # ------------------------------------------------------------------ animaciones
    def _detener(self) -> None:
        for a in (self._anim, self._anim_tam):
            if a is not None:
                a.stop()
        self._anim = self._anim_tam = None

    def mostrar(self, m: Mensaje) -> None:
        self._detener()
        self._saliendo = False
        self._al_ocultar = None
        self._cargar(m)
        tam = self._contenido.size()
        self._vis = QSizeF(tam.width(), tam.height())
        if not _animar():
            self._p = 1.0
            self.show()
            self.raise_()
            self._aplicar()
            return
        self._p = 0.0
        self.show()
        self.raise_()
        self._aplicar()
        self._anim = self._crear_anim(0.0, 1.0, ENTRADA_MS, QEasingCurve.Type.OutCubic, self._poner_progreso, None)

    def transformar(self, m: Mensaje) -> None:
        """Cambia el contenido sin ocultar la cápsula: el icono se transforma y el tamaño se acomoda de forma continua."""
        if self.isHidden() or self._saliendo:
            self.mostrar(m)
            return
        antes = QSizeF(self._vis)
        self._cargar(m)
        tam = self._contenido.size()
        destino = QSizeF(tam.width(), tam.height())
        if self._anim_tam is not None:
            self._anim_tam.stop()
        if not _animar():
            self._vis = destino
            self._p = 1.0
            self._aplicar()
            return
        self._p = max(self._p, 1.0) if self._p >= 0.99 else self._p

        def paso(v: float) -> None:
            self._vis = QSizeF(antes.width() + (destino.width() - antes.width()) * v,
                               antes.height() + (destino.height() - antes.height()) * v)
            self._aplicar()
        self._anim_tam = self._crear_anim(0.0, 1.0, TRANSFORMA_MS, QEasingCurve.Type.OutCubic, paso, None)

    def ocultar(self, al_terminar: Callable[[], None] | None = None) -> None:
        if self.isHidden():
            if al_terminar:
                al_terminar()
            return
        self._detener()
        self._saliendo = True
        self._al_ocultar = al_terminar
        if not _animar():
            self._terminar_salida()
            return
        self._anim = self._crear_anim(self._p, 0.0, SALIDA_MS, QEasingCurve.Type.InCubic, self._poner_progreso,
                                      self._terminar_salida)

    def _terminar_salida(self) -> None:
        self._saliendo = False
        self.hide()
        self._p = 0.0
        cb, self._al_ocultar = self._al_ocultar, None
        if cb is not None:
            cb()

    def _poner_progreso(self, v: float) -> None:
        self._p = v
        self._aplicar()

    def _crear_anim(self, ini: float, fin: float, ms: int, curva, paso, al_terminar) -> QVariantAnimation:
        a = QVariantAnimation(self)
        a.setStartValue(float(ini))
        a.setEndValue(float(fin))
        a.setDuration(ms)
        a.setEasingCurve(curva)
        a.valueChanged.connect(lambda v: paso(float(v)))
        if al_terminar is not None:
            a.finished.connect(al_terminar)
        a.start()
        return a

    # ------------------------------------------------------------------ ratón
    def enterEvent(self, evento) -> None:
        self.hover.emit(True)
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self.hover.emit(False)
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        evento.accept()  # la cápsula no deja pasar los clics a lo que hay debajo


class _Velo(QWidget):
    """Atenúa y bloquea la ventana mientras una confirmación espera respuesta."""

    def __init__(self, ventana: QWidget) -> None:
        super().__init__(ventana)
        self.hide()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 96))
        p.end()

    def mousePressEvent(self, evento) -> None:
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:
        evento.accept()


# ----------------------------------------------------------------------------- gestor
class GestorIsla(QObject):
    """Cola, prioridades, estados persistentes y ciclo de vida de la cápsula. Es único para toda la aplicación."""

    _orden = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self._ids = itertools.count(1)
        self._ventana: QWidget | None = None
        self._capsula: Capsula | None = None
        self._velo: _Velo | None = None
        self._actual: Mensaje | None = None
        self._saliendo = False
        self._cola: list[Mensaje] = []
        self._estados: dict[str, Mensaje] = {}
        self._historial: deque[str] = deque(maxlen=60)
        self._vencimiento = QTimer(self)
        self._vencimiento.setSingleShot(True)
        self._vencimiento.timeout.connect(self._vencio)
        self._reloj = QElapsedTimer()
        self._restante = 0
        self._orden.connect(self._correr)

    # ------------------------------------------------------------------ instalación
    def instalar(self, ventana: QWidget) -> None:
        """Monta la cápsula dentro de ``ventana`` (la ventana principal). Se puede llamar de nuevo con otra ventana."""
        self._soltar()
        self._ventana = ventana
        self._capsula = Capsula(ventana)
        self._velo = _Velo(ventana)
        self._capsula.cerrar_pedido.connect(self._cerrar_manual)
        self._capsula.confirmado.connect(lambda: self._resolver(True))
        self._capsula.cancelado.connect(lambda: self._resolver(False))
        self._capsula.hover.connect(self._sobre)
        ventana.installEventFilter(self)
        ventana.destroyed.connect(self._ventana_destruida)

    def _ventana_destruida(self, *_args) -> None:
        self._ventana = self._capsula = self._velo = None
        self._soltar(solo_estado=True)

    def _soltar(self, solo_estado: bool = False) -> None:
        pendiente = self._actual
        self._vencimiento.stop()
        if not solo_estado and self._ventana is not None:
            try:
                self._ventana.removeEventFilter(self)
            except RuntimeError:
                pass
        self._actual = None
        self._saliendo = False
        if pendiente is not None and pendiente.tipo == CONFIRMAR and pendiente.al_cancelar:
            pendiente.al_cancelar()
        for m in self._cola:
            if m.tipo == CONFIRMAR and m.al_cancelar:
                m.al_cancelar()
        self._cola.clear()
        self._estados.clear()

    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self._ventana and self._capsula is not None:
            tipo = evento.type()
            if tipo == QEvent.Type.Resize:
                if self._velo is not None:
                    self._velo.setGeometry(self._ventana.rect())
                self._capsula.reubicar()
            elif tipo == QEvent.Type.KeyPress and evento.key() == Qt.Key.Key_Escape:
                if self._actual is not None and self._actual.tipo == CONFIRMAR:
                    self._resolver(False)
                    return True
            elif tipo in (QEvent.Type.PaletteChange, QEvent.Type.StyleChange, QEvent.Type.ApplicationPaletteChange):
                self._capsula.refrescar_tema()
        return super().eventFilter(objeto, evento)

    # ------------------------------------------------------------------ API pública (segura entre hilos)
    def _id(self) -> int:
        return next(self._ids)

    def _ejecutar(self, funcion: Callable[[], None]) -> None:
        if QThread.currentThread() is self.thread():
            funcion()
        else:
            self._orden.emit(funcion)

    @pyqtSlot(object)
    def _correr(self, funcion) -> None:
        funcion()

    def _crear(self, tipo: str, titulo: str, descripcion: str = "", **datos) -> int:
        m = Mensaje(self._id(), tipo, titulo, descripcion, **datos)
        self._ejecutar(lambda: self._publicar(m))
        return m.id

    def exito(self, titulo: str, descripcion: str = "", **datos) -> int:
        return self._crear(EXITO, titulo, descripcion, **datos)

    def error(self, titulo: str, descripcion: str = "", **datos) -> int:
        return self._crear(ERROR, titulo, descripcion, **datos)

    def advertencia(self, titulo: str, descripcion: str = "", **datos) -> int:
        return self._crear(ADVERTENCIA, titulo, descripcion, **datos)

    def info(self, titulo: str, descripcion: str = "", **datos) -> int:
        return self._crear(INFO, titulo, descripcion, **datos)

    def cargando(self, titulo: str, descripcion: str = "", **datos) -> int:
        return self._crear(CARGANDO, titulo, descripcion, **datos)

    def confirmar(self, titulo: str, descripcion: str = "", al_confirmar: Callable[[], None] | None = None,
                  al_cancelar: Callable[[], None] | None = None, verbo: str = "Confirmar", cancelar: str = "Cancelar",
                  peligro: bool = True, entiendo: bool = False) -> int:
        """Confirmación que espera la decisión. Nada se ejecuta hasta que la persona elige."""
        return self._crear(CONFIRMAR, titulo, descripcion, al_confirmar=al_confirmar, al_cancelar=al_cancelar,
                           verbo=verbo, cancelar=cancelar, peligro=peligro, entiendo=entiendo)

    def confirmar_y_esperar(self, titulo: str, descripcion: str = "", verbo: str = "Confirmar", cancelar: str = "Cancelar",
                            peligro: bool = True, entiendo: bool = False) -> bool:
        """Como ``confirmar`` pero devuelve la decisión (bloquea solo el flujo que llama, no la interfaz)."""
        if self._capsula is None or QThread.currentThread() is not self.thread():
            return False
        bucle = QEventLoop()
        respuesta = [False]

        def si() -> None:
            respuesta[0] = True
            bucle.quit()
        self.confirmar(titulo, descripcion, si, bucle.quit, verbo, cancelar, peligro, entiendo)
        bucle.exec()
        return respuesta[0]

    def estado(self, clave: str, tipo: str, titulo: str, descripcion: str = "") -> int:
        """Estado persistente (Oracle, Bluetooth…): se queda hasta que cambie y no se repite si no cambió."""
        return self._crear(tipo, titulo, descripcion, clave=clave, persistente=True)

    def quitar_estado(self, clave: str) -> None:
        self._ejecutar(lambda: self._quitar_estado(clave))

    def actualizar(self, id_: int, tipo: str, titulo: str, descripcion: str = "", **datos) -> None:
        self._ejecutar(lambda: self._actualizar(id_, tipo, titulo, descripcion, datos))

    def cerrar(self, id_: int | None = None, clave: str | None = None) -> None:
        self._ejecutar(lambda: self._cerrar(id_, clave))

    def elevar(self) -> None:
        """Vuelve a poner la cápsula por encima de lo último que se abrió en la ventana (p. ej. una hoja flotante)."""
        if self._capsula is not None and not self._capsula.isHidden():
            if self._velo is not None and not self._velo.isHidden():
                self._velo.raise_()
            self._capsula.raise_()

    def textos(self) -> list[str]:
        """Lo que está visible o esperando turno (para las pruebas)."""
        vistos = [m for m in [self._actual, *self._cola, *self._estados.values()] if m is not None]
        salida: list[str] = []
        for m in vistos:
            if m.texto() not in salida:
                salida.append(m.texto())
        return salida

    def historial(self) -> list[str]:
        return list(self._historial)

    def actual(self) -> Mensaje | None:
        return self._actual

    # ------------------------------------------------------------------ lógica (hilo de la interfaz)
    def _ocupado(self) -> bool:
        return self._actual is not None or self._saliendo

    def _publicar(self, m: Mensaje) -> None:
        self._historial.append(f"{m.tipo}: {m.texto()}")
        if m.persistente and m.clave:
            self._poner_estado(m)
            return
        if m.clave:
            if self._actual is not None and self._actual.clave == m.clave and not self._actual.persistente:
                self._sustituir_actual(m)
                return
            for i, q in enumerate(self._cola):
                if q.clave == m.clave:
                    self._cola[i] = m
                    return
        if self._actual is not None and not self._actual.persistente and self._actual.firma() == m.firma() \
                and not m.pegajoso:
            self._actual.repeticiones += 1
            self._arrancar_vencimiento(self._actual)
            if self._capsula is not None:
                self._capsula.transformar(self._actual)
            return
        for q in self._cola:
            if q.firma() == m.firma() and not m.pegajoso:
                q.repeticiones += 1
                return
        if not self._ocupado() or (self._actual is not None and self._actual.persistente):
            self._mostrar(m)
        elif self._debe_interrumpir(m):
            anterior = self._actual
            if anterior is not None and (anterior.prioridad >= 2 or anterior.pegajoso):
                self._cola.insert(0, anterior)
            self._mostrar(m)
        else:
            self._encolar(m)

    def _debe_interrumpir(self, m: Mensaje) -> bool:
        a = self._actual
        if a is None or a.persistente or self._saliendo:
            return False
        if m.tipo == CONFIRMAR:   # quien pide una confirmación está esperando: pasa al frente de todo lo demás
            return a.tipo != CONFIRMAR
        return not a.pegajoso and m.prioridad > a.prioridad and m.prioridad >= 2

    def _encolar(self, m: Mensaje) -> None:
        pos = len(self._cola)
        for i, q in enumerate(self._cola):
            if m.prioridad > q.prioridad:
                pos = i
                break
        self._cola.insert(pos, m)

    def _mostrar(self, m: Mensaje) -> None:
        self._vencimiento.stop()
        habia = self._actual is not None and self._capsula is not None and not self._capsula.isHidden()
        self._actual = m
        self._saliendo = False
        if self._capsula is not None:
            if m.tipo == CONFIRMAR and self._velo is not None:
                self._velo.setGeometry(self._ventana.rect())
                self._velo.show()
                self._velo.raise_()
                self._capsula.raise_()
            if habia:
                self._capsula.transformar(m)
            else:
                self._capsula.mostrar(m)
            if m.tipo == CONFIRMAR:
                foco = self._capsula.btn_no if m.peligro else self._capsula.btn_ok
                foco.setFocus(Qt.FocusReason.OtherFocusReason)
        self._arrancar_vencimiento(m)

    def _arrancar_vencimiento(self, m: Mensaje) -> None:
        self._vencimiento.stop()
        ms = m.duracion()
        if ms is None:
            return
        self._restante = ms
        self._reloj.start()
        self._vencimiento.start(ms)

    def _sustituir_actual(self, m: Mensaje) -> None:
        self._mostrar(m)

    def _sobre(self, dentro: bool) -> None:
        """El cursor encima pausa el cierre automático; al salir sigue con el tiempo que quedaba (mínimo 1,2 s)."""
        m = self._actual
        if m is None or m.duracion() is None:
            return
        if dentro:
            if self._vencimiento.isActive():
                self._restante = max(1200, self._vencimiento.remainingTime())
                self._vencimiento.stop()
        else:
            self._vencimiento.start(max(1200, self._restante))

    def _vencio(self) -> None:
        m = self._actual
        if m is None:
            return
        if m.persistente:
            return
        self._retirar_actual()

    def _retirar_actual(self) -> None:
        """Cierra lo que se está mostrando y, al terminar la salida, pasa a lo siguiente."""
        self._vencimiento.stop()
        m = self._actual
        self._actual = None
        if self._velo is not None:
            self._velo.hide()
        if self._capsula is None or self._capsula.isHidden():
            self._siguiente()
            return
        self._saliendo = True
        self._capsula.ocultar(self._siguiente)
        del m

    def _siguiente(self) -> None:
        self._saliendo = False
        if self._actual is not None:
            return
        if self._cola:
            self._mostrar(self._cola.pop(0))
            return
        visibles = [s for s in self._estados.values() if not s.descartado]
        if visibles:
            visibles.sort(key=lambda s: s.prioridad)
            self._mostrar(visibles[-1])

    def _poner_estado(self, m: Mensaje) -> None:
        previo = self._estados.get(m.clave)
        if previo is not None and previo.firma() == m.firma():
            return  # mismo estado: no se repite
        self._estados[m.clave] = m
        if self._actual is not None and self._actual is previo:
            self._mostrar(m)
        elif not self._ocupado():
            self._mostrar(m)

    def _quitar_estado(self, clave: str) -> None:
        m = self._estados.pop(clave, None)
        if m is not None and self._actual is m:
            self._retirar_actual()

    def _actualizar(self, id_: int, tipo: str, titulo: str, descripcion: str, datos: dict) -> None:
        objetivo = None
        if self._actual is not None and self._actual.id == id_:
            objetivo = self._actual
        else:
            objetivo = next((q for q in self._cola if q.id == id_), None)
            if objetivo is None:
                objetivo = next((s for s in self._estados.values() if s.id == id_), None)
        if objetivo is None:
            # El aviso original ya se cerró (por la persona o por el tiempo): se muestra como uno nuevo.
            self._publicar(Mensaje(self._id(), tipo, titulo, descripcion, **datos))
            return
        objetivo.tipo, objetivo.titulo, objetivo.descripcion = tipo, titulo, descripcion
        objetivo.repeticiones = 1
        for campo, valor in datos.items():
            setattr(objetivo, campo, valor)
        self._historial.append(f"{tipo}: {objetivo.texto()}")
        if objetivo is self._actual:
            if self._velo is not None and tipo != CONFIRMAR:
                self._velo.hide()
            if self._capsula is not None:
                self._capsula.transformar(objetivo)
            self._arrancar_vencimiento(objetivo)

    def _cerrar(self, id_: int | None, clave: str | None) -> None:
        def coincide(m: Mensaje) -> bool:
            return (id_ is not None and m.id == id_) or (clave is not None and m.clave == clave)
        self._cola = [q for q in self._cola if not coincide(q)]
        for k in [k for k, s in self._estados.items() if coincide(s)]:
            self._estados.pop(k)
        if self._actual is not None and coincide(self._actual):
            self._cancelar_si_confirmacion(self._actual)
            self._retirar_actual()

    def _cancelar_si_confirmacion(self, m: Mensaje) -> None:
        if m.tipo == CONFIRMAR and m.al_cancelar:
            cb, m.al_cancelar = m.al_cancelar, None
            cb()

    def _cerrar_manual(self) -> None:
        m = self._actual
        if m is None:
            return
        if m.persistente:
            m.descartado = True  # vuelve a mostrarse si el estado cambia
        self._retirar_actual()

    def _resolver(self, acepta: bool) -> None:
        m = self._actual
        if m is None or m.tipo != CONFIRMAR:
            return
        self._actual = m
        al_confirmar, al_cancelar = m.al_confirmar, m.al_cancelar
        m.al_confirmar = m.al_cancelar = None
        self._retirar_actual()
        callback = al_confirmar if acepta else al_cancelar
        if callback is not None:
            callback()


_unico: GestorIsla | None = None


def gestor() -> GestorIsla:
    """El gestor único. Se crea la primera vez que se usa (hace falta que ya exista la aplicación Qt)."""
    global _unico
    if _unico is None:
        _unico = GestorIsla()
    return _unico


class _Acceso:
    """``isla.exito(...)`` desde cualquier módulo, sin preocuparse de cuándo se crea el gestor."""

    def __getattr__(self, nombre: str):
        return getattr(gestor(), nombre)


isla = _Acceso()


from .. import i18n  # noqa: E402

i18n.registrar({
    "Cerrar": "Close",
    "Cancelar": "Cancel",
    "Confirmar": "Confirm",
    "Entiendo que esta acción no se puede deshacer": "I understand this action cannot be undone",
    "No se pudo consultar la base de datos": "Could not query the database",
    "Iniciando sesión…": "Signing in…",
    "Inicio de sesión exitoso": "Signed in successfully",
    "No se pudo iniciar sesión": "Could not sign in",
    "Registrando usuario…": "Registering user…",
    "Usuario registrado correctamente": "User registered successfully",
    "No se pudo crear la cuenta": "Could not create the account",
    "Enviando solicitud…": "Sending request…",
    "Solicitud enviada": "Request sent",
    "No se pudo recuperar la contraseña": "Could not recover the password",
    "Bienvenido, {nombre}": "Welcome, {nombre}",
    "Cambios guardados": "Changes saved",
    "La configuración se guardó correctamente.": "The settings were saved successfully.",
    "No se pudo guardar la configuración": "Could not save the settings",
    "Respaldo creado": "Backup created",
    "Creando respaldo…": "Creating backup…",
    "Restaurando respaldo…": "Restoring backup…",
    "Se pausa el servicio Bluetooth.": "The Bluetooth service is paused.",
    "Respaldo automático guardado": "Automatic backup saved",
    "No se pudo completar el respaldo": "Could not complete the backup",
    "No se pudo controlar el servicio Bluetooth": "Could not control the Bluetooth service",
    "Procesando lecturas…": "Processing readings…",
    "Procesamiento completado": "Processing completed",
    "No se pudo procesar": "Could not process",
    "Contraseña actualizada": "Password updated",
    "No se pudo cambiar la contraseña": "Could not change the password",
    "No se pudo actualizar la foto": "Could not update the photo",
    "Foto de perfil": "Profile photo",
    "No se pudo guardar la preferencia": "Could not save the preference",
    "Apariencia actualizada": "Appearance updated",
    "Idioma actualizado": "Language updated",
    "Cuenta reactivada": "Account reactivated",
    "Cuenta suspendida": "Account suspended",
    "Teléfono desvinculado": "Phone unlinked",
    "Contraseña restablecida": "Password reset",
    "Permiso actualizado": "Permission updated",
    "Oracle conectado": "Oracle connected",
    "La conexión se restableció.": "The connection was restored.",
    "Oracle sin conexión": "Oracle offline",
    "Error en el servicio Bluetooth": "Bluetooth service error",
    "Servicio Bluetooth detenido": "Bluetooth service stopped",
    "Los teléfonos no podrán enviar lecturas.": "Phones will not be able to send readings.",
    "Servicio Bluetooth en pausa": "Bluetooth service paused",
    "Sincronizando inventario": "Syncing inventory",
    "Recibiendo lecturas del teléfono…": "Receiving readings from the phone…",
    "Error en la sincronización": "Sync error",
    "Celular conectado": "Phone connected",
    "Listo para recibir el conteo.": "Ready to receive the count.",
    "Celular desconectado": "Phone disconnected",
})
