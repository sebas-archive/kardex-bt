"""Capas flotantes dentro de la ventana principal (overlays al estilo de los paneles de macOS).

Una ``CapaFlotante`` es un widget hijo de la ventana que cubre toda su área: oscurece el fondo con un velo sutil,
dibuja la sombra de su panel y lo muestra centrado. No es una ventana del sistema. Se apilan: la última que se abre
queda arriba y recibe el teclado y el ratón; las de abajo siguen intactas (datos, selección y desplazamiento).

Las animaciones usan una foto del panel (``grab``) que se escala, se mueve y se desvanece: es barato aunque el
panel lleve una tabla con miniaturas. Al terminar se muestra el panel real.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QEasingCurve, QEvent, QPointF, QRect, QRectF, QSize, QSizeF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter, QPainterPath, QPixmap, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget

from . import widgets

SOMBRA = 36
ESCALA_INICIAL = 0.955
DESPLAZAMIENTO = 14


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class CapaFlotante(QWidget):
    """Velo + sombra + panel centrado, dentro de ``ventana``. ``cerrada`` se emite al terminar de cerrarse."""

    cerrada = pyqtSignal()

    def __init__(self, ventana: QWidget, panel: QWidget, *, area: str = "contenido",
                 tamano: Callable[[QRect], QSize] | None = None, oscuridad: float = 0.30, radio: int = 18,
                 origen: QRect | None = None, cerrar_al_clic: bool = True) -> None:
        super().__init__(ventana)
        self._ventana = ventana
        self.panel = panel
        self._area_tipo = area
        self._tamano = tamano
        self._oscuridad = oscuridad
        self._radio = radio
        self._origen = origen
        self._cerrar_al_clic = cerrar_al_clic
        self._estado = "nueva"             # nueva -> abriendo -> abierta -> cerrando -> cerrada
        self._p = 0.0                      # presencia 0..1 (velo, sombra y panel)
        self._foto = QPixmap()
        self._anim = None
        self._foco_previo: QWidget | None = None
        self.setObjectName("capaFlotante")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        panel.setParent(self)
        panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        panel.hide()
        if hasattr(panel, "cerrar_pedido"):
            panel.cerrar_pedido.connect(self.cerrar)
        # Escape cierra la capa de arriba: la que tiene el foco (el visor, si está abierto; si no, las lecturas).
        self._escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._escape.activated.connect(self.cerrar)
        ventana.installEventFilter(self)
        self.setGeometry(ventana.rect())
        self.hide()

    # ------------------------------------------------------------- geometría
    def _area(self) -> QRect:
        if self._area_tipo == "contenido":
            area = getattr(self._ventana, "area_contenido", None)
            if callable(area):
                r = area()
                if r.width() > 200 and r.height() > 200:
                    return r
        return self._ventana.rect()

    def rect_panel(self) -> QRect:
        area = self._area()
        if self._tamano is not None:
            tam = self._tamano(area)
        else:
            tam = QSize(min(1080, int(area.width() * 0.92)), min(720, int(area.height() * 0.90)))
        w = max(320, min(tam.width(), self._ventana.width() - 16))
        h = max(240, min(tam.height(), self._ventana.height() - 16))
        r = QRect(0, 0, w, h)
        r.moveCenter(area.center())
        # Siempre dentro de la ventana.
        limites = self._ventana.rect().adjusted(8, 8, -8, -8)
        r.moveLeft(max(limites.left(), min(r.left(), limites.right() - r.width() + 1)))
        r.moveTop(max(limites.top(), min(r.top(), limites.bottom() - r.height() + 1)))
        return r

    def _acomodar(self) -> None:
        self.setGeometry(self._ventana.rect())
        if self._estado == "abierta":
            self.panel.setGeometry(self.rect_panel())

    def eventFilter(self, obj, evento) -> bool:
        if obj is self._ventana and evento.type() == QEvent.Type.Resize:
            self._acomodar()
        return False

    # ------------------------------------------------------------- abrir y cerrar
    def esta_abierta(self) -> bool:
        return self._estado in ("abriendo", "abierta")

    def abrir(self) -> None:
        if self._estado != "nueva":
            return
        self._foco_previo = QApplication.focusWidget()
        self.setGeometry(self._ventana.rect())
        self.show()
        self.raise_()
        self._subir_isla()
        final = self.rect_panel()
        self.panel.setGeometry(final)
        if not widgets.ANIMAR:
            self._terminar_apertura()
            return
        self.panel.show()
        self._foto = self.panel.grab()
        self.panel.hide()
        self._estado = "abriendo"
        self._p = 0.0
        self.setFocus()
        self._animar(0.0, 1.0, 300, QEasingCurve.Type.OutCubic, self._terminar_apertura)

    def cerrar(self) -> None:
        if self._estado in ("cerrando", "cerrada"):
            return
        if self._estado == "nueva" or not widgets.ANIMAR or not self.isVisible():
            self._finalizar()
            return
        self._detener()
        if self._estado == "abierta":
            self.panel.setGeometry(self.rect_panel())
            self._foto = self.panel.grab()
        self.panel.hide()
        self._estado = "cerrando"
        self.setFocus()
        self._animar(self._p, 0.0, 210, QEasingCurve.Type.InCubic, self._finalizar)

    def _terminar_apertura(self) -> None:
        self._anim = None
        self._estado = "abierta"
        self._p = 1.0
        self._foto = QPixmap()
        self.panel.setGeometry(self.rect_panel())
        self.panel.show()
        self.panel.raise_()
        self.panel.setFocus()
        self.update()

    def _finalizar(self) -> None:
        self._detener()
        self._estado = "cerrada"
        self._p = 0.0
        self.hide()
        self._ventana.removeEventFilter(self)
        self._devolver_foco()
        self.cerrada.emit()
        self.deleteLater()

    def _devolver_foco(self) -> None:
        """El foco vuelve a la capa que quedó debajo (o al widget que lo tenía antes de abrir)."""
        otras = [c for c in self._ventana.findChildren(CapaFlotante) if c is not self and c.esta_abierta()]
        try:
            if otras:
                otras[-1].panel.setFocus()
            elif self._foco_previo is not None:
                self._foco_previo.setFocus()
        except RuntimeError:
            pass

    def _subir_isla(self) -> None:
        # La cápsula de la Isla (avisos) sigue por encima de cualquier capa.
        from .isla import gestor
        capsula = getattr(gestor(), "_capsula", None)
        try:
            if capsula is not None and capsula.isVisible():
                capsula.raise_()
        except RuntimeError:
            pass

    # ------------------------------------------------------------- animación
    def _detener(self) -> None:
        widgets._detener(self._anim)
        self._anim = None

    def _animar(self, desde: float, hasta: float, ms: int, curva, al_terminar) -> None:
        def paso(v: float) -> None:
            self._p = v
            self.update()

        self._anim = widgets.animar(self, desde, hasta, ms, paso, al_terminar, curva)

    # ------------------------------------------------------------- pintura
    def _sombra(self, p: QPainter, r: QRectF, k: float) -> None:
        for i in range(SOMBRA, 0, -3):
            ruta = QPainterPath()
            caja = r.adjusted(-i, -i + 10, i, i + 10)
            ruta.addRoundedRect(caja, self._radio + i, self._radio + i)
            p.fillPath(ruta, QColor(0, 0, 0, int(30 * k * (1 - i / SOMBRA) ** 2)))

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        t = max(0.0, min(1.0, self._p))
        p.fillRect(self.rect(), QColor(0, 0, 0, round(255 * self._oscuridad * t)))
        final = QRectF(self.rect_panel())
        if self._estado == "abierta":
            self._sombra(p, final, 1.0)
            return
        if self._foto.isNull():
            return
        if self._origen is not None and self._estado == "abriendo":
            ini = QRectF(self._ventana.mapFromGlobal(self._origen.topLeft()).toPointF(), QSizeF(self._origen.size()))
            e = t
            r = QRectF(_lerp(ini.x(), final.x(), e), _lerp(ini.y(), final.y(), e),
                       _lerp(ini.width(), final.width(), e), _lerp(ini.height(), final.height(), e))
            opacidad = min(1.0, t * 2.4)
        else:
            escala = _lerp(ESCALA_INICIAL, 1.0, t)
            ancho, alto = final.width() * escala, final.height() * escala
            centro = final.center() + QPointF(0, (1 - t) * DESPLAZAMIENTO)
            r = QRectF(centro.x() - ancho / 2, centro.y() - alto / 2, ancho, alto)
            opacidad = t
        self._sombra(p, r, t)
        p.setOpacity(opacidad)
        p.drawPixmap(r, self._foto, QRectF(self._foto.rect()))

    # ------------------------------------------------------------- ratón y teclado
    def mousePressEvent(self, evento) -> None:
        evento.accept()
        if (self._estado == "abierta" and self._cerrar_al_clic and evento.button() == Qt.MouseButton.LeftButton
                and not self.panel.geometry().contains(evento.position().toPoint())):
            self.cerrar()

    def mouseReleaseEvent(self, evento) -> None:
        evento.accept()

    def mouseDoubleClickEvent(self, evento) -> None:
        evento.accept()

    def mouseMoveEvent(self, evento) -> None:
        evento.accept()

    def wheelEvent(self, evento) -> None:
        evento.accept()

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.cerrar()
            return
        super().keyPressEvent(evento)


def abrir_capa(ventana: QWidget, panel: QWidget, **opciones) -> CapaFlotante:
    """Crea la capa sobre ``ventana`` con ``panel`` y la abre."""
    capa = CapaFlotante(ventana, panel, **opciones)
    capa.abrir()
    return capa


def superficie(p: QPainter, rect: QRectF, color: str, borde: str, radio: float = 18) -> None:
    """Fondo redondeado de un panel (lo usan lecturas, detalle y visor)."""
    ruta = QPainterPath()
    ruta.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radio, radio)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.fillPath(ruta, QColor(color))
    p.setPen(QColor(borde))
    p.drawPath(ruta)
