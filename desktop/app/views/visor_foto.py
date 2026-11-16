"""Visor de fotografías de evidencia, al estilo de Apple Photos / Quick Look.

La foto es la protagonista: superficie oscura con esquinas redondeadas, controles flotantes que se esconden solos,
zoom (botones, rueda, doble clic), paneo, giro de 90°, navegación entre las fotos de las lecturas del producto y un
panel de información que empieza oculto. Las fotos se leen de la carpeta de fotos del PC (``foto.leer_foto``), fuera
del hilo de la interfaz; no se inventa ninguna imagen.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import (QEvent, QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPixmap, QTransform
from PyQt6.QtWidgets import (QApplication, QDialog, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QWidget)

from ..i18n import registrar, t
from . import widgets
from .base import QueryRunner
from .iconos import icono

registrar({
    "Foto de evidencia": "Evidence photo",
    "Cargando la foto…": "Loading the photo…",
    "La foto no está disponible": "The photo is not available",
    "El archivo no es una imagen válida.": "The file is not a valid image.",
    "Acercar": "Zoom in",
    "Alejar": "Zoom out",
    "Ajustar a la pantalla": "Fit to screen",
    "Tamaño original (100 %)": "Original size (100%)",
    "Girar 90°": "Rotate 90°",
    "Restablecer": "Reset",
    "Cerrar": "Close",
    "Foto anterior": "Previous photo",
    "Foto siguiente": "Next photo",
    "Información": "Information",
    "Mostrar u ocultar la información (I)": "Show or hide information (I)",
    "Producto": "Product",
    "SKU": "SKU",
    "Cantidad": "Quantity",
    "Operador": "Operator",
    "Fecha": "Date",
    "Nota": "Note",
    "Sin nota": "No note",
    "{n} de {total}": "{n} of {total}",
    "Rueda: zoom · arrastra: mover · doble clic: ajustar": "Wheel: zoom · drag: move · double-click: fit",
})

ESCALA_MINIMA, ESCALA_MAXIMA = 0.05, 10.0
ESCALA_AJUSTE_MAX = 2.0          # una foto pequeña no se agranda más del doble (se vería borrosa)
SOMBRA = 14
RADIO = 18
ANCHO_PANEL = 300
MARGENES = (28, 76, 28, 96)      # izquierda, arriba, derecha, abajo del área de la foto (respeta cabecera y barra)

QSS = """
QPushButton#visorBtn { background: rgba(255,255,255,0.10); border: none; border-radius: 17px; min-width: 34px;
    max-width: 34px; min-height: 34px; max-height: 34px; color: #FFFFFF; padding: 0; margin: 0; }
QPushButton#visorBtn:hover { background: rgba(255,255,255,0.20); }
QPushButton#visorBtn:pressed { background: rgba(255,255,255,0.30); }
QPushButton#visorBtn:disabled { background: rgba(255,255,255,0.04); }
QPushButton#visorBtn[activo="true"] { background: rgba(255,255,255,0.28); }
QPushButton#visorTexto { background: rgba(255,255,255,0.10); border: none; border-radius: 15px; min-height: 30px;
    max-height: 30px; padding: 0 12px; color: #FFFFFF; font-size: 12px; font-weight: 600; }
