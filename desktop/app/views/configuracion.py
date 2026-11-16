"""Pantalla «Configuración» (solo el Administrador): intervalo del lote y tamaño máximo de foto.

La carpeta de fotos se muestra pero no se edita: la fija la instalación. Al guardar se reaplica el job del
Scheduler con el intervalo nuevo. No hay umbrales de ajuste crítico ni purga configurable.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QWidget)

from .. import auth, configuracion
from ..i18n import registrar, t
from .base import QueryRunner, StateBanner
from .isla import isla

registrar({
    "Configuración general": "General settings",
    "Valores generales del sistema. Cada cambio queda en la auditoría.":
        "General system values. Every change is recorded in the audit log.",
    "Sincronización": "Synchronization",
    "Procesar lecturas cada": "Process readings every",
    "minutos": "minutes",
    "Fotos": "Photos",
    "Tamaño máximo": "Maximum size",
    "MB": "MB",
    "Carpeta": "Folder",
    "Se define al instalar (FOTOS_DIR). Las fotos ya guardadas no se mueven.":
        "Set at install time (FOTOS_DIR). Photos already saved are not moved.",
    "Guardar": "Save",
    "Guardado.": "Saved.",
})

# (título del grupo, [(clave, etiqueta, unidad)])
GRUPOS = (
    ("Sincronización", [("lote.intervalo_min", "Procesar lecturas cada", "minutos")]),
    ("Fotos", [("fotos.max_mb", "Tamaño máximo", "MB")]),
)


class ConfiguracionView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._campos: dict[str, QLineEdit] = {}
        self._cargados: dict[str, str] = {}
        self._carpeta = QLineEdit()
        self._carpeta.setReadOnly(True)
        self._carpeta.setObjectName("carpetaFotos")

        ayuda = QLabel(t("Valores generales del sistema. Cada cambio queda en la auditoría."))
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
        cuerpo.setContentsMargins(24, 20, 24, 20)
        cuerpo.setSpacing(14)
        for titulo, campos in GRUPOS:
            encabezado = QLabel(t(titulo))
            encabezado.setObjectName("seccion")
            cuerpo.addWidget(encabezado)
            forma = QFormLayout()
            forma.setVerticalSpacing(12)
            forma.setHorizontalSpacing(16)
            forma.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            for clave, etiqueta, unidad in campos:
                editor = QLineEdit()
                editor.setMaximumWidth(140)
                editor.textEdited.connect(lambda _t: self.lbl_info.hide())
                self._campos[clave] = editor
                fila = QHBoxLayout()
                fila.addWidget(editor)
                fila.addWidget(QLabel(t(unidad)))
                fila.addStretch(1)
                forma.addRow(t(etiqueta), fila)
            if titulo == "Fotos":
                forma.insertRow(0, t("Carpeta"), self._carpeta)
                nota = QLabel(t("Se define al instalar (FOTOS_DIR). Las fotos ya guardadas no se mueven."))
                nota.setObjectName("ayuda")
                nota.setWordWrap(True)
                forma.insertRow(1, "", nota)
            cuerpo.addLayout(forma)

        self.btn_guardar = QPushButton(t("Guardar"))
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

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("configuracion") or self._sucio():
            return
        self._cargar()

    def campo(self, clave: str) -> QLineEdit:
        return self._campos[clave]

    def banner_texto(self) -> str:
        return self.lbl_error.text() or self.banner.text()

    # ------------------------------------------------------------- internos
    def _sucio(self) -> bool:
        return bool(self._cargados) and any(e.text() != self._cargados.get(k, "") for k, e in self._campos.items())

    def _cargar(self) -> None:
        self._runner.run(configuracion.valores, self._mostrar, self.banner.show_error, key="valores")

    def _mostrar(self, valores: dict[str, str]) -> None:
        self.banner.clear()
        self._cargados = {k: valores.get(k, "") for k in self._campos}
        for clave, editor in self._campos.items():
            editor.setText(valores.get(clave, ""))
        self._carpeta.setText(configuracion.carpeta_fotos(valores))

    def _guardar(self) -> None:
        if self._sesion is None:
            return
        self.lbl_error.setText("")
        self.btn_guardar.setEnabled(False)
        cambios = {k: e.text() for k, e in self._campos.items()}
        self._runner.run(configuracion.guardar, self._guardado, self._error, self._sesion, cambios)

    def _guardado(self, valores: dict[str, str]) -> None:
        self.btn_guardar.setEnabled(True)
        self._mostrar(valores)
        self.lbl_info.setText(t("Guardado."))
        isla.exito(t("Cambios guardados"), t("La configuración se guardó correctamente."))

    def _error(self, mensaje: str) -> None:
        self.btn_guardar.setEnabled(True)
        self.lbl_error.setText(mensaje)  # consultable; el aviso se muestra en la Isla
        if mensaje:
            isla.error(t("No se pudo guardar la configuración"), mensaje)
