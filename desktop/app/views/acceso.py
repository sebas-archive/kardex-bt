"""Pantalla de acceso: iniciar sesión, crear cuenta o pedir una contraseña nueva. Sin sesión, la aplicación no pasa de aquí."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from .. import auth
from .base import QueryRunner

FUERZA = ("Mínimo 8 caracteres, con letras y números", "Débil", "Aceptable", "Buena", "Fuerte")


def _campo(pista: str, clave: bool = False) -> QLineEdit:
    campo = QLineEdit()
    campo.setPlaceholderText(pista)
    campo.setMinimumHeight(38)
    if clave:
        campo.setEchoMode(QLineEdit.EchoMode.Password)
    return campo


class AccesoView(QWidget):
    """Dos formularios (entrar y crear cuenta) en una tarjeta; la validación corre fuera del hilo de la interfaz."""

    entro = pyqtSignal(object)       # auth.Sesion
    sin_acceso = pyqtSignal(object)  # auth.CuentaSinAcceso: pendiente, rechazada o suspendida

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)

        # ---- panel de marca (izquierda)
        marca = QFrame()
        marca.setObjectName("panelMarca")
        en_marca = QVBoxLayout(marca)
        en_marca.setContentsMargins(40, 40, 40, 40)
        titulo = QLabel("Gestión de inventario")
        titulo.setStyleSheet("font-size: 26px; font-weight: 600;")
        titulo.setWordWrap(True)
        lema = QLabel("Conteo físico con el celular, sin red.\nLos datos llegan por Bluetooth y Oracle los concilia.")
        lema.setStyleSheet("font-size: 14px;")
        lema.setWordWrap(True)
        en_marca.addStretch(1)
        en_marca.addWidget(titulo)
        en_marca.addSpacing(8)
        en_marca.addWidget(lema)
        en_marca.addStretch(2)

        # ---- entrar
        self.txt_usuario = _campo("Usuario")
        self.txt_clave = _campo("Contraseña", clave=True)
        self.btn_entrar = QPushButton("Entrar")
        self.btn_ir_a_registro = QPushButton("Crear cuenta")
        self.btn_ir_a_olvido = QPushButton("¿Olvidaste tu contraseña?")
        entrar = self._formulario("Iniciar sesión", "Entra con tu cuenta del PC.",
                                  (self.txt_usuario, self.txt_clave), self.btn_entrar, "¿No tienes cuenta?", self.btn_ir_a_registro,
                                  extra=self.btn_ir_a_olvido)

        # ---- crear cuenta
        self.txt_nombre = _campo("Nombre completo")
        self.txt_usuario_nuevo = _campo("Usuario (3 a 30: letras, números, punto o guion)")
        self.txt_clave_nueva = _campo("Contraseña", clave=True)
        self.txt_confirmacion = _campo("Repite la contraseña", clave=True)
        self.barra_fuerza = QProgressBar()
        self.barra_fuerza.setRange(0, 4)
        self.barra_fuerza.setTextVisible(False)
        self.barra_fuerza.setFixedHeight(6)
        self.lbl_fuerza = QLabel(FUERZA[0])
        self.lbl_fuerza.setObjectName("ayuda")
        self.btn_crear = QPushButton("Crear cuenta")
        self.btn_ir_a_entrar = QPushButton("Iniciar sesión")
        registro = self._formulario(
            "Crear cuenta", "La primera cuenta queda como administrador; las demás esperan a que un administrador les asigne el rol.",
            (self.txt_nombre, self.txt_usuario_nuevo, self.txt_clave_nueva, self.barra_fuerza, self.lbl_fuerza, self.txt_confirmacion),
            self.btn_crear, "¿Ya tienes cuenta?", self.btn_ir_a_entrar)

        # ---- contraseña olvidada
        self.txt_usuario_olvido = _campo("Usuario")
        self.txt_clave_olvido = _campo("Contraseña nueva", clave=True)
        self.txt_confirmacion_olvido = _campo("Repite la contraseña nueva", clave=True)
        self.btn_pedir_clave = QPushButton("Enviar solicitud")
        self.btn_volver = QPushButton("Iniciar sesión")
        olvido = self._formulario(
            "Contraseña nueva", "Escribe la que quieres usar. Un administrador la aprueba y desde entonces entras con ella.",
            (self.txt_usuario_olvido, self.txt_clave_olvido, self.txt_confirmacion_olvido), self.btn_pedir_clave,
            "¿Ya la recuerdas?", self.btn_volver)

        self.formularios = QStackedWidget()
        self.formularios.addWidget(entrar)
        self.formularios.addWidget(registro)
        self.formularios.addWidget(olvido)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        tarjeta.setFixedWidth(400)
        en_tarjeta = QVBoxLayout(tarjeta)
        en_tarjeta.setContentsMargins(28, 28, 28, 24)
        en_tarjeta.addWidget(self.formularios)
        en_tarjeta.addWidget(self.lbl_error)
        derecha = QVBoxLayout()
        derecha.addStretch(1)
        derecha.addWidget(tarjeta, 0, Qt.AlignmentFlag.AlignHCenter)
        derecha.addStretch(1)

        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.setSpacing(0)
        raiz.addWidget(marca, 2)
        raiz.addLayout(derecha, 3)

        self.btn_entrar.clicked.connect(self._entrar)
        self.txt_clave.returnPressed.connect(self._entrar)
        self.btn_crear.clicked.connect(self._crear)
        self.txt_confirmacion.returnPressed.connect(self._crear)
        self.btn_ir_a_registro.clicked.connect(lambda: self.mostrar_formulario(1))
        self.btn_ir_a_entrar.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_ir_a_olvido.clicked.connect(lambda: self.mostrar_formulario(2))
        self.btn_volver.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_pedir_clave.clicked.connect(self._pedir_clave)
        self.txt_confirmacion_olvido.returnPressed.connect(self._pedir_clave)
        self.txt_clave_nueva.textChanged.connect(self._medir_fuerza)

    def _formulario(self, titulo: str, ayuda: str, campos, boton: QPushButton, pregunta: str, enlace: QPushButton,
                    extra: QPushButton | None = None) -> QWidget:
        pagina = QWidget()
        pagina.setObjectName("formulario")
        lay = QVBoxLayout(pagina)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("tituloAcceso")
        texto = QLabel(ayuda)
        texto.setObjectName("ayuda")
        texto.setWordWrap(True)
        lay.addWidget(rotulo)
        lay.addWidget(texto)
        lay.addSpacing(6)
        for campo in campos:
            lay.addWidget(campo)
        boton.setObjectName("primario")
        boton.setMinimumHeight(40)
        if extra is not None:
            extra.setObjectName("enlace")
            extra.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(extra, 0, Qt.AlignmentFlag.AlignRight)
        lay.addSpacing(4)
        lay.addWidget(boton)
        pie = QHBoxLayout()
        pie.addStretch(1)
        etiqueta = QLabel(pregunta)
        etiqueta.setObjectName("ayuda")
        enlace.setObjectName("enlace")
        enlace.setCursor(Qt.CursorShape.PointingHandCursor)
        pie.addWidget(etiqueta)
        pie.addWidget(enlace)
        pie.addStretch(1)
        lay.addLayout(pie)
        lay.addStretch(1)  # el formulario corto no se estira: el espacio sobrante queda abajo
        return pagina

    # ------------------------------------------------------------------ API
    def mostrar_formulario(self, indice: int) -> None:
        """0 = iniciar sesión, 1 = crear cuenta, 2 = contraseña olvidada."""
        self.formularios.setCurrentIndex(indice)
        self._error("")

    def limpiar(self) -> None:
        """Deja la pantalla como al abrirla (al cerrar sesión no deben quedar contraseñas escritas)."""
        for campo in (self.txt_usuario, self.txt_clave, self.txt_nombre, self.txt_usuario_nuevo, self.txt_clave_nueva, self.txt_confirmacion,
                      self.txt_usuario_olvido, self.txt_clave_olvido, self.txt_confirmacion_olvido):
            campo.clear()
        self.mostrar_formulario(0)

    # ------------------------------------------------------------- internos
    def _error(self, mensaje: str) -> None:
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
        self.lbl_error.setStyleSheet("")

    def _aviso(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.setStyleSheet("color: #34D399; background: transparent;")
        self.lbl_error.show()

    def _ocupado(self, ocupado: bool) -> None:
        self.btn_entrar.setEnabled(not ocupado)
        self.btn_crear.setEnabled(not ocupado)
        self.btn_pedir_clave.setEnabled(not ocupado)

    def _medir_fuerza(self, clave: str) -> None:
        nivel = auth.fuerza(clave)
        self.barra_fuerza.setValue(nivel)
        self.lbl_fuerza.setText(FUERZA[nivel] if clave else FUERZA[0])

    def _lanzar(self, operacion, *args) -> None:
        self._error("")
        self._ocupado(True)
        self._runner.run(operacion, self._listo, self._fallo, *args, key="acceso")

    def _entrar(self) -> None:
        self._lanzar(_entrar_o_estado, self.txt_usuario.text(), self.txt_clave.text())

    def _crear(self) -> None:
        self._lanzar(_registrar_o_estado, self.txt_usuario_nuevo.text(), self.txt_nombre.text(),
                     self.txt_clave_nueva.text(), self.txt_confirmacion.text())

    def _pedir_clave(self) -> None:
        self._lanzar(auth.solicitar_clave, self.txt_usuario_olvido.text(), self.txt_clave_olvido.text(), self.txt_confirmacion_olvido.text())

    def _listo(self, resultado) -> None:
        self._ocupado(False)
        self.limpiar()
        if isinstance(resultado, auth.Sesion):
            self.entro.emit(resultado)
        elif isinstance(resultado, auth.CuentaSinAcceso):
            self.sin_acceso.emit(resultado)
        else:  # solicitud de contraseña: no se abre sesión, se avisa
            self._aviso(resultado)

    def _fallo(self, mensaje: str) -> None:
        self._ocupado(False)
        self._error(mensaje)


# Corren fuera del hilo de la interfaz. El estado de la cuenta vuelve como resultado (no como error): los errores
# solo llegan como texto y la pantalla del estado necesita sus datos.
def _entrar_o_estado(usuario: str, clave: str) -> auth.Sesion | auth.CuentaSinAcceso:
    try:
        return auth.iniciar_sesion(usuario, clave)
    except auth.CuentaSinAcceso as cuenta:
        return cuenta


def _registrar_o_estado(usuario: str, nombre: str, clave: str, confirmacion: str) -> auth.Sesion | auth.CuentaSinAcceso:
    sesion = auth.registrar(usuario, nombre, clave, confirmacion)
    return sesion if sesion is not None else auth.consultar_cuenta(usuario)
