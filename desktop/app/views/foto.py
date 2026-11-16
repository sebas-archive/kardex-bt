"""Fotos de la aplicación: avatar de perfil (editor con rotar, zoom, recorte y vista previa) y visor de evidencia.

Las fotos viven en la carpeta de fotos del PC (``FOTOS_DIR``); Oracle guarda la ruta relativa. El avatar se
guarda cuadrado en ``perfiles/<usuario>.jpg`` y se muestra circular; si no hay foto, se dibuja la inicial.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QImage, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QTransform)
from PyQt6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame, QGraphicsDropShadowEffect,
                             QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QSlider, QToolButton,
                             QVBoxLayout, QWidget)

from btsync.store import fotos_dir

from ..auth import ErrorDeAcceso
from ..i18n import t
from . import widgets
from .base import QueryRunner
from .iconos import icono

FALTA = "La foto no está en la carpeta del PC ({ruta}). Puede que aún no haya llegado o que se haya movido."
ESCALA_MINIMA, ESCALA_MAXIMA = 0.12, 8.0
FORMATOS = ("PNG", "JPG", "JPEG", "WEBP", "BMP")
CARPETA_PERFILES = "perfiles"
LADO_AVATAR = 512


# ------------------------------------------------------------------ avatar
def _absoluta(ruta: str) -> Path:
    base = fotos_dir().resolve()
    archivo = (base / ruta).resolve()
    if base not in archivo.parents:
        raise ErrorDeAcceso(t("La ruta de la foto no es válida."))
    return archivo


def leer_foto(ruta: str) -> bytes:
    """Los bytes de la foto ``ruta`` (relativa a la carpeta de fotos). Nunca lee fuera de esa carpeta."""
    archivo = _absoluta(ruta)
    if not archivo.is_file():
        raise ErrorDeAcceso(t(FALTA, ruta=ruta))
    return archivo.read_bytes()


def _circular(mapa: QPixmap, tam: int) -> QPixmap:
    """Recorta al centro un cuadrado y lo enmascara en círculo (con el doble de resolución)."""
    lado = tam * 2
    escalada = mapa.scaled(lado, lado, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    x = max(0, (escalada.width() - lado) // 2)
    y = max(0, (escalada.height() - lado) // 2)
    recorte = escalada.copy(x, y, lado, lado)
    salida = QPixmap(lado, lado)
    salida.fill(Qt.GlobalColor.transparent)
    p = QPainter(salida)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    camino = QPainterPath()
    camino.addEllipse(0, 0, lado, lado)
    p.setClipPath(camino)
    p.drawPixmap(0, 0, recorte)
    p.end()
    salida.setDevicePixelRatio(2)
    return salida


def pixmap_avatar(ruta: str | None, tam: int = 36) -> QPixmap | None:
    """Avatar circular desde la ruta relativa; ``None`` si no hay foto o no se puede leer."""
    if not ruta:
        return None
    try:
        archivo = _absoluta(ruta)
        if not archivo.is_file():
            return None
        mapa = QPixmap(str(archivo))
        return None if mapa.isNull() else _circular(mapa, tam)
    except (ErrorDeAcceso, OSError, RuntimeError):
        return None


def pixmap_inicial(nombre: str, tam: int = 36, oscuro: bool = True) -> QPixmap:
    """Círculo con la inicial (sin foto)."""
    lado = tam * 2
    mapa = QPixmap(lado, lado)
    mapa.fill(Qt.GlobalColor.transparent)
    p = QPainter(mapa)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#059669" if oscuro else "#10B981"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, lado, lado)
    p.setPen(QColor("#FFFFFF"))
    fuente = QFont(p.font())
    fuente.setPixelSize(int(lado * 0.44))
    fuente.setBold(True)
    p.setFont(fuente)
    p.drawText(QRect(0, 0, lado, lado), Qt.AlignmentFlag.AlignCenter, (nombre or "?")[:1].upper())
    p.end()
    mapa.setDevicePixelRatio(2)
    return mapa


def icono_avatar(ruta: str | None, nombre: str, tam: int = 28) -> QPixmap:
    return pixmap_avatar(ruta, tam) or pixmap_inicial(nombre, tam)


def guardar_perfil(usuario: str, imagen: QImage) -> str:
    """Guarda el avatar cuadrado en ``perfiles/<usuario>.jpg`` y devuelve su ruta relativa."""
    carpeta = fotos_dir() / CARPETA_PERFILES
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{usuario}.jpg"
    if not imagen.save(str(archivo), "JPG", 90):
        raise ErrorDeAcceso(t("La imagen no se pudo leer."))
    return f"{CARPETA_PERFILES}/{usuario}.jpg"


def borrar_perfil(ruta: str | None) -> None:
    if not ruta:
        return
    try:
        archivo = _absoluta(ruta)
        if archivo.is_file() and archivo.parent.name == CARPETA_PERFILES:
            archivo.unlink()
    except (ErrorDeAcceso, OSError):
        pass


def formato_valido(ruta: str) -> bool:
    lector = QImageReader(ruta)
    return lector.canRead() and (lector.format().data().decode(errors="ignore").upper() in FORMATOS)


# ------------------------------------------------------------------ editor de avatar
class LienzoRecorte(QWidget):
    """Superficie cuadrada: la imagen se arrastra y se acerca; lo que se ve es el avatar."""

    cambio = pyqtSignal()

    def __init__(self, imagen: QImage, lado: int = 360, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._imagen = imagen
        self._giro = 0
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._arrastrando = False
        self._ultimo = QPointF(0, 0)
        self.setFixedSize(lado, lado)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)

    def imagen(self) -> QImage:
        return self._imagen

    def giro(self) -> int:
        return self._giro

    def zoom(self) -> float:
        return self._zoom

    def girar(self, derecha: bool = True) -> None:
        self._giro = (self._giro + (90 if derecha else -90)) % 360
        self._offset = QPointF(0, 0)
        self._limitar()
        self.cambio.emit()
        self.update()

    def poner_zoom(self, valor: float) -> None:
        self._zoom = max(1.0, min(4.0, float(valor)))
        self._limitar()
        self.cambio.emit()
        self.update()

    def _rotada(self) -> QImage:
        if not self._giro:
            return self._imagen
        return self._imagen.transformed(QTransform().rotate(self._giro), Qt.TransformationMode.SmoothTransformation)

    def _escala_base(self) -> float:
        rotada = self._rotada()
        if rotada.isNull():
            return 1.0
        return max(self.width() / rotada.width(), self.height() / rotada.height())

    def _max_offset(self) -> tuple[float, float]:
        rotada = self._rotada()
        escala = self._escala_base() * self._zoom
        ancho, alto = rotada.width() * escala, rotada.height() * escala
        return max(0.0, (ancho - self.width()) / 2), max(0.0, (alto - self.height()) / 2)

    def _limitar(self) -> None:
        mx, my = self._max_offset()
        self._offset = QPointF(max(-mx, min(mx, self._offset.x())), max(-my, min(my, self._offset.y())))

    def wheelEvent(self, evento) -> None:
        delta = evento.angleDelta().y()
        if delta:
            self.poner_zoom(self._zoom * (1.08 if delta > 0 else 1 / 1.08))
            evento.accept()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self._arrastrando = True
            self._ultimo = evento.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        if self._arrastrando:
            delta = evento.position() - self._ultimo
            self._ultimo = evento.position()
            self._offset += delta
            self._limitar()
            self.cambio.emit()
            self.update()

    def mouseReleaseEvent(self, _evento) -> None:
        self._arrastrando = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#080808"))
        rotada = self._rotada()
        if rotada.isNull():
            return
        escala = self._escala_base() * self._zoom
        p.translate(self.width() / 2 + self._offset.x(), self.height() / 2 + self._offset.y())
        p.rotate(self._giro)
        p.scale(escala, escala)
        p.drawImage(int(-self._imagen.width() / 2), int(-self._imagen.height() / 2), self._imagen)
        p.resetTransform()
        p.setPen(QPen(QColor("#10B981"), 2))
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))
        p.end()

    def recorte(self) -> QImage:
        """El cuadrado visible, a 512×512, para guardarlo como avatar."""
        rotada = self._rotada()
        if rotada.isNull():
            return QImage()
        escala_salida = LADO_AVATAR / self.width()
        escala = self._escala_base() * self._zoom
        salida = QImage(LADO_AVATAR, LADO_AVATAR, QImage.Format.Format_ARGB32)
        salida.fill(QColor("#000000"))
        p = QPainter(salida)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(LADO_AVATAR / 2 + self._offset.x() * escala_salida, LADO_AVATAR / 2 + self._offset.y() * escala_salida)
        p.rotate(self._giro)
        p.scale(escala * escala_salida, escala * escala_salida)
        p.drawImage(int(-self._imagen.width() / 2), int(-self._imagen.height() / 2), self._imagen)
        p.end()
        return salida


class EditorFoto(QDialog):
    """Editor de la foto de perfil: rotar, zoom, arrastrar para cortar y vista previa circular antes de guardar."""

    def __init__(self, imagen: QImage, padre: QWidget | None = None) -> None:
        super().__init__(padre)
        self.setWindowTitle(t("Editor de foto"))
        self.setModal(True)
        self.lienzo = LienzoRecorte(imagen)
        self.vista = QLabel()
        self.vista.setFixedSize(140, 140)
        self.vista.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vista.setObjectName("avatar")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(100, 400)
        self.slider.setValue(100)

        from .iconos import icono
        btn_izq = QPushButton(" " + t("Rotar"))
        btn_izq.setIcon(icono("rotate_ccw", tam=16))
        btn_der = QPushButton(" " + t("Rotar"))
        btn_der.setIcon(icono("rotate_cw", tam=16))
        btn_izq.clicked.connect(lambda: self.lienzo.girar(False))
        btn_der.clicked.connect(lambda: self.lienzo.girar(True))
        btn_reset = QPushButton(t("Restablecer"))
        btn_reset.clicked.connect(self._reset)
        self.slider.valueChanged.connect(lambda v: self.lienzo.poner_zoom(v / 100))
        self.lienzo.cambio.connect(self._previsualizar)

        controles = QVBoxLayout()
        controles.addWidget(QLabel(t("Vista previa")))
        controles.addWidget(self.vista, 0, Qt.AlignmentFlag.AlignHCenter)
        controles.addSpacing(8)
        fila = QHBoxLayout()
        fila.addWidget(btn_izq)
        fila.addWidget(btn_der)
        controles.addLayout(fila)
        controles.addWidget(QLabel(t("Zoom")))
        controles.addWidget(self.slider)
        controles.addWidget(btn_reset)
        controles.addStretch(1)

        cuerpo = QHBoxLayout()
        cuerpo.setSpacing(16)
        cuerpo.addWidget(self.lienzo)
        cuerpo.addLayout(controles, 1)

        self.btn_cancelar = QPushButton(t("Cancelar"))
        self.btn_aplicar = QPushButton(t("Aplicar"))
        self.btn_aplicar.setObjectName("primario")
        self.btn_cancelar.clicked.connect(self.reject)
        self.btn_aplicar.clicked.connect(self.accept)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.btn_cancelar)
        pie.addWidget(self.btn_aplicar)

        caja = QVBoxLayout(self)
        caja.setContentsMargins(16, 16, 16, 14)
        caja.setSpacing(12)
        caja.addLayout(cuerpo)
        caja.addLayout(pie)
        self._previsualizar()

    def _reset(self) -> None:
        self.lienzo._zoom = 1.0
        self.lienzo._offset = QPointF(0, 0)
        self.lienzo._giro = 0
        self.slider.setValue(100)
        self.lienzo.update()
        self._previsualizar()

    def _previsualizar(self) -> None:
        recorte = self.lienzo.recorte()
        if recorte.isNull():
            return
        self.vista.setPixmap(_circular(QPixmap.fromImage(recorte), 70))

    def resultado(self) -> QImage:
        return self.lienzo.recorte()


def elegir_imagen(padre: QWidget) -> str | None:
    """Diálogo de archivo con los formatos de imagen comunes. ``None`` si se cancela."""
    ruta, _ = QFileDialog.getOpenFileName(
        padre, t("Elegir foto"), "", "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp)")
    return ruta or None


# ------------------------------------------------------------------ visor de evidencia (estilo Apple Photos)
FONDO_VISOR = "#0B0D0C"
TEXTO_VISOR = "#E5E7EB"
ALTO_CABECERA = 96
ANCHO_INFO = 290


class LienzoFoto(QWidget):
    """Superficie de la foto: zoom animado, rueda alrededor del cursor, paneo con arrastre y giro de 90°.

    La imagen nunca se deforma: se escala uniformemente y, al ajustar, jamás se amplía más allá de su tamaño real.
    """

    cambio = pyqtSignal(float)
    movimiento = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._original = QPixmap()
        self._mapa = QPixmap()
        self._giro = 0
        self._escala = 1.0
        self._desplazamiento = QPointF(0, 0)
        self._arrastrando = False
        self._ultimo = QPointF(0, 0)
        self._ajustada = True
        self._anim = None
        self._mensaje = ""
        self._error = False
        self.setMinimumSize(320, 240)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ------------------------------------------------------------------ estado
    def tiene_foto(self) -> bool:
        return not self._mapa.isNull()

    def escala(self) -> float:
        return self._escala

    def giro(self) -> int:
        return self._giro

    def set_foto(self, mapa: QPixmap) -> None:
        self._original, self._giro = mapa, 0
        self._mensaje, self._error = "", False
        self._reconstruir()
        self.ajustar(animar=False)

    def set_estado(self, texto: str, error: bool = False) -> None:
        """Sin foto que mostrar: «Cargando…» o el motivo por el que no hay imagen."""
        self._original = QPixmap()
        self._mapa = QPixmap()
        self._mensaje, self._error = texto, error
        self.update()

    def _reconstruir(self) -> None:
        self._mapa = (self._original if self._giro == 0 else
                      self._original.transformed(QTransform().rotate(self._giro), Qt.TransformationMode.SmoothTransformation))

    # ------------------------------------------------------------------ zoom
    def _escala_de_ajuste(self) -> float:
        return min(max(1, self.width()) / self._mapa.width(), max(1, self.height()) / self._mapa.height(), 1.0)

    def _ir_a(self, escala: float, desplazamiento: QPointF, animar: bool = True) -> None:
        widgets._detener(self._anim)
        if not animar or not widgets.ANIMAR or not self.isVisible():
            self._escala, self._desplazamiento = escala, desplazamiento
            self.cambio.emit(self._escala)
            self.update()
            return
        e0, d0 = self._escala, QPointF(self._desplazamiento)

        def paso(v: float) -> None:
            self._escala = e0 + (escala - e0) * v
            self._desplazamiento = d0 + (desplazamiento - d0) * v
            self.cambio.emit(self._escala)
            self.update()
        self._anim = widgets.animar(self, 0.0, 1.0, 170, paso, None, QEasingCurve.Type.OutCubic)

    def ajustar(self, animar: bool = True) -> None:
        if self._mapa.isNull():
            return
        self._ajustada = True
        self._ir_a(self._escala_de_ajuste(), QPointF(0, 0), animar)

    def cien(self) -> None:
        if self._mapa.isNull():
            return
        self._ajustada = False
        self._ir_a(1.0, QPointF(0, 0))

    def _zoom(self, factor: float) -> None:
        if self._mapa.isNull():
            return
        nueva = max(ESCALA_MINIMA, min(ESCALA_MAXIMA, self._escala * factor))
        self._ajustada = False
        self._ir_a(nueva, self._desplazamiento * (nueva / self._escala))

    def acercar(self) -> None:
        self._zoom(1.25)

    def alejar(self) -> None:
        self._zoom(1 / 1.25)

    def girar(self) -> None:
        if self._original.isNull():
            return
        self._giro = (self._giro + 90) % 360
        self._reconstruir()
        self.ajustar(animar=False)

    def restablecer(self) -> None:
        if self._original.isNull():
            return
        self._giro = 0
        self._reconstruir()
        self.ajustar()

    # ------------------------------------------------------------------ ratón
    def wheelEvent(self, evento) -> None:
        if self._mapa.isNull():
            return
        delta = evento.angleDelta().y()
        if not delta:
            return
        widgets._detener(self._anim)
        factor = 1.18 if delta > 0 else 1 / 1.18
        nueva = max(ESCALA_MINIMA, min(ESCALA_MAXIMA, self._escala * factor))
        if abs(nueva - self._escala) < 1e-4:
            return
        centro = QPointF(self.width() / 2, self.height() / 2)
        cursor = evento.position()
        antes = (cursor - centro - self._desplazamiento) / self._escala    # el punto bajo el cursor se mantiene
        self._escala = nueva
        self._desplazamiento = cursor - centro - antes * self._escala
        self._ajustada = False
        self.cambio.emit(self._escala)
        self.update()
        evento.accept()

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton and self.tiene_foto():
            self._arrastrando = True
            self._ultimo = evento.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, evento) -> None:
        self.movimiento.emit()
        if self._arrastrando:
            delta = evento.position() - self._ultimo
            self._ultimo = evento.position()
            self._desplazamiento += delta
            self._ajustada = False
            self.update()

    def mouseReleaseEvent(self, _evento) -> None:
        if self._arrastrando:
            self._arrastrando = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, _evento) -> None:
        if self._ajustada and self._escala < 1.0 and self.tiene_foto():
            self.cien()
        else:
            self.ajustar()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        if self._ajustada and self.tiene_foto():
            self.ajustar(animar=False)

    # ------------------------------------------------------------------ dibujo
    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._mapa.isNull():
            color = QColor("#F87171" if self._error else "#9CA3AF")
            icono_estado = icono("imagen_no" if self._error else "imagen", color=color.name(), tam=44).pixmap(44, 44)
            centro = self.rect().center()
            p.drawPixmap(centro.x() - 22, centro.y() - 44, icono_estado)
            p.setPen(color)
            p.drawText(QRectF(self.width() * 0.15, centro.y() + 14, self.width() * 0.7, 80),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                       self._mensaje)
            p.end()
            return
        p.translate(self.width() / 2 + self._desplazamiento.x(), self.height() / 2 + self._desplazamiento.y())
        p.scale(self._escala, self._escala)
        ruta = QPainterPath()
        radio = 6 / max(self._escala, 0.01)
        ruta.addRoundedRect(QRectF(-self._mapa.width() / 2, -self._mapa.height() / 2, self._mapa.width(),
                                   self._mapa.height()), radio, radio)
        p.setClipPath(ruta)
        p.drawPixmap(int(-self._mapa.width() / 2), int(-self._mapa.height() / 2), self._mapa)
        p.end()


class _Scrim(QWidget):
    """Degradado oscuro bajo el encabezado: lo hace legible sobre cualquier foto sin competir con ella."""

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(0, 0, 0, 215))
        grad.setColorAt(0.6, QColor(0, 0, 0, 120))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(self.rect(), grad)
        p.end()


def _boton_visor(nombre_icono: str, tooltip: str, tam: int = 18) -> QToolButton:
    b = QToolButton()
    b.setObjectName("visorBoton")
    b.setIcon(icono(nombre_icono, color=TEXTO_VISOR, tam=tam))
    b.setIconSize(QSize(tam, tam))
    b.setToolTip(tooltip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return b


class VisorFoto(QDialog):
    """Visor de evidencia: la foto es la protagonista; todo lo demás es discreto y aparece al mover el cursor.

    Controles: zoom (botones, rueda, +/−), ajustar, 100 %, girar, restablecer, anterior/siguiente (si el SKU tiene más
    fotos), panel de información plegado al abrir (tecla I) y cierre (Esc). Fondo oscuro en ambos temas.
    """

    def __init__(self, padre: QWidget, titulo: str = "Foto de evidencia", fotos: list[dict] | None = None,
                 actual: int = 0) -> None:
        super().__init__(padre)
        self.setWindowTitle(t(titulo))
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("visor")
        self._fotos = fotos or [{"ruta": "", "producto": t(titulo)}]
        self._i = max(0, min(actual, len(self._fotos) - 1))
        self._cache: dict[str, QPixmap] = {}
        self._runner = QueryRunner(self)
        self._cerrando = False
        self._info_visible = False
        self._info_p = 0.0
        self._anim_info = None
        self._anim_controles = None
        self._controles_visibles = True

        self._caja = QFrame()
        self._caja.setObjectName("visorCaja")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 18, 18, 18)
        raiz.addWidget(self._caja)
        sombra = QGraphicsDropShadowEffect(self._caja)
        sombra.setBlurRadius(46)
        sombra.setOffset(0, 10)
        sombra.setColor(QColor(0, 0, 0, 150))
        self._caja.setGraphicsEffect(sombra)

        self.lienzo = LienzoFoto(self._caja)
        self.lienzo.movimiento.connect(self._mostrar_controles)

        # ---- encabezado: producto, SKU, fecha y operador; info y cerrar a la derecha
        self._cabecera = _Scrim(self._caja)
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setObjectName("visorTitulo")
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("visorSub")
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(self.lbl_titulo)
        textos.addWidget(self.lbl_sub)
        self.btn_info = _boton_visor("info", t("Información (I)"))
        self.btn_info.setCheckable(True)
        self.btn_cerrar = _boton_visor("x", t("Cerrar (Esc)"))
        fila = QHBoxLayout(self._cabecera)
        fila.setContentsMargins(22, 16, 16, 0)
        fila.setSpacing(6)
        fila.addLayout(textos, 1)
        fila.addWidget(self.btn_info, 0, Qt.AlignmentFlag.AlignTop)
        fila.addWidget(self.btn_cerrar, 0, Qt.AlignmentFlag.AlignTop)
        self.btn_info.clicked.connect(self.alternar_info)
        self.btn_cerrar.clicked.connect(self.cerrar)

        # ---- panel de información (plegado al abrir)
        self._info = QFrame(self._caja)
        self._info.setObjectName("visorInfo")
        self._lay_info = QVBoxLayout(self._info)
        self._lay_info.setContentsMargins(18, 16, 18, 16)
        self._lay_info.setSpacing(10)
        self._info.hide()

        # ---- flechas de navegación
        self.btn_anterior = _boton_visor("izquierda", t("Anterior (←)"), 22)
        self.btn_siguiente = _boton_visor("derecha", t("Siguiente (→)"), 22)
        for flecha in (self.btn_anterior, self.btn_siguiente):
            flecha.setObjectName("visorFlecha")
            flecha.setParent(self._caja)
            flecha.setFixedSize(44, 44)
        self.btn_anterior.clicked.connect(lambda: self.ir_a(self._i - 1))
        self.btn_siguiente.clicked.connect(lambda: self.ir_a(self._i + 1))

        # ---- barra de controles flotante
        self._controles = QFrame(self._caja)
        self._controles.setObjectName("visorControles")
        lay = QHBoxLayout(self._controles)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        self.lbl_zoom = QLabel("100 %")
        self.lbl_zoom.setObjectName("visorZoom")
        self.lbl_zoom.setMinimumWidth(48)
        self.lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        acciones = (
            ("zoom_out", t("Alejar (−)"), self.lienzo.alejar), None, ("zoom_in", t("Acercar (+)"), self.lienzo.acercar),
            "sep", ("ajustar", t("Ajustar a pantalla (0)"), self.lienzo.ajustar),
            ("imagen", t("Tamaño original (1)"), self.lienzo.cien), "sep",
            ("rotate_cw", t("Girar 90° (R)"), self.lienzo.girar),
            ("rotate_ccw", t("Restablecer"), self.lienzo.restablecer),
        )
        for accion in acciones:
            if accion is None:
                lay.addWidget(self.lbl_zoom)
            elif accion == "sep":
                sep = QFrame()
                sep.setObjectName("visorSep")
                sep.setFixedSize(1, 20)
                lay.addWidget(sep)
            else:
                b = _boton_visor(accion[0], accion[1])
                b.clicked.connect(accion[2])
                lay.addWidget(b)
        self._op_controles = QGraphicsOpacityEffect(self._controles)
        self._controles.setGraphicsEffect(self._op_controles)
        self._op_flechas = QGraphicsOpacityEffect(self.btn_anterior)
        self.btn_anterior.setGraphicsEffect(self._op_flechas)
        self._op_flechas2 = QGraphicsOpacityEffect(self.btn_siguiente)
        self.btn_siguiente.setGraphicsEffect(self._op_flechas2)
        self._reposo = QTimer(self)
        self._reposo.setSingleShot(True)
        self._reposo.setInterval(2600)
        self._reposo.timeout.connect(self._ocultar_controles)
        self.lienzo.cambio.connect(lambda e: self.lbl_zoom.setText(f"{e * 100:.0f} %"))
        for w in (self._caja, self._cabecera, self._controles, self.btn_anterior, self.btn_siguiente, self._info,
                  self.btn_info, self.btn_cerrar):
            w.setMouseTracking(True)
            w.installEventFilter(self)
        self.ir_a(self._i)

    # ------------------------------------------------------------------ datos y navegación
    def fotos(self) -> list[dict]:
        return list(self._fotos)

    def indice(self) -> int:
        return self._i

    def ir_a(self, i: int) -> None:
        if not 0 <= i < len(self._fotos):
            return
        self._i = i
        f = self._fotos[i]
        self._poner_textos(f)
        self.btn_anterior.setVisible(len(self._fotos) > 1 and i > 0)
        self.btn_siguiente.setVisible(len(self._fotos) > 1 and i < len(self._fotos) - 1)
        ruta = f.get("ruta", "")
        if not ruta:
            self.lienzo.set_estado(t("Esta lectura no tiene fotografía."), error=True)
        elif ruta in self._cache:
            self.lienzo.set_foto(self._cache[ruta])
        else:
            self.lienzo.set_estado(t("Cargando la foto…"))
            self._runner.run(leer_foto, lambda datos, r=ruta: self._llego(r, datos),
                             lambda msg, r=ruta: self._fallo(r, msg), ruta, key="visorFoto")
        self._reubicar()

    def _llego(self, ruta: str, datos: bytes) -> None:
        mapa = QPixmap()
        if not mapa.loadFromData(datos):
            if ruta == self._fotos[self._i].get("ruta"):
                self.lienzo.set_estado(t("El archivo no es una imagen válida."), error=True)
            return
        self._cache[ruta] = mapa
        if ruta == self._fotos[self._i].get("ruta"):
            self.lienzo.set_foto(mapa)

    def _fallo(self, ruta: str, mensaje: str) -> None:
        if ruta == self._fotos[self._i].get("ruta"):
            self.lienzo.set_estado(mensaje, error=True)

    def _poner_textos(self, f: dict) -> None:
        producto = f.get("producto", "")
        self.lbl_titulo.setText(f"{producto} · {f['sku']}" if f.get("sku") else producto)
        partes = [p for p in (f.get("fecha"), f.get("operador")) if p]
        if len(self._fotos) > 1:
            partes.append(f"{self._i + 1} / {len(self._fotos)}")
        self.lbl_sub.setText("  ·  ".join(partes))
        while self._lay_info.count():
            item = self._lay_info.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        encabezado = QLabel(t("Información"))
        encabezado.setObjectName("visorInfoTitulo")
        self._lay_info.addWidget(encabezado)
        for etiqueta, valor in ((t("Producto"), producto), (t("SKU"), f.get("sku", "")),
                                (t("Cantidad"), f.get("cantidad", "")), (t("Operador"), f.get("operador", "")),
                                (t("Fecha (UTC)"), f.get("fecha", "")), (t("Estado"), f.get("estado", "")),
                                (t("Nota"), f.get("nota", ""))):
            if not valor:
                continue
            e = QLabel(etiqueta)
            e.setObjectName("visorInfoEtiqueta")
            v = QLabel(str(valor))
            v.setObjectName("visorInfoValor")
            v.setWordWrap(True)
            self._lay_info.addWidget(e)
            self._lay_info.addWidget(v)
        self._lay_info.addStretch(1)

    # ------------------------------------------------------------------ panel de información
    def alternar_info(self) -> None:
        self._info_visible = not self._info_visible
        self.btn_info.setChecked(self._info_visible)
        self._info.show()
        widgets._detener(self._anim_info)

        def paso(v: float) -> None:
            self._info_p = v
            self._reubicar()
        self._anim_info = widgets.animar(self, self._info_p, 1.0 if self._info_visible else 0.0, 200, paso,
                                         None if self._info_visible else self._info.hide, QEasingCurve.Type.OutCubic)
        if self._anim_info is None and not self._info_visible:
            self._info.hide()

    def info_visible(self) -> bool:
        return self._info_visible

    # ------------------------------------------------------------------ controles que aparecen al mover el cursor
    def _fijar_opacidad(self, valor: float) -> None:
        for efecto in (self._op_controles, self._op_flechas, self._op_flechas2):
            efecto.setOpacity(valor)

    def _mostrar_controles(self) -> None:
        self._reposo.start()
        if self._controles_visibles:
            return
        self._controles_visibles = True
        widgets._detener(self._anim_controles)
        self._anim_controles = widgets.animar(self, self._op_controles.opacity(), 1.0, 160, self._fijar_opacidad)

    def _ocultar_controles(self) -> None:
        if self._controles.underMouse() or self.btn_anterior.underMouse() or self.btn_siguiente.underMouse():
            self._reposo.start()
            return
        self._controles_visibles = False
        widgets._detener(self._anim_controles)
        self._anim_controles = widgets.animar(self, self._op_controles.opacity(), 0.0, 260, self._fijar_opacidad)

    def eventFilter(self, objeto, evento) -> bool:
        if evento.type() in (QEvent.Type.MouseMove, QEvent.Type.Enter):
            self._mostrar_controles()
        return False

    # ------------------------------------------------------------------ colocación y animaciones de apertura/cierre
    def _reubicar(self) -> None:
        r = self._caja.rect()
        if r.isEmpty():
            return
        self.lienzo.setGeometry(r)
        self._cabecera.setGeometry(0, 0, r.width(), ALTO_CABECERA)
        ctl = self._controles.sizeHint()
        self._controles.setGeometry((r.width() - ctl.width()) // 2, r.height() - ctl.height() - 22, ctl.width(), ctl.height())
        y = (r.height() - 44) // 2
        self.btn_anterior.move(16, y)
        self.btn_siguiente.move(r.width() - 60 - int(ANCHO_INFO * self._info_p) - (12 if self._info_p else 0), y)
        ancho = int(ANCHO_INFO * self._info_p)
        self._info.setGeometry(r.width() - ancho - (12 if ancho else 0), ALTO_CABECERA + 4, ANCHO_INFO,
                               max(120, r.height() - ALTO_CABECERA - 96))
        for w in (self._cabecera, self._controles, self.btn_anterior, self.btn_siguiente):
            w.raise_()
        self._info.raise_()
        self.btn_info.raise_()
        self.btn_cerrar.raise_()
        self.lienzo.lower()

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._reubicar()

    def _encajar(self) -> None:
        """Casi todo el espacio de la ventana principal, centrado y sin tamaños rígidos."""
        raiz = self.parentWidget()
        while raiz is not None and raiz.parentWidget() is not None:
            raiz = raiz.parentWidget()
        base = raiz.frameGeometry() if raiz is not None else QApplication.primaryScreen().availableGeometry()
        pantalla = QApplication.primaryScreen().availableGeometry()
        ancho = min(pantalla.width() - 40, max(720, int(base.width() * 0.94)))
        alto = min(pantalla.height() - 40, max(520, int(base.height() * 0.94)))
        self.resize(ancho, alto)
        self.move(base.center().x() - ancho // 2, base.center().y() - alto // 2)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if not getattr(self, "_encajado", False):
            self._encajado = True
            self._encajar()
        self._reubicar()
        self.setFocus()
        self._reposo.start()
        if widgets.ANIMAR:
            self.setWindowOpacity(0.0)
            widgets.animar(self, 0.0, 1.0, 200, self.setWindowOpacity)

    def cerrar(self) -> None:
        """Desaparece con un fundido corto y cierra."""
        if self._cerrando:
            return
        self._cerrando = True
        if not widgets.ANIMAR or not self.isVisible():
            self.accept()
            return
        widgets.animar(self, 1.0, 0.0, 160, self.setWindowOpacity, self.accept, QEasingCurve.Type.InCubic)

    def reject(self) -> None:
        self.cerrar()

    def keyPressEvent(self, evento) -> None:
        clave = evento.key()
        if clave in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.cerrar()
        elif clave in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.lienzo.acercar()
        elif clave in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.lienzo.alejar()
        elif clave == Qt.Key.Key_0:
            self.lienzo.ajustar()
        elif clave == Qt.Key.Key_1:
            self.lienzo.cien()
        elif clave == Qt.Key.Key_R:
            self.lienzo.girar()
        elif clave == Qt.Key.Key_I:
            self.alternar_info()
        elif clave == Qt.Key.Key_Left:
            self.ir_a(self._i - 1)
        elif clave == Qt.Key.Key_Right:
            self.ir_a(self._i + 1)
        else:
            super().keyPressEvent(evento)
        self._mostrar_controles()


def ver_foto(padre: QWidget, ruta: str, titulo: str = "Foto de evidencia") -> None:
    """Abre la foto en el visor. Si ``padre`` conoce las fotos de su SKU (``fotos_del_sku``), se puede navegar entre ellas.

    El archivo se lee fuera del hilo de la interfaz. Al cerrar, la ventana de lecturas sigue como estaba.
    """
    contexto = getattr(padre, "fotos_del_sku", None)
    fotos = contexto() if callable(contexto) else []
    indice = next((i for i, f in enumerate(fotos) if f.get("ruta") == ruta), None)
    if indice is None:
        fotos, indice = [{"ruta": ruta, "producto": titulo}], 0
    VisorFoto(padre, titulo, fotos, indice).exec()
