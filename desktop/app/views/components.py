"""Componentes interactivos compartidos: tarjetas, drawer, confirmación, tooltips, chips, barra de lote y acciones de fila.

Principio: el estado (texto, selección, datos) se actualiza de inmediato; solo el dibujo se anima. Así una prueba con
``APP_SIN_ANIMACIONES=1`` ve el resultado final sin esperar.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtWidgets import QApplication

from PyQt6 import sip

from ..i18n import t
from . import motion, motion_global, widgets
from .iconos import icono
from .isla import isla

VERDE, ROJO = "#10B981", "#F87171"


# ----------------------------------------------------------------------------- tarjetas
class TarjetaHover(QFrame):
    """Tarjeta con hover rico: se eleva, el borde hace glow y las acciones rápidas suben desde abajo."""

    clicked = pyqtSignal()
    contexto = pyqtSignal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._anim_acciones: QVariantAnimation | None = None
        self._sombra = None
        self.cuerpo = QVBoxLayout(self)
        self.cuerpo.setContentsMargins(16, 14, 16, 14)
        self.cuerpo.setSpacing(8)
        self._acciones = QWidget(self)
        self._acciones.setObjectName("accionesCard")
        self._en_acciones = QHBoxLayout(self._acciones)
        self._en_acciones.setContentsMargins(0, 6, 0, 0)
        self._en_acciones.setSpacing(6)
        self._en_acciones.addStretch(1)
        self._acciones.setMaximumHeight(0)
        self._acciones.hide()
        self.cuerpo.addWidget(self._acciones)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contexto)

    # -- construcción
    def agregar(self, widget: QWidget, estirar: int = 0) -> None:
        self.cuerpo.insertWidget(max(0, self.cuerpo.count() - 1), widget, estirar)

    def agregar_accion(self, texto: str, fn: Callable[[], None], primaria: bool = False) -> QPushButton:
        boton = QPushButton(texto)
        boton.setObjectName("accionCard")
        if primaria:
            boton.setProperty("primaria", True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        boton.clicked.connect(lambda _=False: fn())
        self._en_acciones.insertWidget(self._en_acciones.count() - 1, boton)
        return boton

    def acciones(self) -> list[QPushButton]:
        return [b for b in self._acciones.findChildren(QPushButton)]

    # -- hover
    def enterEvent(self, evento) -> None:
        self._hover = True
        self.setProperty("hover", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._sombra = motion.elevar(self, True)
        if self._en_acciones.count() > 1:
            self._animar_acciones(True)
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._hover = False
        self.setProperty("hover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._sombra = motion.elevar(self, False)
        if not self._acciones.underMouse() and not self._acciones.hasFocus():
            self._animar_acciones(False)
        super().leaveEvent(evento)

    def _animar_acciones(self, mostrar: bool) -> None:
        motion.detener(self._anim_acciones)
        alto = max(34, self._acciones.sizeHint().height())
        if mostrar:
            self._acciones.show()
            self._acciones.setMaximumHeight(0)
            self._anim_acciones = motion.animar(self, 0.0, float(alto), motion.NORMAL,
                                                lambda v: self._acciones.setMaximumHeight(int(v)))
        else:
            inicio = self._acciones.maximumHeight() or alto
            self._anim_acciones = motion.animar(
                self, float(inicio), 0.0, motion.RAPIDO,
                lambda v: self._acciones.setMaximumHeight(int(v)),
                lambda: self._acciones.hide())

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and not self._en_acciones.geometry().contains(evento.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(evento)

    def contextMenuEvent(self, evento) -> None:
        self.contexto.emit(evento.pos())
        evento.accept()

    def paintEvent(self, evento) -> None:
        super().paintEvent(evento)


# ----------------------------------------------------------------------------- drawer
class Drawer(QWidget):
    """Panel lateral con backdrop difuminado; se abre desde la derecha y se cierra con Esc, clic fuera o ✕."""

    cerrado = pyqtSignal()

    def __init__(self, host: QWidget, ancho: int = 430) -> None:
        super().__init__(host)
        self._host = host
        self.ancho = ancho
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()

        self._fondo = QLabel(self)
        self._fondo.setObjectName("drawerFondo")
        self._fondo.setScaledContents(True)
        self._fondo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._velo = QFrame(self)
        self._velo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._velo.setObjectName("drawerVelo")
        self._velo.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self._panel = QFrame(self)
        self._panel.setObjectName("drawerPanel")
        en_panel = QVBoxLayout(self._panel)
        en_panel.setContentsMargins(22, 20, 22, 20)
        en_panel.setSpacing(12)
        cabecera = QHBoxLayout()
        self.titulo = QLabel("")
        self.titulo.setObjectName("drawerTitulo")
        cerrar = QToolButton()
        cerrar.setObjectName("cerrarDrawer")
        cerrar.setIcon(icono("x", tam=16))
        cerrar.setToolTip("Cerrar (Esc)")
        cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        cerrar.clicked.connect(self.cerrar)
        cabecera.addWidget(self.titulo, 1)
        cabecera.addWidget(cerrar)
        en_panel.addLayout(cabecera)
        self._area = QScrollArea()
        self._area.setWidgetResizable(True)
        self._area.setFrameShape(QFrame.Shape.NoFrame)
        en_panel.addWidget(self._area, 1)
        self._contenido: QWidget | None = None
        self._anim: QVariantAnimation | None = None
        self._opacidad_velo = None

    @property
    def panel(self) -> QFrame:
        return self._panel

    def abrir(self, titulo: str, contenido: QWidget) -> None:
        self.titulo.setText(titulo)
        if self._contenido is not None:
            self._contenido.deleteLater()
        self._contenido = contenido
        self._area.setWidget(contenido)
        self.setGeometry(self._host.rect())
        self._reubicar()
        self._fondo.setPixmap(self._host.grab())
        desenfoque = QGraphicsBlurEffect(self._fondo)
        desenfoque.setBlurRadius(9)
        self._fondo.setGraphicsEffect(desenfoque)
        self._velo.setStyleSheet("background: rgba(0, 0, 0, 0.55);")
        self.show()
        self.raise_()
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        motion.detener(self._anim)
        inicio, fin = float(self._host.width()), float(self._host.width() - self.ancho)
        self._panel.move(self._host.width(), 0)
        self._velo.setGeometry(self.rect())
        self._velo.show()
        self._anim = motion.animar(self, inicio, fin, motion.LENTO,
                                   lambda v: self._panel.move(int(v), 0),
                                   None, motion.CURVA_SUAVE)

    def cerrar(self) -> None:
        if self.isHidden():
            return
        motion.detener(self._anim)
        inicio = float(self._panel.x())
        self._anim = motion.animar(self, inicio, float(self._host.width()), motion.NORMAL,
                                   lambda v: self._panel.move(int(v), 0), self._terminar,
                                   motion.CURVA)

    def _terminar(self) -> None:
        self.hide()
        self._velo.hide()
        if self._contenido is not None:
            self._contenido.deleteLater()
            self._contenido = None
            self._area.takeWidget()
        self.cerrado.emit()

    def _reubicar(self) -> None:
        self._fondo.setGeometry(self.rect())
        self._velo.setGeometry(self.rect())
        self._panel.setGeometry(self._host.width(), 0, self.ancho, self.height())

    def resizeEvent(self, evento) -> None:
        self._reubicar()
        super().resizeEvent(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.pos().x() < self._panel.x():
            self.cerrar()
            evento.accept()
            return
        super().mousePressEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.cerrar()
            evento.accept()
            return
        super().keyPressEvent(evento)


def _titulo(texto: str, objeto: str = "seccion") -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setObjectName(objeto)
    etiqueta.setWordWrap(True)
    return etiqueta


def contenido_detalle(titulo: str, filas: list[tuple[str, str]], nota: str = "", acciones: list[QWidget] | None = None) -> QWidget:
    """Contenido estándar de un drawer: pares etiqueta/valor, una nota y acciones al final."""
    caja = QWidget()
    lay = QVBoxLayout(caja)
    lay.setContentsMargins(0, 0, 6, 0)
    lay.setSpacing(10)
    if titulo:
        lay.addWidget(_titulo(titulo))
    for etiqueta, valor in filas:
        fila = QHBoxLayout()
        fila.setSpacing(12)
        nombre = QLabel(etiqueta)
        nombre.setObjectName("subtitulo")
        nombre.setFixedWidth(96)
        nombre.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        dato = QLabel(valor)
        dato.setObjectName("datoDrawer")
        dato.setWordWrap(True)
        dato.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        fila.addWidget(nombre, 0)
        fila.addWidget(dato, 1)
        lay.addLayout(fila)
    if nota:
        texto = QLabel(nota)
        texto.setObjectName("ayuda")
        texto.setWordWrap(True)
        lay.addWidget(texto)
    for accion in acciones or []:
        lay.addWidget(accion)
    lay.addStretch(1)
    return caja


# ----------------------------------------------------------------------------- confirmación
class Confirmacion(QDialog):
    """Modal con backdrop, checkbox de «Entiendo» y botón destructivo que respira hasta confirmar."""

    def __init__(self, host: QWidget, titulo: str, texto: str, verbo: str = "Confirmar",
                 requiere_entendido: bool = False, peligro: bool = True, detalle: str = "") -> None:
        super().__init__(host.window())
        self.resultado = False
        self._requiere = requiere_entendido
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setObjectName("dialogoModal")
        self.setGeometry(host.window().mapToGlobal(QPoint(0, 0)).x(), host.window().mapToGlobal(QPoint(0, 0)).y(),
                         host.window().width(), host.window().height())

        velo = QFrame(self)
        velo.setObjectName("modalVelo")
        velo.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        velo.setStyleSheet("background: rgba(0, 0, 0, 0.62);")
        velo.setGeometry(self.rect())

        self._caja = QFrame(self)
        self._caja.setObjectName("modalCaja")
        self._caja.setFixedWidth(470)
        en_caja = QVBoxLayout(self._caja)
        en_caja.setContentsMargins(26, 24, 26, 20)
        en_caja.setSpacing(12)
        encabezado = QLabel(titulo)
        encabezado.setObjectName("modalTitulo")
        encabezado.setWordWrap(True)
        en_caja.addWidget(encabezado)
        cuerpo = QLabel(texto)
        cuerpo.setObjectName("modalTexto")
        cuerpo.setWordWrap(True)
        en_caja.addWidget(cuerpo)
        if detalle:
            nota = QLabel(detalle)
            nota.setObjectName("ayuda")
            nota.setWordWrap(True)
            en_caja.addWidget(nota)
        self.check = QCheckBox("Entiendo que esta acción no se puede deshacer")
        self.check.setObjectName("confirmarEntiendo")
        self.check.setVisible(requiere_entendido)
        en_caja.addWidget(self.check)
        self.aviso = QLabel("")
        self.aviso.setObjectName("errorFormulario")
        self.aviso.setWordWrap(True)
        self.aviso.hide()
        en_caja.addWidget(self.aviso)
        botones = QHBoxLayout()
        botones.addStretch(1)
        cancelar = QPushButton("Cancelar")
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.clicked.connect(self.reject)
        self._contenedor_confirmar = QWidget(self._caja)
        en_confirmar = QHBoxLayout(self._contenedor_confirmar)
        en_confirmar.setContentsMargins(0, 0, 0, 0)
        self.btn_confirmar = QPushButton(verbo)
        self.btn_confirmar.setObjectName("peligro" if peligro else "primario")
        self.btn_confirmar.setMinimumWidth(128)
        self.btn_confirmar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_confirmar.setDefault(True)
        self.btn_confirmar.clicked.connect(self._confirmar)
        en_confirmar.addWidget(self.btn_confirmar)
        botones.addWidget(cancelar)
        botones.addWidget(self._contenedor_confirmar)
        en_caja.addLayout(botones)
        self._reubicar()
        self._respirar()
        motion.desvanecer(self._caja, 0.0, 1.0, motion.NORMAL)

    def _reubicar(self) -> None:
        self._caja.adjustSize()
        self._caja.move((self.width() - self._caja.width()) // 2, (self.height() - self._caja.height()) // 2)

    def _respirar(self) -> None:
        """El botón destructivo late despacio: recuerda que hay que leer antes de confirmar."""
        if not widgets.ANIMAR:
            return
        efecto = motion.sombra(self.btn_confirmar, "#F87171", 6, 0, 90)
        anim = QVariantAnimation(self)
        anim.setStartValue(6.0)
        anim.setEndValue(22.0)
        anim.setDuration(1500)
        anim.setLoopCount(-1)
        anim.setEasingCurve(motion.QEasingCurve.Type.InOutSine if hasattr(motion, "QEasingCurve") else motion.CURVA)
        anim.valueChanged.connect(efecto.setBlurRadius)
        anim.start()
        self._latido = anim

    def _confirmar(self) -> None:
        if self._requiere and not self.check.isChecked():
            self.aviso.setText("Marca «Entiendo» para continuar.")
            self.aviso.show()
            motion.sacudir(self._contenedor_confirmar, amplitud=8)
            return
        self.resultado = True
        self.accept()

    @classmethod
    def pedir(cls, host: QWidget, titulo: str, texto: str, verbo: str = "Confirmar",
              requiere_entendido: bool = False, peligro: bool = True, detalle: str = "") -> bool:
        """Pide la confirmación en la Isla (arriba, al centro de la ventana) y devuelve la decisión."""
        descripcion = f"{texto}\n{detalle}" if detalle else texto
        return isla.confirmar_y_esperar(titulo, descripcion, verbo, "Cancelar", peligro, requiere_entendido)

    def resizeEvent(self, evento) -> None:
        self._reubicar()
        super().resizeEvent(evento)

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(evento)


# ----------------------------------------------------------------------------- tooltip rico
class TooltipRico(QWidget):
    """Tooltip con título, cuerpo y filas de datos; aparece a los 300 ms y se puede fijar con clic."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("tooltipRico")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._host = host
        self._fijado = False
        self._ancla: QWidget | None = None
        self._ocultar = QTimer(self)
        self._ocultar.setSingleShot(True)
        self._ocultar.setInterval(160)
        self._ocultar.timeout.connect(self._quiza_ocultar)
        self._espera = QTimer(self)
        self._espera.setSingleShot(True)
        self._espera.setInterval(320)
        self._espera.timeout.connect(self._mostrar_si_sigue)
        self._proveedor: Callable[[], tuple[str, str, list[tuple[str, str]]]] | None = None
        self._widget: QWidget | None = None
        self.hide()

    def registrar(self, widget: QWidget, proveedor: Callable[[], tuple[str, str, list[tuple[str, str]]]]) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget.installEventFilter(self)

    def eventFilter(self, objeto, evento) -> bool:
        if isinstance(objeto, QWidget) and evento.type() in (QEvent.Type.Enter, QEvent.Type.Leave, QEvent.Type.MouseButtonPress):
            if evento.type() == QEvent.Type.Enter:
                self._widget = objeto
                self._espera.start()
            elif evento.type() == QEvent.Type.Leave:
                self._espera.stop()
                if not self._fijado:
                    self._ocultar.start()
            elif evento.type() == QEvent.Type.MouseButtonPress:
                self._fijado = not self._fijado
        return super().eventFilter(objeto, evento)

    def _mostrar_si_sigue(self) -> None:
        if self._widget is None or not self._widget.underMouse():
            return
        self._proveedor = getattr(self._widget, "tooltip_rico", None)
        if self._proveedor is None:
            return
        titulo, cuerpo, filas = self._proveedor()
        self.mostrar(self._widget, titulo, cuerpo, filas)

    def mostrar(self, ancla: QWidget, titulo: str, cuerpo: str, filas: list[tuple[str, str]] | None = None) -> None:
        self._ancla = ancla
        self._limpiar()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(5)
        encabezado = QLabel(titulo)
        encabezado.setObjectName("tooltipTitulo")
        lay.addWidget(encabezado)
        if cuerpo:
            texto = QLabel(cuerpo)
            texto.setObjectName("tooltipTexto")
            texto.setWordWrap(True)
            texto.setMaximumWidth(280)
            lay.addWidget(texto)
        for etiqueta, valor in filas or []:
            linea = QHBoxLayout()
            izq = QLabel(etiqueta)
            izq.setObjectName("subtitulo")
            der = QLabel(valor)
            der.setObjectName("tooltipDato")
            linea.addWidget(izq)
            linea.addStretch(1)
            linea.addWidget(der)
            lay.addLayout(linea)
        self.adjustSize()
        self._colocar()
        self.show()
        self.raise_()
        motion.desvanecer(self, 0.0, 1.0, motion.RAPIDO)

    def _colocar(self) -> None:
        if self._ancla is None:
            return
        punto = self._ancla.mapTo(self._host, QPoint(0, 0))
        x = punto.x() + self._ancla.width() // 2 - self.width() // 2
        y = punto.y() - self.height() - 10
        if y < 8:
            y = punto.y() + self._ancla.height() + 10
        x = max(8, min(self._host.width() - self.width() - 8, x))
        self.move(x, y)

    def _quiza_ocultar(self) -> None:
        if self._fijado:
            return
        if self._widget is not None and self._widget.underMouse():
            return
        motion.desvanecer(self, 1.0, 0.0, motion.RAPIDO, self.hide)

    def _limpiar(self) -> None:
        viejo = self.layout()
        if viejo is None:
            return
        while viejo.count():
            item = viejo.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._limpiar_layout(item.layout())
                item.layout().deleteLater()

    @staticmethod
    def _limpiar_layout(lay) -> None:
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                TooltipRico._limpiar_layout(item.layout())
                item.layout().deleteLater()


