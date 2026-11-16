"""Piezas visuales compartidas: tarjetas con cifras que cuentan, anillos, barras, pasos, avisos y transiciones.

Regla de todas: el **dato** queda disponible de inmediato (``texto()``, ``valor()``…) y solo el dibujo se anima.
Así una prueba o un refresco nunca dependen de que una animación haya terminado. ``ANIMAR`` las apaga todas
(variable de entorno ``APP_SIN_ANIMACIONES=1``): lo usan las pruebas y las capturas de pantalla.
"""

from __future__ import annotations

import os
from typing import Callable

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from .. import tema
from .. import i18n

ANIMAR = os.environ.get("APP_SIN_ANIMACIONES") != "1"

# Paleta (la misma familia de colores de la app del celular). ``refrescar_paleta`` la pone al día con el tema.
VERDE, VERDE_OSCURO = "#10B981", "#0B8A62"
TINTA, TINTA_SUAVE, LINEA, FONDO, PISTA = "#EDEDED", "#8A8A8A", "#2E2E2E", "#0A0A0A", "#1F1F1F"


def refrescar_paleta() -> None:
    """Actualiza los colores que se usan al pintar a mano (se llama al aplicar un tema)."""
    global VERDE, VERDE_OSCURO, TINTA, TINTA_SUAVE, LINEA, FONDO, PISTA
    c = tema.colores()
    VERDE, VERDE_OSCURO = c["acento"], c["acento_suave"]
    TINTA, TINTA_SUAVE = c["texto"], c["texto_suave"]
    LINEA, FONDO, PISTA = c["borde"], c["fondo"], c["tarjeta_alt"]
COLOR_CLASIFICACION = {"OK": "#12B76A", "FALTANTE": "#F04438", "SOBRANTE": "#F79009", "SIN_CONTAR": "#98A2B3"}
NOMBRE_CLASIFICACION = {"OK": "OK", "FALTANTE": "Faltante", "SOBRANTE": "Sobrante", "SIN_CONTAR": "Sin contar"}


def animar(dueno: QWidget, inicio: float, fin: float, ms: int, al_cambiar: Callable[[float], None],
           al_terminar: Callable[[], None] | None = None,
           curva: QEasingCurve.Type = QEasingCurve.Type.OutCubic) -> QVariantAnimation | None:
    """Lleva un número de ``inicio`` a ``fin`` llamando a ``al_cambiar``. Sin animaciones, salta al final."""
    if not ANIMAR or ms <= 0:
        al_cambiar(fin)
        if al_terminar:
            al_terminar()
        return None
    anim = QVariantAnimation(dueno)
    anim.setStartValue(float(inicio))
    anim.setEndValue(float(fin))
    anim.setDuration(ms)
    anim.setEasingCurve(curva)
    anim.valueChanged.connect(lambda v: al_cambiar(float(v)))
    if al_terminar:
        anim.finished.connect(al_terminar)
    anim.finished.connect(anim.deleteLater)
    anim.start()
    return anim


def _detener(anim: QVariantAnimation | None) -> None:
    if anim is not None:
        try:
            anim.stop()
        except RuntimeError:  # ya la borró Qt al terminar
            pass


