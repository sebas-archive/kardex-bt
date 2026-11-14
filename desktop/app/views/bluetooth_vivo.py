"""Vista viva del Bluetooth: diagrama celular ↔ PC, tráfico en tiempo real y botón de reintento que gira.

Todo se dibuja con QPainter; no hay recursos externos ni emoji. El diagrama responde al hover (resalta el
dispositivo) y al clic (emite cuál se eligió para abrir su panel de detalle).
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QPushButton, QWidget

from . import widgets

VERDE = "#10B981"
VERDE_CLARO = "#34D399"
TINTA = "#EDEDED"
SUAVE = "#8A8A8A"
FONDO = "#111111"
LINEA = "#2E2E2E"
AZUL = "#3B5BDB"


class Diagrama(QWidget):
    """Celular a la izquierda, PC a la derecha y paquetes que viajan mientras hay sincronización."""

    elegido = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._estado = "ESPERANDO_EMPAREJAMIENTO"
        self._fase = 0.0
        self._hover: str | None = None
        self._activo = False
        self.setMinimumHeight(160)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ciclo = QVariantAnimation(self)
        self._ciclo.setStartValue(0.0)
        self._ciclo.setEndValue(1.0)
        self._ciclo.setDuration(1600)
        self._ciclo.setLoopCount(-1)
        self._ciclo.valueChanged.connect(self._latir)

    def estado(self) -> str:
        return self._estado

    def set_estado(self, estado: str) -> None:
        self._estado = estado
        self._activo = estado in ("CONECTADO", "RECIBIENDO", "PROCESANDO")
        if self._activo and widgets.ANIMAR and self.isVisible():
            if self._ciclo.state() != QVariantAnimation.State.Running:
                self._ciclo.start()
        else:
            self._ciclo.stop()
            self._fase = 0.0
        self.update()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if self._activo and widgets.ANIMAR:
            self._ciclo.start()

    def hideEvent(self, evento) -> None:
        self._ciclo.stop()
        super().hideEvent(evento)

    def _latir(self, valor) -> None:
        self._fase = float(valor)
        self.update()

    def _cajas(self) -> tuple[QRectF, QRectF]:
        alto = self.height()
        lado = min(86.0, max(54.0, alto * 0.46))
        telefono = QRectF(24, (alto - lado) / 2, lado * 0.58, lado)
        pc = QRectF(self.width() - 24 - lado, (alto - lado) / 2 - 6, lado, lado * 0.72)
        return telefono, pc

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        telefono, pc = self._cajas()
        conectado = self._estado in ("CONECTADO", "RECIBIENDO", "PROCESANDO", "LISTO")
        color = QColor(VERDE_CLARO if conectado else AZUL)
        # línea punteada entre los dos equipos
        y = telefono.center().y()
        p.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
        p.drawLine(QPointF(telefono.right() + 8, y), QPointF(pc.left() - 8, y))
        # ondas de la conexión
        if conectado:
            for i in range(3):
                f = (self._fase + i / 3) % 1.0
                tono = QColor(color)
                tono.setAlphaF(0.35 * (1 - f))
                p.setPen(QPen(tono, 2))
                radio = 8 + 18 * f
                p.drawEllipse(QPointF((telefono.right() + pc.left()) / 2, y), radio, radio * 0.45)
        # paquetes viajando
        if self._activo:
            for i in range(2):
                f = (self._fase + i * 0.5) % 1.0
                x = telefono.right() + 8 + f * (pc.left() - telefono.right() - 16)
                p.setBrush(QColor(VERDE_CLARO))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(x - 4, y - 4, 8, 8), 2, 2)
        # teléfono
        self._equipo(p, telefono, "Celular", self._hover == "celular")
        # PC / monitor
        self._equipo(p, pc, "PC (servidor)", self._hover == "pc")
        # etiqueta de estado
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        p.setFont(fuente)
        p.setPen(QColor(SUAVE))
        texto = {
            "IDLE": "servicio activo · esperando un teléfono",
            "ESPERANDO_EMPAREJAMIENTO": "servicio activo · esperando un teléfono",
            "CONFIRMAR_CODIGO": "confirma el código en el celular",
            "CONECTADO": "celular conectado",
            "RECIBIENDO": "recibiendo lecturas…",
            "PROCESANDO": "procesando lecturas…",
            "LISTO": "sincronización completa",
            "ERROR": "error de conexión",
            "PAUSADO": "servicio en pausa",
            "PAUSANDO": "pausando…",
            "DETENIDO": "servicio detenido",
        }.get(self._estado, self._estado.lower())
        p.drawText(QRectF(0, self.height() - 20, self.width(), 18), Qt.AlignmentFlag.AlignCenter, texto)

    def _equipo(self, p: QPainter, caja: QRectF, nombre: str, resaltado: bool) -> None:
        borde = QColor(VERDE_CLARO if resaltado else (VERDE if self._estado in ("CONECTADO", "RECIBIENDO", "LISTO") else LINEA))
        relleno = QColor("#14332A" if resaltado else FONDO)
        camino = QPainterPath()
        camino.addRoundedRect(caja, 10, 10)
        p.fillPath(camino, relleno)
        p.setPen(QPen(borde, 2))
        p.drawPath(camino)
        # pantalla
        pantalla = caja.adjusted(caja.width() * 0.12, caja.height() * 0.12, -caja.width() * 0.12, -caja.height() * 0.22)
        p.setPen(QPen(QColor("#3A3A3A"), 1))
        p.setBrush(QColor("#0A0A0A"))
        p.drawRoundedRect(pantalla, 4, 4)
        # detalle interior: barras que sugieren datos
        p.setPen(Qt.PenStyle.NoPen)
        ancho = max(2.0, pantalla.width() / 9)
        for i in range(4):
            altura = pantalla.height() * (0.25 + 0.15 * ((i + 1) % 4))
            p.setBrush(QColor(VERDE if i % 2 else AZUL))
            p.drawRoundedRect(QRectF(pantalla.left() + 4 + i * (ancho + 3), pantalla.bottom() - altura - 4,
                                     ancho, altura), 1, 1)
        fuente = QFont(self.font())
        fuente.setPixelSize(11)
        fuente.setBold(True)
        p.setFont(fuente)
        p.setPen(QColor(TINTA))
        p.drawText(QRectF(caja.left() - 10, caja.bottom() + 6, caja.width() + 20, 18),
                   Qt.AlignmentFlag.AlignCenter, nombre)

    # ---------------------------------------------------------------- hover / clic
    def _zona(self, punto) -> str | None:
        telefono, pc = self._cajas()
        if telefono.adjusted(-8, -8, 8, 8).contains(punto):
            return "celular"
        if pc.adjusted(-8, -8, 8, 8).contains(punto):
            return "pc"
        return None

    def mouseMoveEvent(self, evento) -> None:
        zona = self._zona(evento.position())
        if zona != self._hover:
            self._hover = zona
            self.setToolTip({
                "celular": "Teléfono del operador: envía las lecturas por Bluetooth.",
                "pc": "PC: recibe, valida y guarda en Oracle. Clic para ver el detalle.",
            }.get(zona, ""))
            self.update()
        super().mouseMoveEvent(evento)

    def leaveEvent(self, evento) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(evento)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            zona = self._zona(evento.position())
            if zona:
                self.elegido.emit(zona)
        super().mousePressEvent(evento)


class BarrasTrafico(QWidget):
    """Ecualizador del tráfico: cuántas lecturas llegaron en los últimos intervalos."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._historial: list[int] = []
        self.setMinimumHeight(52)
        self.setMaximumHeight(70)
        self._avance = 1.0
        self._anim = None

    def historial(self) -> list[int]:
        return list(self._historial)

    def agregar(self, valor: int) -> None:
        if self._historial and self._historial[-1] == valor:
            return
        self._historial.append(int(valor))
        del self._historial[:-28]
        self._avance = 0.0
        widgets._detener(self._anim)
        self._anim = widgets.animar(self, 0.0, 1.0, 260, self._pintar_hasta)

    def _pintar_hasta(self, v: float) -> None:
        self._avance = v
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._historial or not any(self._historial):
            p.setPen(QColor(SUAVE))
            fuente = QFont(self.font())
            fuente.setPixelSize(11)
            p.setFont(fuente)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "sin tráfico todavía")
            return
        maximo = max(1, max(self._historial))
        n = len(self._historial)
        ancho = max(3.0, (self.width() - 8) / max(1, n) - 3)
        x = 4.0
        for i, valor in enumerate(self._historial):
            alto = (self.height() - 10) * (valor / maximo) * self._avance
            gradiente = QLinearGradient(x, self.height(), x, self.height() - max(alto, 2))
            gradiente.setColorAt(0.0, QColor("#0B8A62"))
            gradiente.setColorAt(1.0, QColor(VERDE_CLARO))
            p.setBrush(gradiente)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(x, self.height() - 4 - max(alto, 2), ancho, max(alto, 2)), 2, 2)
            x += ancho + 3


class BotonReintentar(QPushButton):
    """Botón de reintento: mientras reintenta, un arco gira a la izquierda del texto."""

    def __init__(self, texto: str = "Reintentar", parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self._angulo = 0
        self._girando = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._girar)

    def iniciar(self) -> None:
        self._girando = True
        self.setEnabled(False)
        self._timer.start()

    def detener(self) -> None:
        self._girando = False
        self._timer.stop()
        self._angulo = 0
        self.setEnabled(True)
        self.update()

    def _girar(self) -> None:
        self._angulo = (self._angulo + 24) % 360
        self.update()

    def paintEvent(self, evento) -> None:
        super().paintEvent(evento)
        if not self._girando:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lado = 14
        caja = QRectF(10, (self.height() - lado) / 2, lado, lado)
        p.setPen(QPen(QColor("#04130E"), 2.4, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(caja, int(-self._angulo * 16), 110 * 16)
