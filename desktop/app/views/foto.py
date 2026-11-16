"""Fotos de la aplicación: avatar de perfil (editor con rotar, zoom, recorte y vista previa) y visor de evidencia.

Las fotos viven en la carpeta de fotos del PC (``FOTOS_DIR``); Oracle guarda la ruta relativa. El avatar se
guarda cuadrado en ``perfiles/<usuario>.jpg`` y se muestra circular; si no hay foto, se dibuja la inicial.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QImage, QImageReader, QPainter, QPainterPath, QPen, QPixmap,
                         QTransform)
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout,
                             QWidget)

from btsync.store import fotos_dir

from ..auth import ErrorDeAcceso
from ..i18n import t
from .base import QueryRunner

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

        btn_izq = QPushButton(t("Rotar") + " ⟲")
        btn_der = QPushButton(t("Rotar") + " ⟳")
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


# ------------------------------------------------------------------ visor de evidencia
def ver_foto(padre: QWidget, ruta: str, titulo: str = "Foto de evidencia") -> None:
    """Abre una sola foto en el visor (el archivo se lee fuera del hilo de la interfaz)."""
    from .visor_foto import FotoLectura, ver_fotos
    ver_fotos(padre, [FotoLectura(ruta=ruta, producto=t(titulo))])
