"""Rejilla del dashboard personalizable: baldosas con tamaño S/M/L o medida propia, modo edición y reordenar arrastrando.

La medida propia sale del asa de la esquina inferior derecha (modo edición): el ancho salta de columna en columna y
el alto es libre entre un mínimo y un máximo por tipo (``dashboard_prefs.LIMITES_ALTO``).

``colocar`` es la parte pura (qué rectángulo le toca a cada baldosa); ``RejillaPersonal`` la usa para colocar los
widgets, animarlos al cambiar de sitio y mover una baldosa mientras se arrastra, mostrando dónde caería. Los demás
widgets se apartan con una animación corta, sin saltos ni superposiciones.
"""

from __future__ import annotations

from functools import partial

from PyQt6 import sip
from PyQt6.QtCore import (QEasingCurve, QPoint, QSize, QPointF, QPropertyAnimation, QRect, QRectF, Qt,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QScrollArea, QWidget

from .. import dashboard_prefs as prefs
from ..tema import colores
from . import motion, motion_global, widgets
from .iconos import icono
from .motion import ARRASTRE_C, Dur

GAP = 14
ALTO_KPI, ALTO_PANEL = 118, 132
ALTO_GRAFICO = {"S": 250, "M": 312, "L": 366}
ALTO_LISTA = {"M": 250, "L": 312}      # paneles con lista que se desplaza (Actividad reciente)


def columnas(ancho: float) -> int:
    return 4 if ancho >= 880 else 2


def span(tam: str, cols: int, propias: int = 0) -> int:
    """Columnas que ocupa: las propias (si se redimensionó con el asa) o las del tamaño S/M/L."""
    if propias:
        return min(cols, propias)
    return min(cols, {"S": 1, "M": 2, "L": cols}.get(tam, 1))


def alto_de(tipo: str, tam: str, propio: int = 0) -> int:
    if propio:
        bajo, alto = prefs.LIMITES_ALTO.get(tipo, prefs.LIMITES_ALTO["grafico"])
        return max(bajo, min(propio, alto))
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


def _ocultar_si_apagado(boton) -> None:
    if not sip.isdeleted(boton) and boton.opacity() <= 0.01:
        boton.hide()


def _fundir_boton(boton, visible: bool, ms: int = Dur.HOVER, inmediato: bool = False) -> None:
    """Muestra u oculta un control de la baldosa con un fundido (sin efectos gráficos: ``BotonFundible``)."""
    motion.detener(getattr(boton, "_fade", None))
    padre = boton.parentWidget()
    if inmediato or not widgets.ANIMAR or padre is None or not padre.isVisible():
        boton.setOpacity(1.0 if visible else 0.0)
        boton.setVisible(visible)
        return
    if visible:
        if boton.isHidden():
            boton.setOpacity(0.0)
        boton.show()
        boton.raise_()
        boton._fade = motion.animar(boton, boton.opacity(), 1.0, ms, boton.setOpacity)
    else:
        boton._fade = motion.animar(boton, boton.opacity(), 0.0, ms, boton.setOpacity,
                                    partial(_ocultar_si_apagado, boton))


class _Edicion(QWidget):
    """Capa del modo edición: contorno punteado, asa de arrastre y captura del ratón para mover la baldosa.

    Aparece y se va con un fundido (``mostrar``): al entrar al modo edición los controles se revelan sin saltos."""

    ASA = 30    # lado de la zona de redimensión, en la esquina inferior derecha

    def __init__(self, baldosa: "Baldosa") -> None:
        super().__init__(baldosa)
        self._b = baldosa
        self._redimensionando = False
        self._alfa = 0.0
        self._anim = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.hide()

    def mostrar(self, si: bool, animar_: bool = True) -> None:
        motion.detener(self._anim)
        if not animar_ or not widgets.ANIMAR or not self._b.isVisible():
            self._alfa = 1.0 if si else 0.0
            self.setVisible(si)
            self.update()
            return
        if si:
            self.show()
        self._anim = motion.animar(self, self._alfa, 1.0 if si else 0.0, motion.dur(Dur.HOVER + 80), self._paso,
                                   None if si else self._apagar)

    def _paso(self, v: float) -> None:
        self._alfa = v
        self.update()

    def _apagar(self) -> None:
        if self._alfa <= 0.01:
            self.hide()

    def _en_asa(self, pos) -> bool:
        return self._b.rejilla().redimensionable and pos.x() >= self.width() - self.ASA and pos.y() >= self.height() - self.ASA

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setOpacity(self._alfa)
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
        if self._b.rejilla().redimensionable:       # asa: tres rayas diagonales en la esquina inferior derecha
            p.setPen(QPen(acento, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            x1, y1 = caja.right() - 6, caja.bottom() - 6
            for k in (4, 9, 14):
                p.drawLine(QPointF(x1, y1 - k), QPointF(x1 - k, y1))
        p.end()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            if self._en_asa(evento.position()):
                self._redimensionando = True
                self._b.rejilla()._redim_inicio(self._b, evento.globalPosition())
            else:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self._b.rejilla()._arrastre_inicio(self._b, evento.globalPosition())
        evento.accept()

    def mouseMoveEvent(self, evento) -> None:
        if self._redimensionando:
            self._b.rejilla()._redim_mover(evento.globalPosition())
        elif evento.buttons() & Qt.MouseButton.LeftButton:
            self._b.rejilla()._arrastre_mover(evento.globalPosition())
        else:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._en_asa(evento.position())
                           else Qt.CursorShape.OpenHandCursor)
        evento.accept()

    def mouseReleaseEvent(self, evento) -> None:
        if self._redimensionando:
            self._redimensionando = False
            self._b.rejilla()._redim_fin()
        else:
            self._b.rejilla()._arrastre_fin()
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._en_asa(evento.position())
                       else Qt.CursorShape.OpenHandCursor)
        evento.accept()


class Baldosa(QFrame):
    """Un widget del dashboard con sus controles: menú ⋯ (al pasar el cursor o en edición) y quitar (edición).

    Lleva un único ``EfectoMovimiento`` (instalado solo mientras hace falta) con tres canales: entrada/salida, hover de
    la tarjeta KPI y levantar/asentar al arrastrar. Su geometría la manda la rejilla con una sola animación reutilizada."""

    menu_pedido = pyqtSignal(str)
    quitar = pyqtSignal(str)

    def __init__(self, id_: str, tipo: str, tam: str, contenido: QWidget, cols: int = 0, alto: int = 0,
                 cols_min: int = 1) -> None:
        super().__init__()
        self.id, self.tipo, self.tam = id_, tipo, tam
        self.cols, self.alto = cols, alto       # medida propia (0 = la del tamaño S/M/L)
        self.cols_min = cols_min
        self.contenido = contenido
        contenido.setParent(self)
        self.setObjectName("baldosa")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._edicion = _Edicion(self)
        self.btn_menu = widgets.BotonFundible(self)
        self.btn_menu.setObjectName("baldosaMenu")
        self.btn_menu.setIcon(icono("ellipsis", color=colores()["texto_suave"], tam=16))
        self.btn_menu.setIconSize(QSize(16, 16))
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.clicked.connect(lambda: self.menu_pedido.emit(self.id))
        self.btn_menu.hide()
        self.btn_quitar = widgets.BotonFundible(self)
        self.btn_quitar.setObjectName("baldosaQuitar")
        self.btn_quitar.setIcon(icono("minus", color="#FFFFFF", tam=14))
        self.btn_quitar.setIconSize(QSize(14, 14))
        self.btn_quitar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quitar.clicked.connect(lambda: self.quitar.emit(self.id))
        self.btn_quitar.hide()
        self._en_edicion = False
        self._anim: QPropertyAnimation | None = None      # geometría (una sola, reutilizada)
        self.destino = QRect()                            # el rectángulo que la rejilla le asignó
        self._entrada_pendiente = False                   # fuera de la pantalla: se revelará al desplazarse

    def rejilla(self) -> "RejillaPersonal":
        return self.parentWidget()  # type: ignore[return-value]

    def set_edicion(self, si: bool, animar_: bool = True) -> None:
        self._en_edicion = si
        self._colocar_hijos()
        self._edicion.mostrar(si, animar_)
        _fundir_boton(self.btn_quitar, si, inmediato=not animar_)
        _fundir_boton(self.btn_menu, si or self.underMouse(), inmediato=not animar_)
        for boton in (self.btn_menu, self.btn_quitar):
            boton.raise_()

    def enterEvent(self, evento) -> None:
        _fundir_boton(self.btn_menu, True)
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        _fundir_boton(self.btn_menu, self._en_edicion)
        super().leaveEvent(evento)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._colocar_hijos()

    def _colocar_hijos(self) -> None:
        self.contenido.setGeometry(0, 0, self.width(), self.height())
        self._edicion.setGeometry(0, 0, self.width(), self.height())
        self.btn_menu.move(self.width() - self.btn_menu.sizeHint().width() - 8, 8)
        self.btn_quitar.move(self.btn_menu.x() - self.btn_quitar.sizeHint().width() - 6, 8)


class _PildoraMedida(QWidget):
    """Etiqueta flotante con la medida mientras se redimensiona con el asa («2 × 312 px»)."""

    def __init__(self, padre: QWidget) -> None:
        super().__init__(padre)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._texto, self._alfa, self._anim = "", 0.0, None
        self.hide()

    def poner(self, texto: str, ancla: QRect) -> None:
        self._texto = texto
        fuente = QFont(self.font())
        fuente.setPixelSize(12)
        fuente.setBold(True)
        ancho = QFontMetrics(fuente).horizontalAdvance(texto) + 22
        alto = 24
        x = max(ancla.left() + 4, ancla.right() - ancho - 12)
        y = max(ancla.top() + 4, ancla.bottom() - alto - 40)
        self.setGeometry(x, y, ancho, alto)
        self.raise_()
        self.update()

    def mostrar(self, si: bool) -> None:
        motion.detener(self._anim)
        if not widgets.ANIMAR:
            self._alfa = 1.0 if si else 0.0
            self.setVisible(si)
            return
        if si:
            self.show()
            self.raise_()
        self._anim = motion.animar(self, self._alfa, 1.0 if si else 0.0, Dur.HOVER, self._paso,
                                   None if si else self._apagar)

    def _paso(self, v: float) -> None:
        self._alfa = v
        self.update()

    def _apagar(self) -> None:
        if self._alfa <= 0.01:
            self.hide()

    def paintEvent(self, _evento) -> None:
        c = colores()
        p = QPainter(self)
        p.setOpacity(self._alfa)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        caja = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fondo = QColor(c["tarjeta"])
        fondo.setAlpha(235)
        p.setBrush(fondo)
        p.setPen(QPen(QColor(c["acento"]), 1.0))
        p.drawRoundedRect(caja, 12, 12)
        fuente = QFont(self.font())
        fuente.setPixelSize(12)
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(c["texto"]))
        p.drawText(caja, int(Qt.AlignmentFlag.AlignCenter), self._texto)
        p.end()


