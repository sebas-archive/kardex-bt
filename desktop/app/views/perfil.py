"""Pantalla «Perfil»: quién tiene la sesión abierta, su rol, cambiar la contraseña y cerrar sesión."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from .. import auth
from .base import QueryRunner

PERMISOS = (
    ("Ver el dashboard, el inventario y las gráficas", False),
    ("Sincronizar con el celular", False),
    ("Exportar el inventario a CSV", False),
    ("Cerrar conteos y reprocesar errores", True),
    ("Administrar las cuentas y sus roles", True),
)


class PerfilView(QWidget):
    cerrar_sesion = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None

        self.lbl_inicial = QLabel("")
        self.lbl_inicial.setFixedSize(64, 64)
        self.lbl_inicial.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_inicial.setStyleSheet("background: #10261F; color: #34D399; border-radius: 32px; font-size: 26px; font-weight: 600;")
        self.lbl_nombre = QLabel("")
        self.lbl_nombre.setObjectName("tituloPagina")
        self.lbl_usuario = QLabel("")
        self.lbl_usuario.setObjectName("subtitulo")
        self.lbl_rol = QLabel("")
        self.lbl_rol.setObjectName("insignia")
        datos = QVBoxLayout()
        datos.setSpacing(2)
        datos.addWidget(self.lbl_nombre)
        fila_usuario = QHBoxLayout()
        fila_usuario.addWidget(self.lbl_usuario)
        fila_usuario.addWidget(self.lbl_rol)
        fila_usuario.addStretch(1)
        datos.addLayout(fila_usuario)
        self.btn_salir = QPushButton("Cerrar sesión")
        self.btn_salir.setObjectName("peligro")
        cabecera = QHBoxLayout()
        cabecera.setSpacing(16)
        cabecera.addWidget(self.lbl_inicial)
        cabecera.addLayout(datos, 1)
        cabecera.addWidget(self.btn_salir)

        self.lbl_permisos = QLabel("")
        self.lbl_permisos.setTextFormat(Qt.TextFormat.RichText)
        tarjeta_permisos = self._tarjeta("Lo que puede hacer tu rol", self.lbl_permisos)

        self.txt_actual = self._clave("Contraseña actual")
        self.txt_nueva = self._clave("Contraseña nueva (mínimo 8, con letras y números)")
        self.txt_confirmacion = self._clave("Repite la contraseña nueva")
        self.btn_cambiar = QPushButton("Cambiar contraseña")
        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.hide()
        fila_boton = QHBoxLayout()
        fila_boton.addWidget(self.btn_cambiar)
        fila_boton.addStretch(1)
        tarjeta_clave = self._tarjeta("Contraseña", self.txt_actual, self.txt_nueva, self.txt_confirmacion, fila_boton, self.lbl_resultado)
        tarjeta_clave.setMaximumWidth(460)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(16)
        raiz.addLayout(cabecera)
        columnas = QHBoxLayout()
        columnas.setSpacing(16)
        columnas.addWidget(tarjeta_clave, 1, Qt.AlignmentFlag.AlignTop)
        columnas.addWidget(tarjeta_permisos, 1, Qt.AlignmentFlag.AlignTop)
        raiz.addLayout(columnas)
        raiz.addStretch(1)

        self.btn_salir.clicked.connect(self.cerrar_sesion)
        self.btn_cambiar.clicked.connect(self._cambiar)
        self.txt_confirmacion.returnPressed.connect(self._cambiar)

    @staticmethod
    def _clave(pista: str) -> QLineEdit:
        campo = QLineEdit()
        campo.setPlaceholderText(pista)
        campo.setEchoMode(QLineEdit.EchoMode.Password)
        return campo

    @staticmethod
    def _tarjeta(titulo: str, *contenido) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("seccion")
        lay.addWidget(rotulo)
        for pieza in contenido:
            lay.addLayout(pieza) if isinstance(pieza, QHBoxLayout) else lay.addWidget(pieza)
        return tarjeta

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        for campo in (self.txt_actual, self.txt_nueva, self.txt_confirmacion):
            campo.clear()
        self.lbl_resultado.hide()
        if sesion is None:
            return
        self.lbl_inicial.setText(sesion.nombre[:1].upper())
        self.lbl_nombre.setText(sesion.nombre)
        self.lbl_usuario.setText(f"@{sesion.usuario}")
        self.lbl_rol.setText(auth.NOMBRE_ROL[sesion.rol])
        self.lbl_rol.setProperty("estado", sesion.rol)
        self.lbl_rol.style().unpolish(self.lbl_rol)
        self.lbl_rol.style().polish(self.lbl_rol)
        self.lbl_permisos.setText("<br>".join(
            (f"<span style='color:#34D399'>✓</span>&nbsp; {texto}" if sesion.es_admin or not solo_admin
             else f"<span style='color:#6E6E6E'>—&nbsp; {texto} (solo administrador)</span>")
            for texto, solo_admin in PERMISOS))

    def set_conteo(self, id_conteo: str | None) -> None:
        """El perfil no depende del conteo."""

    def refresh(self) -> None:
        """Nada que consultar: los datos de la sesión ya están aquí."""

    # ------------------------------------------------------------- internos
    def _cambiar(self) -> None:
        if self._sesion is None:
            return
        self.btn_cambiar.setEnabled(False)
        self._runner.run(auth.cambiar_clave, lambda _: self._resultado("Contraseña cambiada.", True),
                         lambda mensaje: self._resultado(mensaje, False),
                         self._sesion.usuario, self.txt_actual.text(), self.txt_nueva.text(), self.txt_confirmacion.text())

    def _resultado(self, mensaje: str, ok: bool) -> None:
        self.btn_cambiar.setEnabled(True)
        self.lbl_resultado.setObjectName("avisoFormulario" if ok else "errorFormulario")
        self.lbl_resultado.style().unpolish(self.lbl_resultado)
        self.lbl_resultado.style().polish(self.lbl_resultado)
        self.lbl_resultado.setText(mensaje)
        self.lbl_resultado.show()
        if ok:
            for campo in (self.txt_actual, self.txt_nueva, self.txt_confirmacion):
                campo.clear()