class TarjetaKpi(QFrame):
    """Tarjeta de un indicador: título y una cifra que cuenta hasta su valor.

    Al pasar el mouse la cifra se voltea y muestra el detalle desglosado (``set_detalle``), la tarjeta se eleva y un
    clic avisa para abrir el panel lateral. El dato final (``texto``) está disponible aunque el dibujo esté animado.
    """

    clicked = pyqtSignal()

    def __init__(self, titulo: str, color: str = VERDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._final, self._numero, self._anim = "—", 0.0, None
        self._detalle_texto = ""
        self._volteada = False
        self._anim_volteo = None
        self._titulo = QLabel(titulo)
        self._titulo.setObjectName("cardTitulo")
        self._valor = QLabel("—")
        self._valor.setObjectName("cardValor")
        self._valor.setMinimumHeight(34)
        self._detalle = QLabel("")
        self._detalle.setObjectName("cardDetalle")
        self._detalle.setMinimumHeight(34)
        self._detalle.setWordWrap(True)
        self._detalle.hide()
        self._pista = QLabel("↗  Ver detalle")
        self._pista.setObjectName("cardPista")
        self._pista.hide()
        self._op_valor = QGraphicsOpacityEffect(self._valor)
        self._valor.setGraphicsEffect(self._op_valor)
        self._op_detalle = QGraphicsOpacityEffect(self._detalle)
        self._detalle.setGraphicsEffect(self._op_detalle)
        self._op_detalle.setOpacity(0.0)
        self._capa = QStackedLayout()
        self._capa.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self._capa.addWidget(self._valor)
        self._capa.addWidget(self._detalle)
        texto = QVBoxLayout()
        texto.setSpacing(2)
        for w in (self._titulo,):
            texto.addWidget(w)
        texto.addLayout(self._capa)
        texto.addWidget(self._pista)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.addLayout(texto, 1)
        if color != VERDE:  # solo las cifras con significado (faltante, sobrante) llevan color
            self._valor.setStyleSheet(f"color: {color};")

    def texto(self) -> str:
        """El valor final, aunque la cifra todavía esté contando."""
        return self._final

    def texto_visible(self) -> str:
        return self._valor.text()

    def detalle(self) -> str:
        return self._detalle_texto

    def _normalizar(self) -> None:
        """Si el cursor ya no está encima, la tarjeta vuelve a mostrar la cifra.

        Qt no manda ``leaveEvent`` cuando la tarjeta se reubica o se oculta bajo el cursor (p. ej. al agregarla con el
        catálogo abierto): sin esto la cifra se quedaba a opacidad 0 para siempre.
        """
        if self.underMouse():
            return
        _detener(self._anim_volteo)
        self._volteada = False
        self._detalle.setVisible(False)
        self._op_detalle.setOpacity(0.0)
        self._op_valor.setOpacity(1.0)
        self._pista.hide()

    def set_detalle(self, texto: str) -> None:
        self._detalle_texto = texto
        self._detalle.setText(texto)
        self._detalle.setVisible(self._volteada and bool(texto))
        self._normalizar()

    def set_texto(self, texto: str) -> None:
        self._normalizar()
        _detener(self._anim)
        self._final, self._numero = texto, 0.0
        self._valor.setText(texto)

    def set_valor(self, numero: float | None, formato: Callable[[float], str]) -> None:
        """Muestra ``formato(numero)`` contando desde la cifra anterior; ``None`` deja «—»."""
        if numero is None:
            self.set_texto("—")
            return
        self._normalizar()
        _detener(self._anim)
        self._final = formato(numero)
        inicio, self._numero = self._numero, float(numero)
        if self._final == self._valor.text():
            return
        self._anim = animar(self, inicio, float(numero), 650, lambda v: self._valor.setText(formato(v)),
                            lambda: self._valor.setText(self._final))

    # ------------------------------------------------------------------ hover y clic
    def enterEvent(self, evento) -> None:
        self.setProperty("hover", True)
        self.style().unpolish(self)
        self.style().polish(self)
        # Sin QGraphicsDropShadowEffect aquí: el hover ya cambia borde/fondo por QSS y este widget tiene
        # efectos de opacidad en sus hijos; anidar efectos provoca avisos de QPainter y artefactos.
        if not ANIMAR:
            self._voltear(True)
        else:
            _detener(self._anim_volteo)
            self._anim_volteo = animar(self, 0.0, 1.0, 220, lambda v: self._mezclar(v, True))
        self._pista.setVisible(bool(self._detalle_texto))
        super().enterEvent(evento)

    def leaveEvent(self, evento) -> None:
        self.setProperty("hover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._pista.hide()
        if not ANIMAR:
            self._voltear(False)
        else:
            _detener(self._anim_volteo)
            self._anim_volteo = animar(self, 0.0, 1.0, 220, lambda v: self._mezclar(v, False))
        super().leaveEvent(evento)

    def _mezclar(self, v: float, hacia_detalle: bool) -> None:
        """Volteo 2D: la cifra se desvanece mientras el detalle aparece (sin bloquear el dato)."""
        hay = bool(self._detalle_texto)
        self._detalle.setVisible(hay)
        if hacia_detalle and not hay:
            self._op_valor.setOpacity(1.0)            # sin detalle que mostrar, la cifra nunca se desvanece
            self._op_detalle.setOpacity(0.0)
        elif hacia_detalle:
            self._op_valor.setOpacity(max(0.0, 1.0 - v))
            self._op_detalle.setOpacity(v if hay else 0.0)
        else:
            self._op_valor.setOpacity(v)
            self._op_detalle.setOpacity(max(0.0, 1.0 - v) if hay else 0.0)

    def _voltear(self, hacia_detalle: bool) -> None:
        self._volteada = hacia_detalle and bool(self._detalle_texto)
        self._detalle.setVisible(self._volteada)
        self._op_detalle.setOpacity(1.0 if self._volteada else 0.0)
        self._op_valor.setOpacity(0.0 if self._volteada else 1.0)

    def hideEvent(self, evento) -> None:
        self._normalizar()
        super().hideEvent(evento)

    def mouseReleaseEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(evento)


class Anillo(QWidget):
    """Anillo de porcentaje (0–100) que se llena hasta su valor, con la cifra en el centro."""

    def __init__(self, titulo: str, color: str = VERDE, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._titulo, self._color = titulo, QColor(color)
        self._valor: float | None = None
        self._visible, self._anim = 0.0, None
        self.setMinimumSize(170, 210)

    def valor(self) -> float | None:
        return self._valor

    def valor_visible(self) -> float:
        return self._visible

    def set_valor(self, valor: float | None) -> None:
        _detener(self._anim)
        self._valor = None if valor is None else float(valor)
        self._anim = animar(self, self._visible, self._valor or 0.0, 800, self._pintar_hasta)

    def _pintar_hasta(self, v: float) -> None:
        self._visible = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.width() - 24, self.height() - 52, 200)
        grosor = max(10.0, lado * 0.11)
        # El trazo se dibuja centrado en el borde de la caja: se deja medio grosor de margen para que no se recorte.
        caja = QRectF((self.width() - lado) / 2, 10 + grosor / 2, lado, lado)
        p.setPen(QPen(QColor(PISTA), grosor, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(caja, 0, 360 * 16)
        if self._valor is not None and self._visible > 0:
            p.setPen(QPen(self._color, grosor, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(caja, 90 * 16, -int(360 * 16 * min(self._visible, 100.0) / 100.0))
        p.setPen(QColor(TINTA))
        fuente = QFont(self.font())
        fuente.setPixelSize(int(lado * 0.2))
        fuente.setBold(True)
        p.setFont(fuente)
        texto = "—" if self._valor is None else i18n.porcentaje(self._visible)
        p.drawText(caja, Qt.AlignmentFlag.AlignCenter, texto)
        fuente.setPixelSize(13)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(TINTA_SUAVE))
        p.drawText(QRectF(0, caja.bottom() + grosor / 2 + 8, self.width(), 22), Qt.AlignmentFlag.AlignCenter, self._titulo)


class BarraSegmentada(QWidget):
    """Una barra partida en segmentos proporcionales (crece de izquierda a derecha) con su leyenda debajo.

    Al hacer clic en una entrada de la leyenda se oculta o muestra esa serie (con atenuación de la leyenda).
    """

    alternada = pyqtSignal(str)

    def __init__(self, colores: dict[str, str], nombres: dict[str, str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._colores, self._nombres = colores, nombres or {}
        self._segmentos: list[tuple[str, int]] = []
        self._avance, self._anim = 1.0, None
        self._ocultas: set[str] = set()
        self._leyenda: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(58)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def segmentos(self) -> list[tuple[str, int]]:
        return list(self._segmentos)

    def set_segmentos(self, segmentos: list[tuple[str, int]]) -> None:
        cambio = segmentos != self._segmentos
        self._segmentos = list(segmentos)
        if cambio:
            _detener(self._anim)
            self._anim = animar(self, 0.0, 1.0, 700, self._pintar_hasta)
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho, alto = self.width(), 16
        fondo = QPainterPath()
        fondo.addRoundedRect(QRectF(0, 4, ancho, alto), 8, 8)
        p.fillPath(fondo, QColor(PISTA))
        visibles = [(c, n) for c, n in self._segmentos if c not in self._ocultas]
        total = sum(n for _, n in visibles)
        if total > 0:
            p.setClipPath(fondo)
            x = 0.0
            for clave, n in visibles:
                tramo = ancho * n / total * self._avance
                p.fillRect(QRectF(x, 4, tramo, alto), QColor(self._colores.get(clave, VERDE)))
                x += tramo
            p.setClipping(False)
        fuente = QFont(self.font())
        fuente.setPixelSize(12)
        p.setFont(fuente)
        self._leyenda = []
        x = 0.0
        for clave, n in self._segmentos:
            oculta = clave in self._ocultas
            tono = QColor(self._colores.get(clave, VERDE))
            if oculta:
                tono.setAlpha(70)
            p.setBrush(tono)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x + 5, 40), 5, 5)
            p.setPen(QColor(TINTA_SUAVE if oculta else TINTA))
            texto = f"{self._nombres.get(clave, clave)}  {n}"
            ancho_texto = p.fontMetrics().horizontalAdvance(texto)
            p.drawText(QRectF(x + 15, 30, 200, 20), Qt.AlignmentFlag.AlignVCenter, texto)
            self._leyenda.append((QRectF(x, 28, 18 + ancho_texto, 24), clave))
            x += 28 + ancho_texto


class Dona(QWidget):
    """Gráfica de dona: los sectores se abren en abanico hasta su tamaño; el total va en el centro."""

    def __init__(self, colores: dict[str, str], nombres: dict[str, str] | None = None, parent: QWidget | None = None,
                 unidad: str = "SKU") -> None:
        super().__init__(parent)
        self._colores, self._nombres, self._unidad = colores, nombres or {}, unidad
        self._datos: list[tuple[str, float]] = []
        self._avance, self._anim = 1.0, None
        self._ocultas: set[str] = set()
        self._leyenda: list[tuple[QRectF, str]] = []
        self.setMinimumHeight(230)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.alternada = pyqtSignal(str)

    def datos(self) -> list[tuple[str, float]]:
        return list(self._datos)

    def set_datos(self, datos: list[tuple[str, float]]) -> None:
        cambio = datos != self._datos
        self._datos = list(datos)
        if cambio:
            _detener(self._anim)
            self._anim = animar(self, 0.0, 1.0, 850, self._pintar_hasta)
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = min(self.height() - 20, self.width() * 0.42)
        caja = QRectF(16, (self.height() - lado) / 2, lado, lado)
        grosor = lado * 0.2
        aro = caja.adjusted(grosor / 2, grosor / 2, -grosor / 2, -grosor / 2)
        visibles = [(c, v) for c, v in self._datos if c not in self._ocultas]
        total = sum(v for _, v in visibles)
        p.setPen(QPen(QColor(PISTA), grosor))
        p.drawArc(aro, 0, 360 * 16)
        angulo = 90.0
        if total > 0:
            for clave, v in visibles:
                barrido = 360.0 * v / total * self._avance
                p.setPen(QPen(QColor(self._colores.get(clave, VERDE)), grosor, cap=Qt.PenCapStyle.FlatCap))
                p.drawArc(aro, int(angulo * 16), -int(barrido * 16))
                angulo -= barrido
        fuente = QFont(self.font())
        fuente.setPixelSize(int(lado * 0.2))
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(TINTA))
        p.drawText(caja.adjusted(0, -8, 0, -8), Qt.AlignmentFlag.AlignCenter, f"{total * self._avance:.0f}")
        fuente.setPixelSize(12)
        fuente.setBold(False)
        p.setFont(fuente)
        p.setPen(QColor(TINTA_SUAVE))
        p.drawText(caja.adjusted(0, lado * 0.2, 0, lado * 0.2), Qt.AlignmentFlag.AlignCenter, self._unidad)
        # Leyenda a la derecha, con el porcentaje de cada sector.
        x, y = caja.right() + 24, caja.top() + max(0.0, (lado - 28 * len(self._datos)) / 2)
        fuente.setPixelSize(13)
        p.setFont(fuente)
        self._leyenda = []
        for clave, v in self._datos:
            oculta = clave in self._ocultas
            tono = QColor(self._colores.get(clave, VERDE))
            if oculta:
                tono.setAlpha(70)
            p.setBrush(tono)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x, y + 4, 12, 12), 3, 3)
            p.setPen(QColor(TINTA_SUAVE if oculta else TINTA))
            pct = f"{100 * v / total:.0f} %" if total > 0 else "—"
            p.drawText(QRectF(x + 20, y, self.width() - x - 24, 20), Qt.AlignmentFlag.AlignVCenter,
                       f"{self._nombres.get(clave, clave)}  ·  {v:.0f}  ({pct})")
            self._leyenda.append((QRectF(x, y, max(40, self.width() - x - 20), 24), clave))
            y += 28

    def mousePressEvent(self, evento) -> None:
        for caja, clave in self._leyenda:
            if caja.contains(evento.position()):
                if clave in self._ocultas:
                    self._ocultas.discard(clave)
                else:
                    self._ocultas.add(clave)
                self.alternada.emit(clave)
                self.update()
                evento.accept()
                return
        super().mousePressEvent(evento)


class MapaUbicaciones(QWidget):
    """Mapa de calor de las ubicaciones: una fila por zona y una celda por ubicación, más intensa cuanto más se contó."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._datos: list[tuple[str, str, int]] = []
        self._avance, self._anim = 1.0, None
        self.setMinimumHeight(170)

    def datos(self) -> list[tuple[str, str, int]]:
        return list(self._datos)

    def set_datos(self, datos: list[tuple[str, str, int]]) -> None:
        cambio = datos != self._datos
        self._datos = list(datos)
        zonas = len({z for _, z, _ in datos})
        self.setMinimumHeight(max(170, 30 + 62 * zonas))
        if cambio:
            _detener(self._anim)
            self._anim = animar(self, 0.0, 1.0, 700, self._pintar_hasta)
        self.update()

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        por_zona: dict[str, list[tuple[str, int]]] = {}
        for cod, zona, skus in self._datos:
            por_zona.setdefault(zona, []).append((cod, skus))
        if not por_zona:
            return
        maximo = max((s for _, _, s in self._datos), default=0) or 1
        columnas = max(len(v) for v in por_zona.values())
        margen, alto = 74, 52
        ancho = max(40.0, min(240.0, (self.width() - margen - 8) / columnas - 8))
        fuente = QFont(self.font())
        base, tope = QColor(PISTA), QColor(VERDE)
        for fila, (zona, celdas) in enumerate(sorted(por_zona.items())):
            y = 8 + fila * (alto + 10)
            fuente.setPixelSize(13)
            fuente.setBold(True)
            p.setFont(fuente)
            p.setPen(QColor(TINTA_SUAVE))
            p.drawText(QRectF(0, y, margen - 8, alto), Qt.AlignmentFlag.AlignVCenter, f"Zona {zona}")
            for col, (cod, skus) in enumerate(celdas):
                t = (skus / maximo) * self._avance
                color = QColor(int(base.red() + (tope.red() - base.red()) * t),
                               int(base.green() + (tope.green() - base.green()) * t),
                               int(base.blue() + (tope.blue() - base.blue()) * t))
                caja = QRectF(margen + col * (ancho + 8), y, ancho, alto)
                camino = QPainterPath()
                camino.addRoundedRect(caja, 10, 10)
                p.fillPath(camino, color)
                p.setPen(QColor("#FFFFFF" if t > 0.45 else TINTA))
                fuente.setPixelSize(12)
                fuente.setBold(True)
                p.setFont(fuente)
                p.drawText(caja.adjusted(0, 6, 0, -alto / 2), Qt.AlignmentFlag.AlignCenter, cod)
                fuente.setBold(False)
                p.setFont(fuente)
                p.drawText(caja.adjusted(0, alto / 2 - 4, 0, -6), Qt.AlignmentFlag.AlignCenter,
                           "sin contar" if skus == 0 else f"{skus} SKU")


class Chip(QPushButton):
    """Botón de filtro rápido con forma de píldora (se queda marcado)."""

    def __init__(self, texto: str = "", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setObjectName("chip")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class Pasos(QWidget):
    """Las etapas de una sincronización en fila; la actual late y las anteriores quedan marcadas."""

    def __init__(self, nombres: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._nombres, self._actual, self._fase = list(nombres), None, 0.0
        self.setMinimumHeight(64)
        self._latido = QVariantAnimation(self)
        self._latido.setStartValue(0.0)
        self._latido.setEndValue(1.0)
        self._latido.setDuration(1400)
        self._latido.setLoopCount(-1)
        self._latido.valueChanged.connect(self._latir)

    def nombres(self) -> list[str]:
        return list(self._nombres)

    def actual(self) -> str | None:
        return self._actual

    def set_actual(self, nombre: str | None) -> None:
        self._actual = nombre if nombre in self._nombres else None
        ultimo = self._actual == self._nombres[-1]
        if ANIMAR and self._actual is not None and not ultimo and self.isVisible():
            self._latido.start()
        else:
            self._latido.stop()
            self._fase = 0.0
        self.update()

    def hideEvent(self, evento) -> None:
        self._latido.stop()
        super().hideEvent(evento)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self.set_actual(self._actual)

    def _latir(self, v) -> None:
        self._fase = float(v)
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self._nombres)
        paso = self.width() / n
        indice = self._nombres.index(self._actual) if self._actual else -1
        cy, radio = 22.0, 13.0
        for i in range(n - 1):
            hecho = i < indice
            p.setPen(QPen(QColor(VERDE if hecho else LINEA), 3))
            p.drawLine(QPointF(paso * (i + 0.5) + radio + 4, cy), QPointF(paso * (i + 1.5) - radio - 4, cy))
        fuente = QFont(self.font())
        for i, nombre in enumerate(self._nombres):
            cx = paso * (i + 0.5)
            terminado = indice >= 0 and (i < indice or (i == indice and i == n - 1))
            if i == indice and not terminado:
                halo = QColor(VERDE)
                halo.setAlphaF(0.35 * (1 - self._fase))
                p.setBrush(halo)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, cy), radio + 10 * self._fase, radio + 10 * self._fase)
            p.setBrush(QColor(VERDE if (terminado or i == indice) else "#111111"))
            p.setPen(QPen(QColor(VERDE if (terminado or i == indice) else LINEA), 2))
            p.drawEllipse(QPointF(cx, cy), radio, radio)
            fuente.setPixelSize(12)
            fuente.setBold(True)
            p.setFont(fuente)
            p.setPen(QColor("#04130E" if (terminado or i == indice) else TINTA_SUAVE))
            p.drawText(QRectF(cx - radio, cy - radio, 2 * radio, 2 * radio), Qt.AlignmentFlag.AlignCenter,
                       "✓" if terminado else str(i + 1))
            fuente.setBold(i == indice)
            p.setFont(fuente)
            p.setPen(QColor(TINTA if i <= indice else TINTA_SUAVE))
            p.drawText(QRectF(cx - paso / 2, cy + radio + 8, paso, 20), Qt.AlignmentFlag.AlignCenter, nombre)


class Indicador(QWidget):
    """El estado de la sincronización, dibujado: ondas (esperando), arco que gira (recibiendo), visto o alerta."""

    MODOS = ("reposo", "radar", "progreso", "listo", "error")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._modo, self._fase, self._entrada = "reposo", 0.0, 1.0
        self.setMinimumSize(190, 190)
        self._ciclo = QVariantAnimation(self)
        self._ciclo.setStartValue(0.0)
        self._ciclo.setEndValue(1.0)
        self._ciclo.setDuration(2200)
        self._ciclo.setLoopCount(-1)
        self._ciclo.valueChanged.connect(self._girar)

    def modo(self) -> str:
        return self._modo

    def set_modo(self, modo: str) -> None:
        if modo not in self.MODOS:
            raise ValueError(modo)
        if modo != self._modo:
            self._modo = modo
            animar(self, 0.0, 1.0, 450, self._entrar, curva=QEasingCurve.Type.OutBack)  # el icono «salta» al cambiar
        self._arrancar()
        self.update()

    def _arrancar(self) -> None:
        if ANIMAR and self._modo in ("radar", "progreso") and self.isVisible():
            self._ciclo.start()
        else:
            self._ciclo.stop()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._arrancar()

    def hideEvent(self, evento) -> None:
        self._ciclo.stop()
        super().hideEvent(evento)

    def _girar(self, v) -> None:
        self._fase = float(v)
        self.update()

    def _entrar(self, v: float) -> None:
        self._entrada = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        centro = QPointF(self.width() / 2, self.height() / 2)
        radio = min(self.width(), self.height()) / 2 - 6
        azul = QColor("#3B5BDB")
        color = {"listo": QColor(COLOR_CLASIFICACION["OK"]), "error": QColor(COLOR_CLASIFICACION["FALTANTE"])}.get(self._modo, azul)
        if self._modo == "radar":
            for i in range(3):  # tres ondas desfasadas que crecen y se desvanecen
                f = (self._fase + i / 3) % 1.0
                onda = QColor(azul)
                onda.setAlphaF(0.30 * (1 - f))
                p.setBrush(onda)
                p.setPen(Qt.PenStyle.NoPen)
                r = radio * (0.45 + 0.55 * f)
                p.drawEllipse(centro, r, r)
        elif self._modo == "progreso":
            caja = QRectF(centro.x() - radio + 8, centro.y() - radio + 8, 2 * radio - 16, 2 * radio - 16)
            p.setPen(QPen(QColor(PISTA), 10))
            p.drawArc(caja, 0, 360 * 16)
            p.setPen(QPen(QColor(VERDE), 10, cap=Qt.PenCapStyle.RoundCap))
            p.drawArc(caja, int((90 - 360 * self._fase) * 16), -100 * 16)
        nucleo = radio * 0.44 * max(0.2, self._entrada)
        p.setBrush(color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(centro, nucleo, nucleo)
        p.setPen(QPen(QColor("#FFFFFF"), max(3.0, nucleo * 0.13), cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = nucleo * 0.42
        trazo = QPainterPath()
        if self._modo == "listo":
            trazo.moveTo(centro.x() - s, centro.y())
            trazo.lineTo(centro.x() - s * 0.25, centro.y() + s * 0.7)
            trazo.lineTo(centro.x() + s, centro.y() - s * 0.6)
        elif self._modo == "error":
            trazo.moveTo(centro.x(), centro.y() - s)
            trazo.lineTo(centro.x(), centro.y() + s * 0.25)
            trazo.moveTo(centro.x(), centro.y() + s * 0.85)
            trazo.lineTo(centro.x(), centro.y() + s * 0.9)
        else:  # la runa de Bluetooth
            trazo.moveTo(centro.x() - s * 0.6, centro.y() - s * 0.55)
            trazo.lineTo(centro.x() + s * 0.55, centro.y() + s * 0.55)
            trazo.lineTo(centro.x(), centro.y() + s * 1.1)
            trazo.lineTo(centro.x(), centro.y() - s * 1.1)
            trazo.lineTo(centro.x() + s * 0.55, centro.y() - s * 0.55)
            trazo.lineTo(centro.x() - s * 0.6, centro.y() + s * 0.55)
        p.drawPath(trazo)


class Transicion(QWidget):
    """Cambio de pestaña: la imagen de la página anterior se desliza y se desvanece sobre la nueva."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._imagen: QPixmap | None = None
        self._avance, self._sentido, self._anim = 0.0, 1, None
        self.hide()

    def lanzar(self, imagen: QPixmap, sentido: int) -> None:
        if not ANIMAR or imagen.isNull():
            return
        _detener(self._anim)
        self._imagen, self._sentido, self._avance = imagen, sentido, 0.0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        self._anim = animar(self, 0.0, 1.0, 320, self._pintar_hasta, self._terminar, QEasingCurve.Type.OutCubic)

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def _terminar(self) -> None:
        self._imagen = None
        self.hide()

    def paintEvent(self, _evento) -> None:
        if self._imagen is None:
            return
        p = QPainter(self)
        p.setOpacity(1.0 - self._avance)
        p.drawPixmap(int(-self._sentido * 70 * self._avance), 0, self._imagen)