QPushButton#visorTexto:hover { background: rgba(255,255,255,0.20); }
QPushButton#visorFlecha { background: rgba(30,30,32,0.72); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 22px; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; padding: 0; }
QPushButton#visorFlecha:hover { background: rgba(60,60,64,0.9); }
QPushButton#visorFlecha:disabled { background: transparent; border-color: transparent; }
QFrame#visorCabecera { background: transparent; }
QFrame#visorBarra { background: rgba(28,28,30,0.78); border: 1px solid rgba(255,255,255,0.10); border-radius: 24px; }
QFrame#visorPanel { background: rgba(28,28,30,0.92); border: 1px solid rgba(255,255,255,0.10); border-radius: 16px; }
QLabel { background: transparent; color: #FFFFFF; }
QLabel#visorTitulo { font-size: 15px; font-weight: 700; }
QLabel#visorSub { font-size: 12px; color: rgba(255,255,255,0.62); }
QLabel#visorZoom { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.80); min-width: 46px; }
QLabel#visorEtiqueta { font-size: 10px; font-weight: 700; color: rgba(255,255,255,0.45); }
QLabel#visorValor { font-size: 13px; color: #FFFFFF; }
QLabel#visorContador { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.70); }
QFrame#visorSep { background: rgba(255,255,255,0.12); max-width: 1px; min-width: 1px; }
"""


@dataclass(frozen=True)
class FotoLectura:
    """Una fotografía de lectura con los datos que se muestran junto a ella."""

    ruta: str
    producto: str = ""
    sku: str = ""
    cantidad: str = ""
    operador: str = ""
    fecha: str = ""
    nota: str = ""


def _acotar(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


# ------------------------------------------------------------------ lienzo
class LienzoFoto(QWidget):
    """Superficie con zoom (rueda, botones, doble clic), paneo con arrastre y giro de 90°. Nunca deforma la foto."""

    cambio = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mapa = QPixmap()
        self._giradas: dict[int, QPixmap] = {}
        self._cache: tuple[tuple, QPixmap] | None = None
        self._escala = 1.0
        self._off = QPointF(0, 0)
        self._giros = 0                   # cuartos de vuelta acumulados (objetivo)
        self._angulo = 0.0                # ángulo que se dibuja (se anima hacia ``_giros * 90``)
        self._ajustada = True
        self._arrastrando = False
        self._ultimo = QPointF()
        self._anim: QVariantAnimation | None = None
        self._mensaje = ""
        self._margen_der = 0
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMinimumSize(200, 160)

    # ------------------------------------------------------------- estado
    def tiene_foto(self) -> bool:
        return not self._mapa.isNull()

    def escala(self) -> float:
        return self._escala

    def giros(self) -> int:
        return self._giros % 4

    def set_foto(self, mapa: QPixmap) -> None:
        self._detener()
        self._mapa = mapa
        self._giradas = {0: mapa}
        self._cache = None
        self._mensaje = ""
        self._giros, self._angulo = 0, 0.0
        self._ir_a(self._escala_ajuste(), QPointF(0, 0), 0, animar=False)
        self._ajustada = True

    def set_mensaje(self, texto: str) -> None:
        """Sin foto (cargando o no disponible): se dibuja el texto en el centro."""
        self._detener()
        self._mapa = QPixmap()
        self._cache = None
        self._mensaje = texto
        self.cambio.emit(1.0)
        self.update()

    def set_margen_derecho(self, px: int) -> None:
        """Reserva espacio a la derecha (panel de información) y vuelve a ajustar si estaba ajustada."""
        self._margen_der = px
        if self._ajustada and self.tiene_foto():
            self.ajustar()
        else:
            self._off = self._limitar(self._off, self._escala)
            self.update()

    # ------------------------------------------------------------- geometría
    def _interior(self) -> QRectF:
        izq, arr, der, aba = MARGENES
        return QRectF(izq, arr, max(10, self.width() - izq - der - self._margen_der), max(10, self.height() - arr - aba))

    def _centro(self) -> QPointF:
        return self._interior().center()

    def _tam_giro(self, giros: int | None = None) -> tuple[int, int]:
        g = (self._giros if giros is None else giros) % 4
        w, h = self._mapa.width(), self._mapa.height()
        return (h, w) if g % 2 else (w, h)

    def _escala_ajuste(self, giros: int | None = None) -> float:
        if self._mapa.isNull():
            return 1.0
        w, h = self._tam_giro(giros)
        zona = self._interior()
        return min(zona.width() / w, zona.height() / h, ESCALA_AJUSTE_MAX)

    def _limitar(self, off: QPointF, escala: float, giros: int | None = None) -> QPointF:
        """Sin salirse: si la foto cabe en un eje queda centrada; si no, no deja ver el vacío más allá del borde."""
        if self._mapa.isNull():
            return QPointF(0, 0)
        w, h = self._tam_giro(giros)
        zona = self._interior()
        ex, ey = (w * escala - zona.width()) / 2, (h * escala - zona.height()) / 2
        x = 0.0 if ex <= 0 else _acotar(off.x(), -ex - 40, ex + 40)
        y = 0.0 if ey <= 0 else _acotar(off.y(), -ey - 40, ey + 40)
        return QPointF(x, y)

    # ------------------------------------------------------------- animación
    def _detener(self) -> None:
        widgets._detener(self._anim)
        self._anim = None

    def _ir_a(self, escala: float, off: QPointF, giros: int, animar: bool = True, ms: int = 220) -> None:
        """Lleva zoom, posición y ángulo al destino (suave si hay animaciones)."""
        escala = _acotar(escala, ESCALA_MINIMA, ESCALA_MAXIMA)
        self._detener()
        self._giros = giros
        destino = (escala, off.x(), off.y(), giros * 90.0)
        inicio = (self._escala, self._off.x(), self._off.y(), self._angulo)

        def aplicar(v: float, fin: bool = False) -> None:
            if fin:
                self._escala, self._off, self._angulo = destino[0], QPointF(destino[1], destino[2]), destino[3]
            else:
                self._escala = inicio[0] + (destino[0] - inicio[0]) * v
                self._off = QPointF(inicio[1] + (destino[1] - inicio[1]) * v, inicio[2] + (destino[2] - inicio[2]) * v)
                self._angulo = inicio[3] + (destino[3] - inicio[3]) * v
            self.cambio.emit(self._escala)
            self.update()

        if not animar or self._mapa.isNull():
            aplicar(1.0, True)
            return
        def terminar() -> None:
            self._anim = None
            aplicar(1.0, True)

        self._anim = widgets.animar(self, 0.0, 1.0, ms, aplicar, terminar, QEasingCurve.Type.OutCubic)

    def _animando(self) -> bool:
        try:
            return self._anim is not None and self._anim.state() == QVariantAnimation.State.Running
        except RuntimeError:      # la animación ya terminó y Qt la liberó
            self._anim = None
            return False

    # ------------------------------------------------------------- acciones
    def ajustar(self) -> None:
        if self._mapa.isNull():
            return
        self._ajustada = True
        self._ir_a(self._escala_ajuste(), QPointF(0, 0), self._giros)

    def cien(self) -> None:
        if self._mapa.isNull():
            return
        self._ajustada = False
        self._ir_a(1.0, self._limitar(QPointF(0, 0), 1.0), self._giros)

    def acercar(self, factor: float = 1.25, ancla: QPointF | None = None, animar: bool = True) -> None:
        if self._mapa.isNull():
            return
        nueva = _acotar(self._escala * factor, ESCALA_MINIMA, ESCALA_MAXIMA)
        if abs(nueva - self._escala) < 1e-4:
            return
        c = self._centro()
        ancla = ancla if ancla is not None else c
        # El punto bajo ``ancla`` se queda donde está (si la foto es mayor que la zona).
        antes = (ancla - c - self._off) / self._escala
        off = self._limitar(ancla - c - antes * nueva, nueva)
        self._ajustada = False
        self._ir_a(nueva, off, self._giros, animar=animar, ms=160)

    def alejar(self, factor: float = 1.25) -> None:
        self.acercar(1 / factor)

    def girar(self) -> None:
        if self._mapa.isNull():
            return
        nuevos = self._giros + 1
        self._ajustada = True
        self._ir_a(self._escala_ajuste(nuevos), QPointF(0, 0), nuevos, ms=280)

    def restablecer(self) -> None:
        """Ajustada y sin giro."""
        if self._mapa.isNull():
            return
        giros = self._giros
        if giros % 4:
            giros += 4 - giros % 4          # sigue girando en el mismo sentido hasta la posición original
        self._ajustada = True
        self._ir_a(self._escala_ajuste(giros), QPointF(0, 0), giros, ms=300)

    # ------------------------------------------------------------- eventos
    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        if self._ajustada and self.tiene_foto():
            self._escala = self._escala_ajuste()
            self._off = QPointF(0, 0)
            self.cambio.emit(self._escala)
        elif self.tiene_foto():
            self._off = self._limitar(self._off, self._escala)

    def wheelEvent(self, evento) -> None:
        if self._mapa.isNull():
            return
        delta = evento.angleDelta().y()
        if not delta:
            return
        self.acercar(1.18 if delta > 0 else 1 / 1.18, evento.position(), animar=False)
        evento.accept()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and self.tiene_foto():
            self._detener()
            self._arrastrando = True
            self._ultimo = evento.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        if self._arrastrando:
            delta = evento.position() - self._ultimo
            self._ultimo = evento.position()
            self._off = self._limitar(self._off + delta, self._escala)
            self._ajustada = False
            self.update()

    def mouseReleaseEvent(self, _evento) -> None:
        if self._arrastrando:
            self._arrastrando = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _evento) -> None:
        if self._ajustada and abs(self._escala - 1.0) > 0.01 and self.tiene_foto():
            self.cien()
        else:
            self.ajustar()

    # ------------------------------------------------------------- pintura
    def _girada(self, giros: int) -> QPixmap:
        g = giros % 4
        if g not in self._giradas:
            self._giradas[g] = self._mapa.transformed(QTransform().rotate(g * 90),
                                                      Qt.TransformationMode.SmoothTransformation)
        return self._giradas[g]

    def _reducida(self, giros: int, ancho: int) -> QPixmap:
        """La foto reducida con calidad (suavizado) para que no se vea áspera al verla más pequeña."""
        clave = (giros % 4, ancho)
        if self._cache is None or self._cache[0] != clave:
            base = self._girada(giros)
            self._cache = (clave, base.scaledToWidth(ancho, Qt.TransformationMode.SmoothTransformation))
        return self._cache[1]

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._mapa.isNull():
            fuente = QFont(self.font())
            fuente.setPixelSize(14)
            p.setFont(fuente)
            p.setPen(QColor(255, 255, 255, 150))
            p.drawText(self._interior(), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       self._mensaje or t("Cargando la foto…"))
            return
        c = self._centro() + self._off
        w, h = self._mapa.width(), self._mapa.height()
        ancho_final = round(self._tam_giro()[0] * self._escala)
        quieta = not self._animando() and abs(self._angulo - self._giros * 90.0) < 0.01
        if quieta and self._escala < 0.85 and ancho_final >= 8:
            mapa = self._reducida(self._giros, ancho_final)
            x, y = round(c.x() - mapa.width() / 2), round(c.y() - mapa.height() / 2)
            ruta = QPainterPath()
            ruta.addRoundedRect(QRectF(x, y, mapa.width(), mapa.height()), 10, 10)
            p.setClipPath(ruta)
            p.drawPixmap(x, y, mapa)
            return
        p.translate(c)
        p.rotate(self._angulo)
        p.scale(self._escala, self._escala)
        ruta = QPainterPath()
        ruta.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), 10 / max(self._escala, 0.01), 10 / max(self._escala, 0.01))
        p.setClipPath(ruta)
        p.drawPixmap(round(-w / 2), round(-h / 2), self._mapa)


# ------------------------------------------------------------------ piezas del visor
class _Superficie(QWidget):
    """Fondo oscuro con esquinas redondeadas y sombra suave (el diálogo es translúcido y sin marco)."""

    cambio_tamano = pyqtSignal()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        caja = QRectF(self.rect()).adjusted(SOMBRA, SOMBRA, -SOMBRA, -SOMBRA)
        for i in range(SOMBRA - 2, 0, -2):
            ruta = QPainterPath()
            ruta.addRoundedRect(caja.adjusted(-i, -i + 4, i, i + 4), RADIO + i, RADIO + i)
            p.fillPath(ruta, QColor(0, 0, 0, int(34 * (1 - i / SOMBRA) ** 2)))
        ruta = QPainterPath()
        ruta.addRoundedRect(caja, RADIO, RADIO)
        p.fillPath(ruta, QColor("#0A0A0C"))
        p.setPen(QColor(255, 255, 255, 22))
        p.drawPath(ruta)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self.cambio_tamano.emit()


class _Agarre(QWidget):
    """Esquina inferior derecha para cambiar el tamaño de la ventana sin marco."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, evento) -> None:
        ventana = self.window().windowHandle()
        if evento.button() == Qt.MouseButton.LeftButton and ventana is not None:
            ventana.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.BottomEdge)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QColor(255, 255, 255, 70))
        for d in (6, 11, 16):
            p.drawLine(self.width() - 3, self.height() - 3 - d, self.width() - 3 - d, self.height() - 3)


