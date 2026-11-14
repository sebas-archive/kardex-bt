"""Pantalla «Configuración» (Fase 5, solo el Administrador): los valores que antes estaban fijos en el código.

Tres grupos (Ajustes críticos, Sincronización, Fotos) y «Guardar». Lo escrito no se pisa con el refresco automático
mientras haya cambios sin guardar. La carpeta de fotos se muestra pero no se edita: la fija la instalación.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QWidget)

from btsync.store import fotos_dir

from .. import auth, configuracion
from .base import QueryRunner, StateBanner

# (título del grupo, [(clave, etiqueta, unidad)])
GRUPOS = (
    ("Ajustes críticos", [("ajustes.umbral_pct", "Cambio de existencia desde", "%"),
                          ("ajustes.umbral_valor", "o diferencia de valor desde", "$")]),
    ("Sincronización", [("lote.intervalo_s", "Procesar lecturas cada", "segundos"),
                        ("staging.purga_dias", "Conservar lecturas recibidas", "días")]),
    ("Fotos", [("fotos.max_mb", "Tamaño máximo", "MB")]),
)


class ConfiguracionView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._campos: dict[str, QLineEdit] = {}
        self._cargados: dict[str, str] = {}

        ayuda = QLabel("Valores generales del sistema. Cada cambio queda en la auditoría.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self._cargar)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("avisoFormulario")
        self.lbl_info.hide()

        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        cuerpo = QVBoxLayout(tarjeta)
        cuerpo.setContentsMargins(20, 16, 20, 16)
        cuerpo.setSpacing(10)
        for titulo, campos in GRUPOS:
            encabezado = QLabel(titulo)
            encabezado.setObjectName("seccion")
            cuerpo.addWidget(encabezado)
            forma = QFormLayout()
            for clave, etiqueta, unidad in campos:
                editor = QLineEdit()
                editor.setMaximumWidth(140)
                editor.textEdited.connect(lambda _t: self.lbl_info.hide())
                self._campos[clave] = editor
                fila = QHBoxLayout()
                fila.addWidget(editor)
                fila.addWidget(QLabel(unidad))
                fila.addStretch(1)
                forma.addRow(etiqueta, fila)
            if titulo == "Fotos":
                carpeta = QLineEdit(str(fotos_dir()))
                carpeta.setObjectName("carpetaFotos")
                carpeta.setReadOnly(True)
                forma.insertRow(0, "Carpeta", carpeta)
                nota = QLabel("Se define al instalar (FOTOS_DIR). Las fotos ya guardadas no se mueven.")
                nota.setObjectName("ayuda")
                nota.setWordWrap(True)
                forma.insertRow(1, "", nota)
            cuerpo.addLayout(forma)

        self.btn_guardar = QPushButton("Guardar")
        self.btn_guardar.setObjectName("primario")
        self.btn_guardar.clicked.connect(self._guardar)
        pie = QHBoxLayout()
        pie.addWidget(self.lbl_info)
        pie.addStretch(1)
        pie.addWidget(self.btn_guardar)
        cuerpo.addLayout(pie)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.lbl_error)
        raiz.addWidget(tarjeta)
        raiz.addStretch(1)

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._cargados = {}
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No depende del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("configuracion") or self._sucio():
            return
        self._cargar()

    # ------------------------------------------------------------- pruebas
    def campo(self, clave: str) -> QLineEdit:
        return self._campos[clave]

    def banner_texto(self) -> str:
        return self.lbl_error.text() if not self.lbl_error.isHidden() else self.banner.text()

    # ------------------------------------------------------------- internos
    def _sucio(self) -> bool:
        return bool(self._cargados) and any(e.text() != self._cargados.get(k, "") for k, e in self._campos.items())

    def _cargar(self) -> None:
        self._runner.run(configuracion.valores, self._mostrar, self.banner.show_error, key="valores")

    def _mostrar(self, valores: dict[str, str]) -> None:
        self.banner.clear()
        self._cargados = {k: valores[k] for k in self._campos}
        for clave, editor in self._campos.items():
            editor.setText(valores[clave])

    def _guardar(self) -> None:
        if self._sesion is None:
            return
        self.lbl_error.hide()
        self.btn_guardar.setEnabled(False)
        cambios = {k: e.text() for k, e in self._campos.items()}
        self._runner.run(configuracion.guardar, self._guardado, self._error, self._sesion, cambios)

    def _guardado(self, valores: dict[str, str]) -> None:
        self.btn_guardar.setEnabled(True)
        self._mostrar(valores)
        self.lbl_info.setText("Guardado.")
        self.lbl_info.show()

    def _error(self, mensaje: str) -> None:
        self.btn_guardar.setEnabled(True)
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