class RejillaPersonal(QWidget):
    """Contenedor de baldosas con colocación automática, animación y arrastrar y soltar."""

    orden_cambiado = pyqtSignal(list)    # ids en el nuevo orden
    medidas_cambiadas = pyqtSignal(str, int, int)   # (id, columnas, alto): se soltó el asa de redimensión

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._baldosas: list[Baldosa] = []
        self._edicion = False
        self._arr: dict | None = None
        self._redim: dict | None = None
        self.redimensionable = False      # con asa de redimensión (solo donde se guardan las medidas propias)
        self._marcador = QFrame(self)
        self._marcador.setObjectName("marcadorDestino")
        self._op_marc = QGraphicsOpacityEffect(self._marcador)   # el marcador no tiene hijos: su efecto no se anida
        self._marcador.setGraphicsEffect(self._op_marc)
        self._anim_marc: QPropertyAnimation | None = None
        self._fade_marc = None
        self._marcador.hide()
        self._marcador.lower()
        self._pildora = _PildoraMedida(self)

    # ------------------------------------------------------------------ contenido
    def poner(self, baldosas, transicion: bool = False, antes=None) -> None:
        """Sustituye todas las baldosas. Con ``transicion`` la distribución anterior se funde hacia la nueva (sin salto).

        ``baldosas`` puede ser una lista o una función que la construye; ``antes`` (opcional) se ejecuta justo antes de
        retirar las viejas. Ambas corren **dentro** del cruce, cuando la imagen anterior ya está congelada: así quien
        reutiliza el contenido de las baldosas (las gráficas) no lo deja vacío en esa imagen."""
        def aplicar() -> None:
            if antes is not None:
                antes()
            nuevas = baldosas() if callable(baldosas) else list(baldosas)
            for b in self._baldosas:
                b.hide()
                b.deleteLater()
            self._baldosas = list(nuevas)
            for b in self._baldosas:
                b.setParent(self)
                b.show()
                b.set_edicion(self._edicion, False)
            self.recolocar(animar=False)

        if transicion and widgets.ANIMAR and self.isVisible() and self._baldosas:    # el cruce congela lo que se ve
            motion_global.cruzar_contenido(self, aplicar, Dur.ESTADO)
        else:
            aplicar()

    def ids(self) -> list[str]:
        return [b.id for b in self._baldosas]

    def baldosas(self) -> list[Baldosa]:
        return list(self._baldosas)

    def baldosa(self, id_: str) -> Baldosa | None:
        return next((b for b in self._baldosas if b.id == id_), None)

    def agregar(self, b: Baldosa) -> None:
        """Añade una baldosa al final (aparece con una entrada suave)."""
        b.setParent(self)
        self._baldosas.append(b)
        b.show()
        b.set_edicion(self._edicion, False)
        self.recolocar(animar=False)
        if widgets.ANIMAR and self.isVisible():
            motion.entrar(b, dy=10, escala=0.97, ms_=Dur.ENTRADA, radio=14)

    def quitar(self, id_: str, al_destruir=None) -> None:
        """Quita una baldosa con una salida suave y reacomoda las demás. ``al_destruir(baldosa)`` (opcional) se llama justo
        antes de destruirla: ahí quien quiera conservar su contenido (la gráfica con sus datos) lo suelta."""
        b = self.baldosa(id_)
        if b is None:
            return
        self._baldosas.remove(b)

        def terminar() -> None:
            if not sip.isdeleted(b):
                if al_destruir is not None:
                    al_destruir(b)
                b.hide()
                b.deleteLater()

        if widgets.ANIMAR and self.isVisible():
            b.setEnabled(False)          # ya no recibe clics mientras se va
            b.lower()
            self._marcador.lower()
            motion.salir(b, radio=14, al_terminar=terminar)
        else:
            terminar()
        self.recolocar(animar=True)

    def set_edicion(self, si: bool) -> None:
        self._edicion = si
        if not widgets.ANIMAR or not self.isVisible():
            for b in self._baldosas:
                b.set_edicion(si, False)
            return
        # Los controles se revelan en cascada corta (nunca más de ~150 ms de espera) y sin mover nada.
        motion_global.escalonar([partial(self._edicion_en, b, si) for b in self._baldosas], 22, 6)

    def _edicion_en(self, b: Baldosa, si: bool) -> None:
        if not sip.isdeleted(self) and not sip.isdeleted(b) and self._edicion == si and b in self._baldosas:
            b.set_edicion(si)

    def edicion(self) -> bool:
        return self._edicion

    # ------------------------------------------------------------------ colocación
    def _cols(self) -> int:
        return columnas(self.width())

    def _spec(self, orden: list[Baldosa]) -> list[tuple[int, int]]:
        cols = self._cols()
        return [(span(b.tam, cols, b.cols), alto_de(b.tipo, b.tam, b.alto)) for b in orden]

    def recolocar(self, animar: bool = True, directa: Baldosa | None = None) -> None:
        """Coloca las baldosas. ``directa``: la que el cursor está estirando; sigue al ratón sin retraso y las demás
        se apartan con una animación corta."""
        rects, total = colocar(self._spec(self._baldosas), self.width(), self._cols())
        self.setMinimumHeight(total)
        for b, r in zip(self._baldosas, rects):
            if self._arr and b is self._arr["b"]:
                b.destino = QRect(r)
                continue
            self._mover_a(b, r, animar and b is not directa)

    def _mover_a(self, b: Baldosa, r: QRect, animar: bool) -> None:
        """Lleva una baldosa a ``r``. Una sola ``QPropertyAnimation`` por baldosa, reutilizada (sin acumular objetos)
        y sin reiniciarse si ya va hacia ese mismo destino."""
        enviada = b._anim is not None and b._anim.state() == QPropertyAnimation.State.Running
        if animar and enviada and b.destino == r:
            return
        b.destino = QRect(r)
        if not animar or not widgets.ANIMAR or not self.isVisible() or b.geometry().isEmpty():
            if b._anim is not None:
                b._anim.stop()
            b.setGeometry(r)
            return
        if b.geometry() == r:
            if b._anim is not None:
                b._anim.stop()
            return
        if b._anim is None:
            b._anim = QPropertyAnimation(b, b"geometry", b)
            b._anim.setEasingCurve(QEasingCurve.Type.OutQuint)
        b._anim.stop()
        b._anim.setDuration(motion.dur(260))
        b._anim.setStartValue(b.geometry())
        b._anim.setEndValue(r)
        b._anim.start()

    def _parar(self, b: Baldosa) -> None:
        if b._anim is not None:
            b._anim.stop()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self.recolocar(animar=False)

    def cambiar_tam(self, id_: str, tam: str, reiniciar: bool = False) -> None:
        """Pone un tamaño S/M/L. Al cambiar de tamaño (o con ``reiniciar``) se descarta la medida propia."""
        b = self.baldosa(id_)
        if b is not None and (b.tam != tam or reiniciar):
            b.tam = tam
            b.cols = b.alto = 0
            self.recolocar(animar=True)

    def poner_medidas(self, id_: str, cols: int, alto: int) -> None:
        b = self.baldosa(id_)
        if b is not None and (b.cols, b.alto) != (cols, alto):
            b.cols, b.alto = cols, alto
            self.recolocar(animar=True)

    # ------------------------------------------------------------------ marcador de destino
    def _marcador_mostrar(self, r: QRect) -> None:
        motion.detener(self._fade_marc)
        self._marcador.setGeometry(r)
        if widgets.ANIMAR and not self._marcador.isVisible():
            self._op_marc.setOpacity(0.0)
            self._marcador.show()
            self._fade_marc = motion.animar(self._marcador, 0.0, 1.0, motion.dur(Dur.HOVER + 40), self._op_marc.setOpacity)
        else:
            self._op_marc.setOpacity(1.0)
            self._marcador.show()
        self._marcador.lower()

    def _marcador_a(self, r: QRect) -> None:
        """El marcador del destino se desliza (no salta) hasta el hueco donde caería la baldosa."""
        m = self._marcador
        if not widgets.ANIMAR or not m.isVisible():
            m.setGeometry(r)
            return
        corriendo = self._anim_marc is not None and self._anim_marc.state() == QPropertyAnimation.State.Running
        if corriendo and self._anim_marc.endValue() == r:
            return
        if self._anim_marc is None:
            self._anim_marc = QPropertyAnimation(m, b"geometry", self)
            self._anim_marc.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim_marc.stop()
        self._anim_marc.setDuration(motion.dur(170))
        self._anim_marc.setStartValue(m.geometry())
        self._anim_marc.setEndValue(r)
        self._anim_marc.start()

    def _marcador_ocultar(self) -> None:
        motion.detener(self._fade_marc)
        if self._anim_marc is not None:
            self._anim_marc.stop()
        if not widgets.ANIMAR or not self._marcador.isVisible():
            self._marcador.hide()
            return
        self._fade_marc = motion.animar(self._marcador, self._op_marc.opacity(), 0.0, Dur.HOVER, self._op_marc.setOpacity,
                                        self._marcador.hide)

    # ------------------------------------------------------------------ levantar y asentar (arrastre)
    def _levantar(self, b: Baldosa) -> None:
        """La baldosa se eleva un poco, crece un 2 % y proyecta una sombra: se siente «en la mano»."""
        if not widgets.ANIMAR:
            return
        efecto = motion.efecto_movimiento(b, 14)
        motion.detener(getattr(b, "_a_arrastre", None))
        dy0, esc0, som0 = efecto._dys[ARRASTRE_C], efecto._escs[ARRASTRE_C], efecto._sombras[ARRASTRE_C]

        def paso(v: float) -> None:
            if sip.isdeleted(efecto):
                return
            efecto.set_dy(dy0 + (-motion.desp(4.0) - dy0) * v, ARRASTRE_C)
            efecto.set_escala(esc0 + (1.02 - esc0) * v, ARRASTRE_C)
            efecto.set_sombra(som0 + (2.2 - som0) * v, ARRASTRE_C)

        b._a_arrastre = motion.animar(b, 0.0, 1.0, motion.dur(Dur.HOVER + 30), paso)    # type: ignore[attr-defined]

    def _asentar(self, b: Baldosa) -> None:
        """Al soltar, la baldosa recupera su tamaño con un resorte muy suave y la sombra se disuelve."""
        efecto = b.graphicsEffect()
        if not isinstance(efecto, motion.EfectoMovimiento):
            return
        motion.detener(getattr(b, "_a_arrastre", None))
        dy0, esc0, som0 = efecto._dys[ARRASTRE_C], efecto._escs[ARRASTRE_C], efecto._sombras[ARRASTRE_C]

        def paso(v: float) -> None:
            if sip.isdeleted(efecto):
                return
            efecto.set_dy(dy0 * (1 - v), ARRASTRE_C)
            efecto.set_escala(esc0 + (1.0 - esc0) * v, ARRASTRE_C)
            efecto.set_sombra(som0 * (1 - v), ARRASTRE_C)

        def fin() -> None:
            if sip.isdeleted(efecto):
                return
            efecto.set_dy(0.0, ARRASTRE_C)
            efecto.set_escala(1.0, ARRASTRE_C)
            efecto.set_sombra(0.0, ARRASTRE_C)
            motion.soltar_efecto(b, efecto)

        b._a_arrastre = motion.animar(b, 0.0, 1.0, motion.dur(Dur.ESTADO), paso, fin,
                                      motion.curva_resorte(1.0 if motion.reducido() else 1.3))   # type: ignore[attr-defined]

    # ------------------------------------------------------------------ redimensionar con el asa
    def _redim_inicio(self, b: Baldosa, global_pos: QPointF) -> None:
        b.raise_()
        self._parar(b)
        self._redim = {"b": b, "g": global_pos, "ancho": b.width(), "alto": b.height()}
        self._pildora.poner(self._texto_medida(b), b.geometry())
        self._pildora.mostrar(True)

    def _texto_medida(self, b: Baldosa) -> str:
        return f"{span(b.tam, self._cols(), b.cols)} × {alto_de(b.tipo, b.tam, b.alto)} px"

    def _redim_mover(self, global_pos: QPointF) -> None:
        r = getattr(self, "_redim", None)
        if not r:
            return
        b: Baldosa = r["b"]
        cols = self._cols()
        ancho_col = (self.width() - GAP * (cols - 1)) / cols
        dx, dy = global_pos.x() - r["g"].x(), global_pos.y() - r["g"].y()
        ocupa = round((r["ancho"] + dx + GAP) / (ancho_col + GAP))     # el ancho salta de columna en columna
        b.cols = max(min(b.cols_min, cols), min(ocupa, cols))
        bajo, alto_max = prefs.LIMITES_ALTO.get(b.tipo, prefs.LIMITES_ALTO["grafico"])
        b.alto = max(bajo, min(round(r["alto"] + dy), alto_max))          # el alto es libre al píxel
        self.recolocar(animar=True, directa=b)                            # ella sigue al ratón; las demás se apartan
        self._pildora.poner(self._texto_medida(b), b.geometry())

    def _redim_fin(self) -> None:
        r = getattr(self, "_redim", None)
        self._redim = None
        self._pildora.mostrar(False)
        if r:
            self.medidas_cambiadas.emit(r["b"].id, r["b"].cols, r["b"].alto)

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
        self._parar(b)
        self._arr = {"b": b, "dx": local.x() - b.x(), "dy": local.y() - b.y(), "indice": self._baldosas.index(b),
                     "origen": self.ids(), "levantada": False}
        self._marcador_mostrar(b.geometry())

    def _arrastre_mover(self, global_pos: QPointF) -> None:
        if not self._arr:
            return
        b: Baldosa = self._arr["b"]
        if not self._arr["levantada"]:           # se levanta al empezar a moverse, no con un simple clic
            self._arr["levantada"] = True
            self._levantar(b)
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
                self._marcador_a(r)
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
        levantada = self._arr["levantada"]
        self._arr = None
        self._marcador_ocultar()
        self._baldosas.remove(b)
        self._baldosas.insert(indice, b)
        self.recolocar(animar=True)      # la baldosa se desliza al hueco mientras el resorte la asienta
        if levantada:
            self._asentar(b)
        if self.ids() != origen:
            self.orden_cambiado.emit(self.ids())