class _Cabecera(QFrame):
    """Cabecera que también sirve para mover la ventana."""

    def mousePressEvent(self, evento) -> None:
        ventana = self.window().windowHandle()
        if evento.button() == Qt.MouseButton.LeftButton and ventana is not None:
            ventana.startSystemMove()
        else:
            super().mousePressEvent(evento)


def _boton(nombre: str, ayuda: str, objeto: str = "visorBtn", tam: int = 18) -> QPushButton:
    b = QPushButton()
    b.setObjectName(objeto)
    b.setIcon(icono(nombre, color="#FFFFFF", color_activo="#FFFFFF", tam=tam))
    b.setIconSize(QSize(tam, tam))
    b.setToolTip(ayuda)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


# ------------------------------------------------------------------ visor
class VisorFoto(QDialog):
    """Visor premium. ``fotos`` son las fotografías navegables (solo las que existen); ``indice`` la que se abre."""

    cambio_indice = pyqtSignal(int)

    def __init__(self, padre: QWidget | None, fotos: list[FotoLectura], indice: int = 0,
                 origen: QRect | None = None) -> None:
        super().__init__(padre)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(t("Foto de evidencia"))
        self.setStyleSheet(QSS)
        self._fotos = list(fotos)
        self._indice = max(0, min(indice, len(self._fotos) - 1)) if self._fotos else 0
        self._origen = origen
        self._cache: dict[str, QPixmap | str] = {}     # ruta -> foto, o el texto de por qué no se pudo
        self._runner = QueryRunner(self)
        self._cerrando = False
        self._abierto = False
        self._controles_visibles = True
        self._panel_abierto = False
        self._anims: list = []

        # ------------------------------------------------------------ estructura
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        self.superficie = _Superficie()
        raiz.addWidget(self.superficie)
        self.superficie.setMouseTracking(True)
        self.lienzo = LienzoFoto(self.superficie)

        # cabecera flotante
        self.cabecera = _Cabecera(self.superficie)
        self.cabecera.setObjectName("visorCabecera")
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setObjectName("visorTitulo")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("visorSub")
        textos = QVBoxLayout()
        textos.setSpacing(1)
        textos.addWidget(self.lbl_titulo)
        textos.addWidget(self.lbl_sub)
        self.btn_info = _boton("info", t("Mostrar u ocultar la información (I)"))
        self.btn_cerrar = _boton("cerrar", t("Cerrar"))
        fila = QHBoxLayout(self.cabecera)
        fila.setContentsMargins(22, 14, 18, 8)
        fila.setSpacing(8)
        fila.addLayout(textos, 1)
        fila.addWidget(self.btn_info)
        fila.addWidget(self.btn_cerrar)

        # barra inferior
        self.barra = QFrame(self.superficie)
        self.barra.setObjectName("visorBarra")
        self.btn_menos = _boton("zoom_menos", t("Alejar"))
        self.btn_mas = _boton("zoom_mas", t("Acercar"))
        self.lbl_zoom = QLabel("100 %")
        self.lbl_zoom.setObjectName("visorZoom")
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_ajustar = _boton("ajustar", t("Ajustar a la pantalla"))
        self.btn_cien = QPushButton("1:1")
        self.btn_cien.setObjectName("visorTexto")
        self.btn_cien.setToolTip(t("Tamaño original (100 %)"))
        self.btn_cien.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cien.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_girar = _boton("girar", t("Girar 90°"))
        self.btn_reset = _boton("restablecer", t("Restablecer"))
        sep = QFrame()
        sep.setObjectName("visorSep")
        sep.setFixedHeight(20)
        barra = QHBoxLayout(self.barra)
        barra.setContentsMargins(12, 8, 12, 8)
        barra.setSpacing(6)
        for w in (self.btn_menos, self.lbl_zoom, self.btn_mas, sep, self.btn_ajustar, self.btn_cien, self.btn_girar,
                  self.btn_reset):
            barra.addWidget(w)

        # flechas y contador
        self.btn_ant = _boton("izquierda", t("Foto anterior"), "visorFlecha", 22)
        self.btn_sig = _boton("derecha", t("Foto siguiente"), "visorFlecha", 22)
        self.lbl_contador = QLabel("")
        self.lbl_contador.setObjectName("visorContador")
        self.lbl_contador.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_contador.setParent(self.superficie)

        # panel de información (oculto al principio)
        self.panel = QFrame(self.superficie)
        self.panel.setObjectName("visorPanel")
        self._valores: dict[str, QLabel] = {}
        rejilla = QGridLayout(self.panel)
        rejilla.setContentsMargins(20, 18, 20, 18)
        rejilla.setVerticalSpacing(4)
        cab = QLabel(t("Información"))
        cab.setObjectName("visorTitulo")
        rejilla.addWidget(cab, 0, 0)
        fila_n = 1
        for clave, etiqueta in (("producto", "Producto"), ("sku", "SKU"), ("cantidad", "Cantidad"),
                                ("operador", "Operador"), ("fecha", "Fecha"), ("nota", "Nota")):
            titulo = QLabel(t(etiqueta).upper())
            titulo.setObjectName("visorEtiqueta")
            valor = QLabel("")
            valor.setObjectName("visorValor")
            valor.setWordWrap(True)
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rejilla.addWidget(titulo, fila_n, 0)
            rejilla.addWidget(valor, fila_n + 1, 0)
            rejilla.setRowMinimumHeight(fila_n + 2, 8)
            self._valores[clave] = valor
            fila_n += 3
        rejilla.setRowStretch(fila_n, 1)
        self.panel.hide()
        self.agarre = _Agarre(self.superficie)

        # efectos de opacidad de lo que se esconde solo
        self._efectos: list[QGraphicsOpacityEffect] = []
        for w in (self.cabecera, self.barra, self.btn_ant, self.btn_sig, self.lbl_contador):
            ef = QGraphicsOpacityEffect(w)
            ef.setOpacity(1.0)
            w.setGraphicsEffect(ef)
            self._efectos.append(ef)
        self._ef_lienzo = QGraphicsOpacityEffect(self.lienzo)
        self._ef_lienzo.setOpacity(1.0)
        self.lienzo.setGraphicsEffect(self._ef_lienzo)

        self._reposo = QTimer(self)
        self._reposo.setSingleShot(True)
        self._reposo.setInterval(2600)
        self._reposo.timeout.connect(self._esconder_controles)

        # ------------------------------------------------------------ señales
        self.superficie.cambio_tamano.connect(self._acomodar)
        self.btn_cerrar.clicked.connect(self.reject)
        self.btn_info.clicked.connect(self.alternar_info)
        self.btn_menos.clicked.connect(lambda: self.lienzo.alejar())
        self.btn_mas.clicked.connect(lambda: self.lienzo.acercar())
        self.btn_ajustar.clicked.connect(lambda: self.lienzo.ajustar())
        self.btn_cien.clicked.connect(lambda: self.lienzo.cien())
        self.btn_girar.clicked.connect(lambda: self.lienzo.girar())
        self.btn_reset.clicked.connect(lambda: self.lienzo.restablecer())
        self.btn_ant.clicked.connect(lambda: self.ir_a(self._indice - 1))
        self.btn_sig.clicked.connect(lambda: self.ir_a(self._indice + 1))
        self.lienzo.cambio.connect(lambda e: self.lbl_zoom.setText(f"{e * 100:.0f} %"))

        self._tamano_inicial(padre)
        self._mostrar_datos()
        self._cargar_actual()

    # ------------------------------------------------------------- API (también para pruebas)
    @property
    def indice(self) -> int:
        return self._indice

    def total(self) -> int:
        return len(self._fotos)

    def foto_actual(self) -> FotoLectura | None:
        return self._fotos[self._indice] if self._fotos else None

    def panel_visible(self) -> bool:
        return self._panel_abierto

    def ir_a(self, indice: int) -> None:
        """Otra foto de la lista; no se puede ir más allá de la primera ni de la última."""
        if not 0 <= indice < len(self._fotos) or indice == self._indice:
            return
        self._indice = indice
        self._mostrar_datos()
        self._cargar_actual()
        self.cambio_indice.emit(indice)

    def alternar_info(self) -> None:
        self._panel_abierto = not self._panel_abierto
        self.btn_info.setProperty("activo", self._panel_abierto)
        self.btn_info.style().unpolish(self.btn_info)
        self.btn_info.style().polish(self.btn_info)
        self.lienzo.set_margen_derecho(ANCHO_PANEL + 16 if self._panel_abierto else 0)
        self._acomodar()
        if self._panel_abierto:
            self.panel.show()
            self.panel.raise_()
            self.agarre.raise_()
            self._deslizar_panel(True)
        else:
            self._deslizar_panel(False)

    # ------------------------------------------------------------- tamaño y apertura
    def _tamano_inicial(self, padre: QWidget | None) -> None:
        ventana = padre.window() if padre is not None else None
        if ventana is not None and ventana.isVisible():
            marco = ventana.geometry()
        else:
            pantalla = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else QRect(0, 0, 1280, 800)
            marco = pantalla
        ancho = max(760, min(int(marco.width() * 0.84), 1500))
        alto = max(540, min(int(marco.height() * 0.86), 1000))
        self.setMinimumSize(620, 460)
        self.resize(ancho + 2 * SOMBRA, alto + 2 * SOMBRA)
        self.move(marco.center().x() - self.width() // 2, marco.center().y() - self.height() // 2)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        self._acomodar()
        self.setFocus()
        QApplication.instance().installEventFilter(self)
        if not self._abierto:
            self._abierto = True
            self._animar_apertura()
        self._reposo.start()

    def _animar_apertura(self) -> None:
        if not widgets.ANIMAR:
            return
        final = self.geometry()
        self.setWindowOpacity(0.0)
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        if self._origen is not None and self._origen.width() > 0:
            # De la miniatura a la foto: la ventana crece desde el rectángulo que se pulsó.
            g = QPropertyAnimation(self, b"geometry", self)
            g.setDuration(340)
            g.setStartValue(self._origen.adjusted(-SOMBRA, -SOMBRA, SOMBRA, SOMBRA))
            g.setEndValue(final)
            g.setEasingCurve(QEasingCurve.Type.OutCubic)
            g.start()
            self._anims.append(g)
        else:
            reducida = QRect(0, 0, round(final.width() * 0.94), round(final.height() * 0.94))
            reducida.moveCenter(final.center())
            g = QPropertyAnimation(self, b"geometry", self)
            g.setDuration(300)
            g.setStartValue(reducida)
            g.setEndValue(final)
            g.setEasingCurve(QEasingCurve.Type.OutCubic)
            g.start()
            self._anims.append(g)
        a.start()
        self._anims.append(a)

    def reject(self) -> None:
        """Cierra con un desvanecido suave."""
        if self._cerrando:
            return
        self._cerrando = True
        QApplication.instance().removeEventFilter(self)
        if not widgets.ANIMAR or not self.isVisible():
            super().reject()
            return
        a = QPropertyAnimation(self, b"windowOpacity", self)
        a.setDuration(170)
        a.setStartValue(self.windowOpacity())
        a.setEndValue(0.0)
        a.setEasingCurve(QEasingCurve.Type.InCubic)
        a.finished.connect(lambda: QDialog.reject(self))
        a.start()
        self._anims.append(a)

    def done(self, resultado: int) -> None:
        QApplication.instance().removeEventFilter(self)
        super().done(resultado)

    # ------------------------------------------------------------- disposición
    def _acomodar(self) -> None:
        s = self.superficie.rect().adjusted(SOMBRA, SOMBRA, -SOMBRA, -SOMBRA)
        self.lienzo.setGeometry(s)
        self.cabecera.setGeometry(s.left(), s.top(), s.width(), 70)
        ancho_barra = self.barra.sizeHint().width()
        alto_barra = self.barra.sizeHint().height()
        self.barra.setGeometry(s.left() + (s.width() - ancho_barra) // 2, s.bottom() - 18 - alto_barra, ancho_barra,
                               alto_barra)
        self.btn_ant.setGeometry(s.left() + 18, s.center().y() - 22, 44, 44)
        derecha = s.right() - 18 - (ANCHO_PANEL + 16 if self._panel_abierto else 0)
        self.btn_sig.setGeometry(derecha - 44, s.center().y() - 22, 44, 44)
        self.lbl_contador.setGeometry(s.left() + (s.width() - 120) // 2, s.bottom() - 28 - alto_barra - 20, 120, 22)
        self.panel.setGeometry(s.right() - ANCHO_PANEL - 14, s.top() + 62, ANCHO_PANEL, min(420, s.height() - 150))
        self.agarre.move(s.right() - 18, s.bottom() - 18)
        for w in (self.cabecera, self.barra, self.btn_ant, self.btn_sig, self.lbl_contador, self.panel, self.agarre):
            w.raise_()

    def _deslizar_panel(self, entrar: bool) -> None:
        destino = self.panel.geometry()
        if not widgets.ANIMAR:
            self.panel.setVisible(entrar)
            return
        ef = QGraphicsOpacityEffect(self.panel)
        self.panel.setGraphicsEffect(ef)
        origen = QPoint(destino.x() + (24 if entrar else 0), destino.y())
        fin = QPoint(destino.x() + (0 if entrar else 24), destino.y())

        def paso(v: float) -> None:
            ef.setOpacity(v if entrar else 1 - v)
            self.panel.move(round(origen.x() + (fin.x() - origen.x()) * v), destino.y())

        def listo() -> None:
            self.panel.setGraphicsEffect(None)
            self.panel.setVisible(entrar)
            self.panel.move(destino.topLeft())

        widgets.animar(self, 0.0, 1.0, 220, paso, listo, QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------- datos y carga
    def _mostrar_datos(self) -> None:
        foto = self.foto_actual()
        n = len(self._fotos)
        if foto is None:
            return
        self.lbl_titulo.setText(foto.producto or foto.sku)
        partes = [p for p in (f"SKU {foto.sku}" if foto.sku else "", foto.fecha, foto.operador) if p]
        self.lbl_sub.setText("  ·  ".join(partes))
        self._valores["producto"].setText(foto.producto or "—")
        self._valores["sku"].setText(foto.sku or "—")
        self._valores["cantidad"].setText(foto.cantidad or "—")
        self._valores["operador"].setText(foto.operador or "—")
        self._valores["fecha"].setText(foto.fecha or "—")
        self._valores["nota"].setText(foto.nota or t("Sin nota"))
        varias = n > 1
        self.btn_ant.setVisible(varias)
        self.btn_sig.setVisible(varias)
        self.lbl_contador.setVisible(varias)
        self.lbl_contador.setText(t("{n} de {total}", n=self._indice + 1, total=n))
        self.btn_ant.setEnabled(self._indice > 0)
        self.btn_sig.setEnabled(self._indice < n - 1)

    def _cargar_actual(self) -> None:
        foto = self.foto_actual()
        if foto is None:
            self.lienzo.set_mensaje(t("La foto no está disponible"))
            return
        if foto.ruta in self._cache:
            self._poner(foto.ruta)
            return
        self.lienzo.set_mensaje(t("Cargando la foto…"))
        from .foto import leer_foto
        ruta = foto.ruta
        self._runner.run(leer_foto, lambda datos, r=ruta: self._llego(r, datos), lambda m, r=ruta: self._fallo(r, m), ruta)

    def _llego(self, ruta: str, datos: bytes) -> None:
        mapa = QPixmap()
        if mapa.loadFromData(datos):
            self._cache[ruta] = mapa
        else:
            self._cache[ruta] = t("El archivo no es una imagen válida.")
        foto = self.foto_actual()
        if foto is not None and foto.ruta == ruta:
            self._poner(ruta)

    def _fallo(self, ruta: str, mensaje: str) -> None:
        self._cache[ruta] = mensaje
        foto = self.foto_actual()
        if foto is not None and foto.ruta == ruta:
            self._poner(ruta)

    def _poner(self, ruta: str) -> None:
        dato = self._cache[ruta]
        if isinstance(dato, QPixmap):
            self.lienzo.set_foto(dato)
            self._fundir_lienzo()
        else:
            self.lienzo.set_mensaje(dato)

    def _fundir_lienzo(self) -> None:
        if not widgets.ANIMAR:
            self._ef_lienzo.setOpacity(1.0)
            return
        self._ef_lienzo.setOpacity(0.0)
        widgets.animar(self, 0.0, 1.0, 220, self._ef_lienzo.setOpacity, lambda: self._ef_lienzo.setOpacity(1.0),
                       QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------- controles que se esconden
    def _fijar_controles(self, visibles: bool) -> None:
        if visibles == self._controles_visibles:
            return
        self._controles_visibles = visibles
        destino = 1.0 if visibles else 0.0
        for ef in self._efectos:
            inicio = ef.opacity()
            widgets.animar(self, inicio, destino, 220, ef.setOpacity, lambda e=ef, d=destino: e.setOpacity(d))

    def _esconder_controles(self) -> None:
        # No se esconden con el cursor sobre ellos.
        pos = self.mapFromGlobal(self.cursor().pos())
        for w in (self.cabecera, self.barra, self.btn_ant, self.btn_sig, self.panel):
            if w.isVisible() and w.geometry().translated(self.superficie.pos()).contains(pos):
                self._reposo.start()
                return
        self._fijar_controles(False)

    def eventFilter(self, obj, evento) -> bool:
        if evento.type() == QEvent.Type.MouseMove and isinstance(obj, QWidget) and (obj is self or self.isAncestorOf(obj)):
            self._fijar_controles(True)
            self._reposo.start()
        return False

    # ------------------------------------------------------------- teclado
    def keyPressEvent(self, evento) -> None:
        k = evento.key()
        if k in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.reject()
        elif k == Qt.Key.Key_Left:
            self.ir_a(self._indice - 1)
        elif k == Qt.Key.Key_Right:
            self.ir_a(self._indice + 1)
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.lienzo.acercar()
        elif k == Qt.Key.Key_Minus:
            self.lienzo.alejar()
        elif k == Qt.Key.Key_0:
            self.lienzo.ajustar()
        elif k == Qt.Key.Key_1:
            self.lienzo.cien()
        elif k == Qt.Key.Key_R:
            self.lienzo.girar()
        elif k == Qt.Key.Key_I:
            self.alternar_info()
        else:
            super().keyPressEvent(evento)
        self._fijar_controles(True)
        self._reposo.start()


def ver_fotos(padre: QWidget | None, fotos: list[FotoLectura], indice: int = 0, origen: QRect | None = None,
              al_cambiar=None) -> None:
    """Abre el visor (modal) con las fotos dadas. ``al_cambiar(indice)`` avisa al navegar, y al cerrar con la última vista."""
    if not fotos:
        return
    visor = VisorFoto(padre, fotos, indice, origen)
    if al_cambiar is not None:
        visor.cambio_indice.connect(al_cambiar)
    visor.exec()
