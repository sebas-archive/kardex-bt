"""Menú flotante con movimiento: el catálogo «Añadir gráfica» y el menú ⋯ de cada baldosa.

Sustituye a ``QMenu`` donde hace falta más lenguaje de movimiento: se abre con un fundido y un desplazamiento mínimo, sus
opciones entran en una cascada corta, el hover es un fondo que aparece y se va (no salta), la opción elegida destella un
instante y el menú se retira con un fundido. La acción se entrega **de inmediato** (``elegida``): la animación es solo
presentación y nunca retrasa lo que el usuario pidió.

Sin animaciones (``APP_SIN_ANIMACIONES=1`` o movimiento reducido) todo ocurre al instante y sigue funcionando igual,
también con el teclado (↑ ↓ Intro Esc).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6 import sip
from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSize, Qt, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

from ..tema import colores
from . import widgets

MARGEN, ALTO_FILA, ALTO_TITULO, ALTO_SEP, RADIO = 12, 32, 28, 11, 12


@dataclass(frozen=True)
class Entrada:
    """Una línea del menú. ``tipo``: «opcion», «titulo» (cabecera de sección) o «separador»."""
    clave: str = ""
    texto: str = ""
    marcada: bool = False         # ✓ delante (el tamaño actual, la gráfica que ya está)
    habilitada: bool = True
    peligro: bool = False         # acción destructiva (se pinta en el color de error)
    nota: str = ""                # texto tenue a la derecha («Añadida»)
    tipo: str = "opcion"


def titulo(texto: str) -> Entrada:
    return Entrada(texto=texto, tipo="titulo", habilitada=False)


def separador() -> Entrada:
    return Entrada(tipo="separador", habilitada=False)


class MenuFlotante(QWidget):
    elegida = pyqtSignal(str)       # clave de la opción elegida (se emite al instante, antes de la salida animada)

    def __init__(self, padre: QWidget, entradas: list[Entrada], ancho_min: int = 210) -> None:
        super().__init__(padre, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setObjectName("menuFlotante")
        self._entradas = list(entradas)
        self._hov = [0.0] * len(entradas)          # realce de cada fila (0–1), con transición
        self._hov_desde = list(self._hov)
        self._hov_hasta = list(self._hov)
        self._ent = [1.0] * len(entradas)          # entrada de cada fila (0–1): cascada al abrir
        self._flash = [0.0] * len(entradas)        # destello de la fila elegida
        self._actual = -1                          # fila señalada (ratón o teclado)
        self._cerrando = False
        self._elegida: str | None = None
        fuente = QFont(self.font())
        fuente.setPixelSize(13)
        self._fuente = fuente
        metrica = QFontMetrics(fuente)
        ancho = ancho_min
        for e in self._entradas:
            if e.tipo == "opcion":
                ancho = max(ancho, 40 + metrica.horizontalAdvance(e.texto) + 24
                            + (metrica.horizontalAdvance(e.nota) + 16 if e.nota else 0))
        alto = sum({"opcion": ALTO_FILA, "titulo": ALTO_TITULO, "separador": ALTO_SEP}[e.tipo] for e in self._entradas)
        self._ancho_util, self._alto_util = ancho, alto + 12
        self.resize(self._ancho_util + 2 * MARGEN, self._alto_util + 2 * MARGEN)
        self._a_hover = QVariantAnimation(self)
        self._a_hover.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a_hover.valueChanged.connect(self._paso_hover)
        self._a_entrada = QVariantAnimation(self)
        self._a_entrada.setEasingCurve(QEasingCurve.Type.Linear)
        self._a_entrada.valueChanged.connect(self._paso_entrada)
        self._a_flash = QVariantAnimation(self)
        self._a_flash.valueChanged.connect(self._paso_flash)
        self._a_cierre = QVariantAnimation(self)
        self._a_cierre.setEasingCurve(QEasingCurve.Type.InCubic)
        self._a_cierre.valueChanged.connect(self._paso_cierre)
        self._a_cierre.finished.connect(self.close)

    # ------------------------------------------------------------------ API
    def entradas(self) -> list[Entrada]:
        return list(self._entradas)

    def esta_cerrando(self) -> bool:
        return self._cerrando

    def abrir(self, global_pos: QPoint, derecha: bool = False) -> None:
        """Abre el menú con su esquina superior izquierda (o derecha, con ``derecha``) en ``global_pos``."""
        x = global_pos.x() - (self.width() - MARGEN if derecha else MARGEN)
        y = global_pos.y() - MARGEN + 4
        pantalla = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        if pantalla is not None:
            zona = pantalla.availableGeometry()
            x = max(zona.left(), min(x, zona.right() - self.width()))
            y = max(zona.top(), min(y, zona.bottom() - self.height()))
        self.move(x, y)
        self._actual = self._primera_habilitada()
        if widgets.ANIMAR:
            self._ent = [0.0] * len(self._entradas)
            self.setWindowOpacity(0.0)
        self.show()
        if not widgets.ANIMAR:
            return
        self._a_entrada.stop()
        self._a_entrada.setDuration(widgets._ms(300))
        self._a_entrada.setStartValue(0.0)
        self._a_entrada.setEndValue(1.0)
        self._a_entrada.start()

    def elegir(self, clave: str) -> bool:
        """Elige una opción (lo mismo que pulsarla): destello, acción inmediata y salida suave. ``False`` si no se puede."""
        for i, e in enumerate(self._entradas):
            if e.tipo == "opcion" and e.clave == clave and e.habilitada:
                self._elegir(i)
                return True
        return False

    # -------------------------------------------------------------- animaciones
    def _paso_entrada(self, v) -> None:
        f = float(v)
        self.setWindowOpacity(min(1.0, f * 3.0))
        n = max(1, len(self._entradas) - 1)
        for i in range(len(self._ent)):
            u = max(0.0, min(1.0, f * 1.5 - 0.5 * (i / n)))
            self._ent[i] = 1 - (1 - u) ** 3
        self.update()

    def _paso_hover(self, v) -> None:
        f = float(v)
        self._hov = [d + (h - d) * f for d, h in zip(self._hov_desde, self._hov_hasta)]
        self.update()

    def _paso_flash(self, v) -> None:
        if self._elegida_i >= 0:
            self._flash[self._elegida_i] = float(v)
            self.update()

    def _paso_cierre(self, v) -> None:
        self.setWindowOpacity(float(v))

    def _señalar(self, i: int) -> None:
        if i == self._actual:
            return
        self._actual = i
        hasta = [1.0 if k == i else 0.0 for k in range(len(self._entradas))]
        if not widgets.ANIMAR:
            self._hov = hasta
            self.update()
            return
        self._hov_desde, self._hov_hasta = list(self._hov), hasta
        self._a_hover.stop()
        self._a_hover.setDuration(widgets._ms(130))
        self._a_hover.setStartValue(0.0)
        self._a_hover.setEndValue(1.0)
        self._a_hover.start()

    _elegida_i = -1

    def _elegir(self, i: int) -> None:
        if self._cerrando:
            return
        e = self._entradas[i]
        self._cerrando = True
        self._elegida = e.clave
        self._elegida_i = i
        self.elegida.emit(e.clave)                # la acción no espera a la animación
        if sip.isdeleted(self):
            return
        if not widgets.ANIMAR:
            self.close()
            return
        self._a_flash.stop()
        self._a_flash.setDuration(widgets._ms(220))
        self._a_flash.setStartValue(1.0)
        self._a_flash.setEndValue(0.0)
        self._a_flash.start()
        self._a_cierre.stop()
        self._a_cierre.setDuration(widgets._ms(170))
        self._a_cierre.setStartValue(self.windowOpacity())
        self._a_cierre.setEndValue(0.0)
        self._a_cierre.start()

    def cerrar_suave(self) -> None:
        if self._cerrando:
            return
        self._cerrando = True
        if not widgets.ANIMAR:
            self.close()
            return
        self._a_cierre.stop()
        self._a_cierre.setDuration(widgets._ms(140))
        self._a_cierre.setStartValue(self.windowOpacity())
        self._a_cierre.setEndValue(0.0)
        self._a_cierre.start()

    # --------------------------------------------------------------- geometría
    def _rects(self) -> list[QRectF]:
        y = MARGEN + 6.0
        rects = []
        for e in self._entradas:
            alto = {"opcion": ALTO_FILA, "titulo": ALTO_TITULO, "separador": ALTO_SEP}[e.tipo]
            rects.append(QRectF(MARGEN + 6, y, self._ancho_util - 12, alto))
            y += alto
        return rects

    def _fila_en(self, pos: QPointF) -> int:
        for i, r in enumerate(self._rects()):
            if self._entradas[i].tipo == "opcion" and r.contains(pos):
                return i
        return -1

    def _primera_habilitada(self) -> int:
        return next((i for i, e in enumerate(self._entradas) if e.tipo == "opcion" and e.habilitada), -1)

    def sizeHint(self) -> QSize:
        return self.size()

    # ------------------------------------------------------------------ eventos
    def mouseMoveEvent(self, evento) -> None:
        i = self._fila_en(evento.position())
        self._señalar(i if i >= 0 and self._entradas[i].habilitada else -1)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._actual >= 0 else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, evento) -> None:
        self._señalar(-1)

    def mouseReleaseEvent(self, evento) -> None:
        i = self._fila_en(evento.position())
        if evento.button() == Qt.MouseButton.LeftButton and i >= 0 and self._entradas[i].habilitada:
            self._elegir(i)
        evento.accept()

    def keyPressEvent(self, evento) -> None:
        tecla = evento.key()
        if tecla in (Qt.Key.Key_Escape,):
            self.cerrar_suave()
        elif tecla in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            paso = 1 if tecla == Qt.Key.Key_Down else -1
            n, i = len(self._entradas), self._actual
            for _ in range(n):
                i = (i + paso) % n
                if self._entradas[i].tipo == "opcion" and self._entradas[i].habilitada:
                    self._señalar(i)
                    break
        elif tecla in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._actual >= 0:
            self._elegir(self._actual)
        else:
            super().keyPressEvent(evento)

    # ------------------------------------------------------------------- pintado
    def paintEvent(self, _evento) -> None:
        c = colores()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        caja = QRectF(MARGEN, MARGEN, self._ancho_util, self._alto_util)
        for k in range(6, 0, -1):                              # sombra suave: capas concéntricas casi transparentes
            sombra = QColor(0, 0, 0, 7)
            p.setBrush(sombra)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(caja.adjusted(-k, -k + 3, k, k + 3), RADIO + k, RADIO + k)
        fondo = QColor(c["tarjeta"])
        p.setBrush(fondo)
        p.setPen(QPen(QColor(c["borde"]), 1.0))
        p.drawRoundedRect(caja.adjusted(0.5, 0.5, -0.5, -0.5), RADIO, RADIO)
        p.setFont(self._fuente)
        texto, suave, acento, error = QColor(c["texto"]), QColor(c["texto_suave"]), QColor(c["acento"]), QColor(c["error"])
        for i, (e, r) in enumerate(zip(self._entradas, self._rects())):
            ent = self._ent[i]
            if ent <= 0.001:
                continue
            p.save()
            p.setOpacity(ent)
            p.translate(0, (1.0 - ent) * widgets._px(6.0))
            if e.tipo == "separador":
                p.setPen(QPen(QColor(c["borde"]), 1.0))
                p.drawLine(QPointF(r.left() + 4, r.center().y()), QPointF(r.right() - 4, r.center().y()))
            elif e.tipo == "titulo":
                f = QFont(self._fuente)
                f.setPixelSize(11)
                f.setBold(True)
                p.setFont(f)
                p.setPen(suave)
                p.drawText(r.adjusted(26, 4, 0, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), e.texto)
                p.setFont(self._fuente)
            else:
                realce = self._hov[i] if e.habilitada else 0.0
                tono = error if e.peligro else acento
                if realce > 0.01 or self._flash[i] > 0.01:
                    fondo_fila = QColor(tono)
                    fondo_fila.setAlpha(int(34 * realce + 70 * self._flash[i]))
                    p.setBrush(fondo_fila)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawRoundedRect(r, 8, 8)
                color = error if e.peligro else texto
                if not e.habilitada:
                    color = QColor(suave)
                p.setPen(color)
                if e.marcada:                                   # ✓ dibujado a mano: no depende de una fuente
                    cx, cy = r.left() + 17, r.center().y()
                    marca = QPainterPath()
                    marca.moveTo(cx - 4.5, cy)
                    marca.lineTo(cx - 1.2, cy + 3.4)
                    marca.lineTo(cx + 4.8, cy - 3.6)
                    p.setPen(QPen(tono if e.habilitada else suave, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                  Qt.PenJoinStyle.RoundJoin))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawPath(marca)
                    p.setPen(color)
                p.drawText(r.adjusted(34, 0, -10, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), e.texto)
                if e.nota:
                    p.setPen(suave)
                    p.drawText(r.adjusted(0, 0, -12, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), e.nota)
            p.restore()
        p.end()
