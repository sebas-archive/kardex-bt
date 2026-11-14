"""Visor de la foto de evidencia de una lectura (Fase 4). El archivo vive en la carpeta de fotos del PC
(``FOTOS_DIR``); Oracle guarda su ruta relativa. El archivo se lee fuera del hilo de la interfaz.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget

from btsync.store import fotos_dir

from ..auth import ErrorDeAcceso
from .base import QueryRunner

FALTA = "La foto no está en la carpeta del PC ({ruta}). Puede que aún no haya llegado o que se haya movido."


def leer_foto(ruta: str) -> bytes:
    """Los bytes de la foto ``ruta`` (relativa a la carpeta de fotos). Nunca lee fuera de esa carpeta."""
    base = fotos_dir().resolve()
    archivo = (base / ruta).resolve()
    if base not in archivo.parents or not archivo.is_file():
        raise ErrorDeAcceso(FALTA.format(ruta=ruta))
    return archivo.read_bytes()


def ver_foto(padre: QWidget, ruta: str, titulo: str = "Foto de evidencia") -> None:
    """Abre la foto en un diálogo (no bloquea mientras se lee el archivo)."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle(titulo)
    dialogo.resize(820, 680)
    imagen = QLabel("Cargando la foto…")
    imagen.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pie = QLabel(str(Path(ruta)))
    pie.setObjectName("ayuda")
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    botones.rejected.connect(dialogo.reject)
    caja = QVBoxLayout(dialogo)
    caja.addWidget(imagen, 1)
    caja.addWidget(pie)
    caja.addWidget(botones)

    def mostrar(datos: bytes) -> None:
        mapa = QPixmap()
        if not mapa.loadFromData(datos):
            imagen.setText("El archivo no es una imagen válida.")
            return
        imagen.setPixmap(mapa.scaled(780, 600, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation))

    runner = QueryRunner(dialogo)
    runner.run(leer_foto, mostrar, imagen.setText, ruta)
    dialogo.exec()