# ----------------------------------------------------------------------------- chips y filtros
class ChipActivo(QFrame):
    """Chip de filtro activo. Vive dentro de un ``_Hueco`` (que le reserva el espacio y el separador): entra creciendo
    desde la izquierda con fundido y una escala leve, y sale encogiéndose, desvaneciéndose y cediendo su sitio a los
    demás sin saltos."""

    quitado = pyqtSignal(str)

    def __init__(self, clave: str, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.clave = clave
        self.setObjectName("chipActivo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 6, 4)
        lay.setSpacing(6)
        etiqueta = QLabel(texto)
        etiqueta.setObjectName("chipActivoTexto")
        cerrar = QToolButton()
        cerrar.setObjectName("chipActivoCerrar")
        cerrar.setIcon(icono("x", tam=12))
        cerrar.setToolTip(t("Quitar este filtro"))
        cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        cerrar.clicked.connect(self._quitar)
        lay.addWidget(etiqueta)
        lay.addWidget(cerrar)
        self._etiqueta = etiqueta
        self._quitando = False

    def poner_texto(self, texto: str) -> None:
        motion.cruzar_texto(self._etiqueta, texto, 180)

    def _quitar(self) -> None:
        """El clic en ✕: avisa (para que quien lo creó quite el filtro) y se retira."""
        if self._quitando:
            return
        clave = self.clave
        self.retirar()
        self.quitado.emit(clave)

    def retirar(self) -> None:
        """Sale con animación (o directamente si no hay animaciones). No avisa: lo usa quien ya sabe que el filtro cayó."""
        if self._quitando:
            return
        self._quitando = True
        hueco = self.parentWidget()
        if not isinstance(hueco, _Hueco):
            self.deleteLater()
            return
        hueco.salir()


class _Hueco(QWidget):
    """Reserva el espacio de un chip (incluido el separador de 6 px), de modo que al entrar o salir el ancho crece o
    se contrae de forma continua y los vecinos se reacomodan sin un salto final."""

    SEPARADOR = 6

    def __init__(self, chip: ChipActivo, parent: QWidget) -> None:
        super().__init__(parent)
        self.chip = chip
        self.saliendo = False
        self._anim: QVariantAnimation | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, self.SEPARADOR, 0)
        lay.addWidget(chip)
        chip.setParent(self)

    def _ancho_natural(self) -> int:
        return self.chip.sizeHint().width() + self.SEPARADOR

    def entrar(self, retardo: int = 0) -> None:
        if not widgets.ANIMAR:
            return
        self.setMaximumWidth(0)
        QTimer.singleShot(retardo, self._arrancar_entrada)

    def _arrancar_entrada(self) -> None:
        if sip.isdeleted(self) or self.saliendo:
            return
        ancho = self._ancho_natural()
        efecto = motion.efecto_movimiento(self.chip, radio=13)
        efecto.set_opacidad(0.0)
        efecto.set_escala(0.88)

        def paso(v: float) -> None:
            if sip.isdeleted(self) or sip.isdeleted(efecto):
                return
            self.setMaximumWidth(max(1, int(ancho * v)))
            efecto.set_opacidad(min(1.0, v * 1.5))
            efecto.set_escala(0.88 + 0.12 * v)

        def fin() -> None:
            if sip.isdeleted(self):
                return
            self.setMaximumWidth(16777215)
            motion.soltar_efecto(self.chip, efecto)

        self._anim = motion.animar(self, 0.0, 1.0, motion.dur(motion.NORMAL), paso, fin, motion_global.resorte(1.05))

    def salir(self) -> None:
        self.saliendo = True
        motion.detener(self._anim)
        if not widgets.ANIMAR or not self.isVisible():
            self.hide()
            self.deleteLater()
            return
        ancho = max(1, self.width())
        efecto = motion.efecto_movimiento(self.chip, radio=13)

        def paso(v: float) -> None:
            if sip.isdeleted(self) or sip.isdeleted(efecto):
                return
            self.setMaximumWidth(max(0, int(ancho * (1 - v))))
            efecto.set_opacidad(1.0 - v)
            efecto.set_escala(1.0 - 0.12 * v)

        def fin() -> None:
            if not sip.isdeleted(self):
                self.hide()
                self.deleteLater()

        self._anim = motion.animar(self, 0.0, 1.0, motion.dur(motion.RAPIDO + 40), paso, fin,
                                   motion_global.SALIDA)


class FiltrosActivos(QWidget):
    """Fila de chips de filtros vigentes. Cada filtro conserva su chip mientras siga activo (si cambia su valor solo se
    cruza el texto), los nuevos entran donde les toca en el orden recibido y solo salen los que ya no están.

    La fila misma se despliega y se pliega (altura) al aparecer el primer chip y al irse el último."""

    quitado = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self._lay.addStretch(1)
        self._chips: dict[str, _Hueco] = {}
        self._quitar: dict[str, Callable[[], None]] = {}
        self.hide()

    def claves(self) -> list[str]:
        """Las claves de los chips vigentes, en el orden en que se ven (para las pruebas)."""
        return [c for c in self._orden_visual() if c in self._chips]

    def _orden_visual(self) -> list[str]:
        huecos = [self._lay.itemAt(i).widget() for i in range(self._lay.count()) if self._lay.itemAt(i).widget()]
        return [h.chip.clave for h in huecos if isinstance(h, _Hueco) and not h.saliendo]

    def actua(self, filtros: list[tuple[str, str, Callable[[], None]]]) -> None:
        """``[(clave, texto, quitar), …]``. Solo las claves nuevas entran; las que sobran salen; las demás se quedan."""
        vigentes = {c for c, _t, _q in filtros}
        for clave in list(self._chips):
            if clave not in vigentes:
                self._quitar.pop(clave, None)           # ya cayó: no hay que volver a ejecutar su acción
                self._chips.pop(clave).chip.retirar()
        nuevas = 0
        for indice, (clave, texto, quitar) in enumerate(filtros):
            self._quitar[clave] = quitar
            if clave in self._chips:
                self._chips[clave].chip.poner_texto(texto)
                continue
            chip = ChipActivo(clave, texto)
            chip.quitado.connect(self._chip_quitado)
            hueco = _Hueco(chip, self)
            self._chips[clave] = hueco
            posterior = next((self._chips[c] for c, _t, _q in filtros[indice + 1:] if c in self._chips), None)
            posicion = self._lay.indexOf(posterior) if posterior is not None else self._lay.count() - 1
            self._lay.insertWidget(posicion, hueco)
            hueco.entrar(nuevas * 28)
            nuevas += 1
        saliendo = any(self._lay.itemAt(i).widget() is not None and getattr(self._lay.itemAt(i).widget(), "saliendo", False)
                       for i in range(self._lay.count()))
        hay = bool(filtros)
        if hay:
            motion_global.desplegar(self, True, motion.dur(motion.NORMAL))
        elif saliendo and widgets.ANIMAR:
            QTimer.singleShot(motion.dur(motion.RAPIDO + 60), self._plegar_si_vacia)
        else:
            motion_global.desplegar(self, False, motion.dur(motion.NORMAL))

    def _plegar_si_vacia(self) -> None:
        if not sip.isdeleted(self) and not self._chips:
            motion_global.desplegar(self, False, motion.dur(motion.NORMAL))

    def _chip_quitado(self, clave: str) -> None:
        """El usuario pulsó ✕: se quita el filtro (el chip ya se está retirando) y se avisa."""
        self._chips.pop(clave, None)
        fn = self._quitar.pop(clave, None)
        if fn is not None:
            fn()
        self.quitado.emit(clave)


# ----------------------------------------------------------------------------- barra de lote
class BarraLote(QFrame):
    """Barra flotante que sube desde abajo cuando hay selección múltiple."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self.setObjectName("barraLote")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(14, 8, 14, 8)
        self._lay.setSpacing(8)
        self._etiqueta = QLabel("")
        self._etiqueta.setObjectName("barraLoteTexto")
        self._lay.addWidget(self._etiqueta)
        self._botones: list[QPushButton] = []
        self.hide()
        host.installEventFilter(self)
        self._ocupada = False

    def mostrar(self, cantidad: int, acciones: list[tuple[str, Callable[[], None], bool]]) -> None:
        if cantidad <= 0:
            self.ocultar()
            return
        self._etiqueta.setText(f"{cantidad} seleccionad{'o' if cantidad == 1 else 'os'}")
        for boton in self._botones:
            boton.deleteLater()
        self._botones = []
        for texto, fn, primaria in acciones:
            boton = QPushButton(texto)
            boton.setObjectName("accionLote")
            if primaria:
                boton.setProperty("primaria", True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.clicked.connect(lambda _=False, f=fn: f())
            self._lay.addWidget(boton)
            self._botones.append(boton)
        self.adjustSize()
        self._reubicar()
        self._entrar()

    def _reubicar(self) -> None:
        alto = max(46, self.sizeHint().height())
        x = (self._host.width() - self.width()) // 2
        y = self._host.height() - alto - 18
        self.setGeometry(x, y + (60 if not self.isVisible() else 0), self.width(), alto)

    def _entrar(self) -> None:
        self._reubicar()
        destino = self.y() - 60
        self.move(self.x(), destino + 60)
        self.show()
        self.raise_()
        motion.animar(self, destino + 60, destino, motion.LENTO, lambda v: self.move(self.x(), int(v)),
                      curva=motion.QEasingCurve.Type.OutBack if hasattr(motion, "QEasingCurve") else motion.CURVA)

    def ocultar(self) -> None:
        if self.isHidden():
            return
        destino = self._host.height() + 20
        motion.animar(self, self.y(), destino, motion.RAPIDO, lambda v: self.move(self.x(), int(v)), self.hide)

    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self._host and evento.type() == QEvent.Type.Resize and self.isVisible():
            self._reubicar()
        return super().eventFilter(objeto, evento)


# ----------------------------------------------------------------------------- acciones de fila
class AccionesFila(QWidget):
    """Acciones rápidas que se deslizan desde la derecha sobre la fila de una tabla."""

    def __init__(self, tabla: QAbstractItemView, acciones: list[tuple[str, str, Callable[[int], None]]]) -> None:
        super().__init__(tabla.viewport())
        self._tabla = tabla
        self.setObjectName("accionesFila")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 2, 3, 2)
        lay.setSpacing(2)
        self._botones = []
        for glifo, tip, fn in acciones:
            boton = QToolButton(self)
            boton.setObjectName("accionFila")
            boton.setText(glifo)
            boton.setToolTip(tip)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.setFixedSize(24, 24)
            boton.clicked.connect(lambda _=False, f=fn: f(self._fila))
            lay.addWidget(boton)
            self._botones.append(boton)
            boton.installEventFilter(self)
        self._fila = -1
        self.hide()
        tabla.viewport().installEventFilter(self)
        self._ocultar = QTimer(self)
        self._ocultar.setSingleShot(True)
        self._ocultar.setInterval(220)
        self._ocultar.timeout.connect(self._quiza_ocultar)
        self.adjustSize()

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() == QEvent.Type.MouseMove and objeto is self._tabla.viewport():
            indice = self._tabla.indexAt(evento.position().toPoint())
            if indice.isValid():
                if indice.row() != self._fila:
                    self._fila = indice.row()
                    self._colocar()
                self._ocultar.stop()
                self.show()
                self.raise_()
            else:
                self._ocultar.start()
        elif evento.type() == QEvent.Type.Leave and objeto is self._tabla.viewport():
            self._ocultar.start()
        elif evento.type() == QEvent.Type.Enter and isinstance(objeto, QToolButton):
            self._ocultar.stop()
        elif evento.type() == QEvent.Type.Leave and isinstance(objeto, QToolButton):
            self._ocultar.start()
        return super().eventFilter(objeto, evento)

    def _colocar(self) -> None:
        rect = self._tabla.visualRect(self._tabla.model().index(self._fila, 0))
        if not rect.isValid():
            return
        ancho, alto = self.sizeHint().width(), max(24, rect.height() - 4)
        self.resize(ancho, alto)
        self.move(max(0, self._tabla.viewport().width() - ancho - 8), rect.top() + 2)

    def _quiza_ocultar(self) -> None:
        if self.underMouse():
            return
        self.hide()
        self._fila = -1


# ----------------------------------------------------------------------------- selección / copia
def copiar_seleccion(tabla: QAbstractItemView, encabezados: list[str] | None = None) -> None:
    """Copia las filas seleccionadas como TSV y destella el área copiada."""
    modelo = tabla.model()
    if modelo is None:
        return
    filas = sorted({i.row() for i in tabla.selectionModel().selectedIndexes()})
    if not filas:
        return
    lineas = []
    if encabezados:
        lineas.append("\t".join(encabezados))
    for fila in filas:
        celdas = []
        for columna in range(modelo.columnCount()):
            indice = modelo.index(fila, columna)
            celdas.append(str(modelo.data(indice) or ""))
        lineas.append("\t".join(celdas))
    QApplication.clipboard().setText("\n".join(lineas))
    motion.destello(tabla)
