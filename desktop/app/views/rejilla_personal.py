"""Rejilla del dashboard personalizable: baldosas de tres tamaños, modo edición y reordenar arrastrando.

``colocar`` es la parte pura (qué rectángulo le toca a cada baldosa); ``RejillaPersonal`` la usa para colocar los
widgets, animarlos al cambiar de sitio y mover una baldosa mientras se arrastra, mostrando dónde caería. Los demás
widgets se apartan con una animación corta, sin saltos ni superposiciones.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPoint, QSize, QPointF, QPropertyAnimation, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QScrollArea, QToolButton, QWidget

from ..tema import colores
from . import widgets
from .iconos import icono

GAP = 14
ALTO_KPI, ALTO_PANEL = 118, 132
ALTO_GRAFICO = {"S": 250, "M": 312, "L": 366}
ALTO_LISTA = {"M": 250, "L": 312}      # paneles con lista que se desplaza (Actividad reciente)


def columnas(ancho: float) -> int:
    return 4 if ancho >= 880 else 2


def span(tam: str, cols: int) -> int:
    return min(cols, {"S": 1, "M": 2, "L": cols}.get(tam, 1))


def alto_de(tipo: str, tam: str) -> int:
    if tipo == "kpi":
        return ALTO_KPI
    if tipo == "panel":
        return ALTO_PANEL
    if tipo == "lista":
        return ALTO_LISTA.get(tam, ALTO_LISTA["M"])
    return ALTO_GRAFICO.get(tam, ALTO_GRAFICO["M"])


def colocar(especificaciones: list[tuple[int, int]], ancho: float, cols: int) -> tuple[list[QRect], int]:
    """Coloca baldosas en orden, de izquierda a derecha, saltando de fila cuando no caben.

    ``especificaciones``: ``(columnas que ocupa, alto)``. Devuelve sus rectángulos y el alto total.
    """
    cols = max(1, cols)
    ancho_col = (ancho - GAP * (cols - 1)) / cols
    rects: list[QRect] = []
    x = y = 0
    fila_alto = 0
    columna = 0
    for ocupa, alto in especificaciones:
        ocupa = max(1, min(ocupa, cols))
        if columna + ocupa > cols:
            y += fila_alto + GAP
            columna, fila_alto = 0, 0
        x = round(columna * (ancho_col + GAP))
        rects.append(QRect(x, y, round(ocupa * ancho_col + (ocupa - 1) * GAP), alto))
        columna += ocupa
        fila_alto = max(fila_alto, alto)
    return rects, (y + fila_alto if rects else 0)


class _Edicion(QWidget):
    """Capa del modo edición: contorno punteado, asa de arrastre y captura del ratón para mover la baldosa."""

    def __init__(self, baldosa: "Baldosa") -> None:
        super().__init__(baldosa)
        self._b = baldosa
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.hide()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        acento = QColor(colores()["acento"])
        relleno = QColor(acento)
        relleno.setAlpha(14)
        caja = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setBrush(relleno)
        pluma = QPen(acento, 1.5, Qt.PenStyle.DashLine)
        p.setPen(pluma)
        p.drawRoundedRect(caja, 14, 14)
        # asa: seis puntos
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(acento)
        cx, cy = caja.center().x(), caja.bottom() - 12
        for dx in (-6, 0, 6):
            for dy in (-3, 3):
                p.drawEllipse(QPointF(cx + dx, cy + dy - 6), 1.5, 1.5)
        p.end()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._b.rejilla()._arrastre_inicio(self._b, evento.globalPosition())
        evento.accept()

    def mouseMoveEvent(self, evento) -> None:
        self._b.rejilla()._arrastre_mover(evento.globalPosition())
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._b.rejilla()._arrastre_fin()
        evento.accept()


class Baldosa(QFrame):
    """Un widget del dashboard con sus controles: menú ⋯ (al pasar el cursor o en edición) y quitar (edición)."""

    menu_pedido = pyqtSignal(str)
    quitar = pyqtSignal(str)

    def __init__(self, id_: str, tipo: str, tam: str, contenido: QWidget) -> None:
        super().__init__()
        self.id, self.tipo, self.tam = id_, tipo, tam
        self.contenido = contenido
        contenido.setParent(self)
        self.setObjectName("baldosa")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._edicion = _Edicion(self)
        self.btn_menu = QToolButton(self)
        self.btn_menu.setObjectName("baldosaMenu")
        self.btn_menu.setIcon(icono("ellipsis", color=colores()["texto_suave"], tam=16))
        self.btn_menu.setIconSize(QSize(16, 16))
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.clicked.connect(lambda: self.menu_pedido.emit(self.id))
        self.btn_menu.hide()
        self.btn_quitar = QToolButton(self)
        self.btn_quitar.setObjectName("baldosaQuitar")
        self.btn_quitar.setIcon(icono("minus", color="#FFFFFF", tam=14))
        self.btn_quitar.setIconSize(QSize(14, 14))
        self.btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quitar.clicked.connect(lambda: self.quitar.emit(self.id))
        self.btn_quitar.hide()
        self._en_edicion = False
        self._anim: QPropertyAnimation | None = None

    def rejilla(self) -> "RejillaPersonal":
        return self.parentWidget()  # type: ignore[return-value]

    def set_edicion(self, si: bool) -> None:
        self._en_edicion = si
        self._edicion.setVisible(si)
        self.btn_quitar.setVisible(si)
        self.btn_menu.setVisible(si or self.underMouse())
        self._colocar_hijos()
        for boton in (self.btn_menu, self.btn_quitar):
            boton.raise_()

    def enterEvent(self, evento) -> None:
        self.btn_menu.show()
        self.btn_menu.raise_()
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self.btn_menu.setVisible(self._en_edicion)
        super().leaveEvent(evento)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._colocar_hijos()

    def _colocar_hijos(self) -> None:
        self.contenido.setGeometry(0, 0, self.width(), self.height())
        self._edicion.setGeometry(0, 0, self.width(), self.height())
        self.btn_menu.move(self.width() - self.btn_menu.sizeHint().width() - 8, 8)
        self.btn_quitar.move(self.btn_menu.x() - self.btn_quitar.sizeHint().width() - 6, 8)


class RejillaPersonal(QWidget):
    """Contenedor de baldosas con colocación automática, animación y arrastrar y soltar."""

    orden_cambiado = pyqtSignal(list)    # ids en el nuevo orden

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._baldosas: list[Baldosa] = []
        self._edicion = False
        self._arr: dict | None = None
        self._marcador = QFrame(self)
        self._marcador.setObjectName("marcadorDestino")
        self._marcador.hide()
        self._marcador.lower()

    # ------------------------------------------------------------------ contenido
    def poner(self, baldosas: list[Baldosa]) -> None:
        for b in self._baldosas:
            b.hide()
            b.deleteLater()
        self._baldosas = list(baldosas)
        for b in self._baldosas:
            b.setParent(self)
            b.show()
            b.set_edicion(self._edicion)
        self.recolocar(animar=False)

    def ids(self) -> list[str]:
        return [b.id for b in self._baldosas]

    def baldosa(self, id_: str) -> Baldosa | None:
        return next((b for b in self._baldosas if b.id == id_), None)

    def agregar(self, b: Baldosa) -> None:
        """Añade una baldosa al final (aparece con un breve fundido)."""
        b.setParent(self)
        self._baldosas.append(b)
        b.show()
        b.set_edicion(self._edicion)
        self.recolocar(animar=False)
        if widgets.ANIMAR and self.isVisible():
            from . import motion
            motion.desvanecer(b, 0.0, 1.0, 220)

    def quitar(self, id_: str) -> None:
        b = self.baldosa(id_)
        if b is None:
            return
        self._baldosas.remove(b)
        b.hide()
        b.deleteLater()
        self.recolocar(animar=True)

    def set_edicion(self, si: bool) -> None:
        self._edicion = si
        for b in self._baldosas:
            b.set_edicion(si)

    def edicion(self) -> bool:
        return self._edicion

    # ------------------------------------------------------------------ colocación
    def _cols(self) -> int:
        return columnas(self.width())

    def _spec(self, orden: list[Baldosa]) -> list[tuple[int, int]]:
        cols = self._cols()
        return [(span(b.tam, cols), alto_de(b.tipo, b.tam)) for b in orden]

    def recolocar(self, animar: bool = True) -> None:
        rects, total = colocar(self._spec(self._baldosas), self.width(), self._cols())
        self.setMinimumHeight(total)
        for b, r in zip(self._baldosas, rects):
            if self._arr and b is self._arr["b"]:
                continue
            self._mover_a(b, r, animar)

    def _mover_a(self, b: Baldosa, r: QRect, animar: bool) -> None:
        if b._anim is not None:
            b._anim.stop()
            b._anim = None
        if not animar or not widgets.ANIMAR or not self.isVisible() or b.geometry().isEmpty():
            b.setGeometry(r)
            return
        if b.geometry() == r:
            return
        anim = QPropertyAnimation(b, b"geometry", b)
        anim.setDuration(190)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(b.geometry())
        anim.setEndValue(r)
        anim.start()
        b._anim = anim

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self.recolocar(animar=False)

    def cambiar_tam(self, id_: str, tam: str) -> None:
        b = self.baldosa(id_)
        if b is not None and b.tam != tam:
            b.tam = tam
            self.recolocar(animar=True)

    def mover(self, id_: str, indice: int) -> None:
        """Pone una baldosa en otra posición (lo que hace soltar tras arrastrar; también sirve sin ratón)."""
        b = self.baldosa(id_)
        if b is None:
            return
        antes = self.ids()
        self._baldosas.remove(b)
        self._baldosas.insert(max(0, min(indice, len(self._baldosas))), b)
        self.recolocar(animar=True)
        if self.ids() != antes:
            self.orden_cambiado.emit(self.ids())

    # ------------------------------------------------------------------ arrastrar
    def _arrastre_inicio(self, b: Baldosa, global_pos: QPointF) -> None:
        local = self.mapFromGlobal(global_pos.toPoint())
        b.raise_()
        if b._anim is not None:
            b._anim.stop()
            b._anim = None
        self._arr = {"b": b, "dx": local.x() - b.x(), "dy": local.y() - b.y(), "indice": self._baldosas.index(b),
                     "origen": self.ids()}
        self._marcador.setGeometry(b.geometry())
        self._marcador.show()
        self._marcador.lower()

    def _arrastre_mover(self, global_pos: QPointF) -> None:
        if not self._arr:
            return
        b: Baldosa = self._arr["b"]
        local = self.mapFromGlobal(global_pos.toPoint())
        nuevo = QPoint(local.x() - self._arr["dx"], local.y() - self._arr["dy"])
        nuevo.setX(max(0, min(nuevo.x(), max(0, self.width() - b.width()))))
        nuevo.setY(max(0, nuevo.y()))
        b.move(nuevo)
        centro = b.geometry().center()
        otras = [x for x in self._baldosas if x is not b]
        mejor, mejor_d, mejor_rects = self._arr["indice"], None, None
        for i in range(len(otras) + 1):
            orden = otras[:i] + [b] + otras[i:]
            rects, _t = colocar(self._spec(orden), self.width(), self._cols())
            d = (rects[i].center() - centro).manhattanLength()
            if mejor_d is None or d < mejor_d:
                mejor, mejor_d, mejor_rects = i, d, rects
        self._arr["indice"] = mejor
        orden = otras[:mejor] + [b] + otras[mejor:]
        for x, r in zip(orden, mejor_rects):
            if x is b:
                self._marcador.setGeometry(r)
            else:
                self._mover_a(x, r, True)
        self._autodesplazar(global_pos)

    def _autodesplazar(self, global_pos: QPointF) -> None:
        area = self.parentWidget()
        while area is not None and not isinstance(area, QScrollArea):
            area = area.parentWidget()
        if area is None:
            return
        vista = area.viewport()
        y = vista.mapFromGlobal(global_pos.toPoint()).y()
        barra = area.verticalScrollBar()
        if y < 36:
            barra.setValue(barra.value() - 22)
        elif y > vista.height() - 36:
            barra.setValue(barra.value() + 22)

    def _arrastre_fin(self) -> None:
        if not self._arr:
            return
        b: Baldosa = self._arr["b"]
        indice = self._arr["indice"]
        origen = self._arr["origen"]
        self._arr = None
        self._marcador.hide()
        self._baldosas.remove(b)
        self._baldosas.insert(indice, b)
        self.recolocar(animar=True)
        if self.ids() != origen:
            self.orden_cambiado.emit(self.ids())
