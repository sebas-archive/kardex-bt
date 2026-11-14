"""Pantalla de acceso: iniciar sesión, crear cuenta o recuperar la contraseña. Sin sesión no se pasa de aquí.

El Administrador recupera con su pregunta de seguridad; Inventory deja una solicitud para que el Administrador
la apruebe. El correo es obligatorio al crear una cuenta del PC y la pregunta solo se pide a la primera cuenta.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from .. import auth, i18n
from ..i18n import t
from . import motion, widgets
from .base import QueryRunner

FUERZA = ("Mínimo 8 caracteres, con letras y números", "Débil", "Aceptable", "Buena", "Fuerte")


def _icono_estado(valido: bool) -> QIcon:
    """Check verde o X roja dibujados (sin emoji ni recursos externos)."""
    mapa = QPixmap(32, 32)
    mapa.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(mapa)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor("#10B981" if valido else "#F87171")
    pintor.setPen(QPen(color, 3.2, cap=Qt.PenCapStyle.RoundCap, join=Qt.PenJoinStyle.RoundJoin))
    if valido:
        pintor.drawPolyline(*[QPointF(x, y) for x, y in ((8, 17), (14, 23), (24, 10))])
    else:
        pintor.drawLine(10, 10, 22, 22)
        pintor.drawLine(22, 10, 10, 22)
    pintor.end()
    mapa.setDevicePixelRatio(2)
    return QIcon(mapa)


def _icono_ojo(abierto: bool) -> QIcon:
    mapa = QPixmap(40, 40)
    mapa.fill(Qt.GlobalColor.transparent)
    p = QPainter(mapa)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#8A8A8A"), 2.0, cap=Qt.PenCapStyle.RoundCap))
    p.drawEllipse(QPointF(20, 20), 10, 6.5)
    p.setBrush(QColor("#8A8A8A"))
    p.drawEllipse(QPointF(20, 20), 3.2, 3.2)
    if not abierto:
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(9, 30, 31, 10)
    p.end()
    mapa.setDevicePixelRatio(2)
    return QIcon(mapa)


def _campo(pista: str, clave: bool = False) -> QLineEdit:
    campo = QLineEdit()
    campo.setPlaceholderText(pista)
    campo.setMinimumHeight(38)
    if clave:
        campo.setEchoMode(QLineEdit.EchoMode.Password)
    return campo


class AccesoView(QWidget):
    """Dos formularios (entrar y crear cuenta) y el de recuperación; la validación corre fuera del hilo de la interfaz."""

    entro = pyqtSignal(object)       # auth.Sesion
    sin_acceso = pyqtSignal(object)  # auth.CuentaSinAcceso: pendiente o rechazada

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._primero = False

        marca = QFrame()
        marca.setObjectName("panelMarca")
        self._marca_panel = marca
        en_marca = QVBoxLayout(marca)
        en_marca.setContentsMargins(40, 40, 40, 40)
        titulo = QLabel(t("Gestión de inventario"))
        titulo.setStyleSheet("font-size: 26px; font-weight: 600;")
        titulo.setWordWrap(True)
        lema = QLabel(t("Conteo físico con el celular, sin red.\nLos datos llegan por Bluetooth y Oracle los concilia."))
        lema.setStyleSheet("font-size: 14px;")
        lema.setWordWrap(True)
        en_marca.addStretch(1)
        en_marca.addWidget(titulo)
        en_marca.addSpacing(8)
        en_marca.addWidget(lema)
        en_marca.addStretch(2)

        # ---- entrar
        self.txt_usuario = _campo(t("Usuario"))
        self.txt_clave = _campo(t("Contraseña"), clave=True)
        self._ojo_abierto = False
        self._accion_ojo = self.txt_clave.addAction(_icono_ojo(False), QLineEdit.ActionPosition.TrailingPosition)
        self._accion_ojo.setToolTip(t("Mostrar contraseña"))
        self._accion_ojo.triggered.connect(self._alternar_clave)
        self.btn_entrar = QPushButton(t("Entrar"))
        self.btn_ir_a_registro = QPushButton(t("Crear cuenta"))
        self.btn_ir_a_olvido = QPushButton(t("¿Olvidaste tu contraseña?"))
        entrar = self._formulario(t("Iniciar sesión"), t("Entra con tu cuenta del PC."),
                                  (self.txt_usuario, self.txt_clave), self.btn_entrar, t("¿No tienes cuenta?"),
                                  self.btn_ir_a_registro, extra=self.btn_ir_a_olvido)

        # ---- crear cuenta
        self.txt_nombre = _campo(t("Nombre completo"))
        self.txt_usuario_nuevo = _campo(t("Usuario (3 a 30: letras, números, punto o guion)"))
        self.txt_correo = _campo(t("Correo electrónico"))
        self.txt_clave_nueva = _campo(t("Contraseña"), clave=True)
        self.txt_confirmacion = _campo(t("Repite la contraseña"), clave=True)
        self.barra_fuerza = QProgressBar()
        self.barra_fuerza.setRange(0, 4)
        self.barra_fuerza.setTextVisible(False)
        self.barra_fuerza.setFixedHeight(6)
        self.lbl_fuerza = QLabel(t(FUERZA[0]))
        self.lbl_fuerza.setObjectName("ayuda")

        self._bloque_admin = QWidget()
        en_admin = QVBoxLayout(self._bloque_admin)
        en_admin.setContentsMargins(0, 0, 0, 0)
        en_admin.setSpacing(6)
        ayuda_admin = QLabel(t("Solo el Administrador usa pregunta de seguridad. Si eres Inventario, la solicitud va a aprobación."))
        ayuda_admin.setObjectName("ayuda")
        ayuda_admin.setWordWrap(True)
        self.combo_pregunta = QComboBox()
        self.combo_pregunta.addItem(t("Elige una pregunta…"), "")
        for pregunta in auth.PREGUNTAS:
            self.combo_pregunta.addItem(t(pregunta), pregunta)
        self.txt_respuesta = _campo(t("Respuesta de seguridad"))
        en_admin.addWidget(ayuda_admin)
        en_admin.addWidget(self.combo_pregunta)
        en_admin.addWidget(self.txt_respuesta)
        self._bloque_admin.hide()

        self.btn_crear = QPushButton(t("Crear cuenta"))
        self.btn_ir_a_entrar = QPushButton(t("Iniciar sesión"))
        registro = self._formulario(
            t("Crear cuenta"),
            t("La primera cuenta queda como administrador; las demás esperan a que un administrador les asigne el rol."),
            (self.txt_nombre, self.txt_usuario_nuevo, self.txt_correo, self.txt_clave_nueva, self.barra_fuerza,
             self.lbl_fuerza, self.txt_confirmacion, self._bloque_admin),
            self.btn_crear, t("¿Ya tienes cuenta?"), self.btn_ir_a_entrar)

        # ---- contraseña olvidada
        self.txt_usuario_olvido = _campo(t("Usuario"))
        self.txt_clave_olvido = _campo(t("Contraseña nueva"), clave=True)
        self.txt_confirmacion_olvido = _campo(t("Repite la contraseña nueva"), clave=True)
        self.lbl_pregunta = QLabel("")
        self.lbl_pregunta.setObjectName("ayuda")
        self.lbl_pregunta.setWordWrap(True)
        self.txt_respuesta_olvido = _campo(t("Respuesta de seguridad"))
        self.txt_respuesta_olvido.hide()
        self.btn_ver_pregunta = QPushButton(t("Ver pregunta"))
        self.btn_ver_pregunta.setObjectName("enlace")
        self.btn_pedir_clave = QPushButton(t("Enviar solicitud"))
        self.btn_volver = QPushButton(t("Iniciar sesión"))
        olvido = self._formulario(
            t("Contraseña nueva"),
            t("El Administrador responde su pregunta de seguridad. Inventario deja la solicitud para aprobación."),
            (self.txt_usuario_olvido, self.lbl_pregunta, self.btn_ver_pregunta, self.txt_respuesta_olvido,
             self.txt_clave_olvido, self.txt_confirmacion_olvido),
            self.btn_pedir_clave, t("¿Ya la recuerdas?"), self.btn_volver)

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
        self._tarjeta = tarjeta
        tarjeta.setFixedWidth(420)
        en_tarjeta = QVBoxLayout(tarjeta)
        en_tarjeta.setContentsMargins(28, 28, 28, 24)
        en_tarjeta.addWidget(self.formularios)
        en_tarjeta.addWidget(self.lbl_error)
        self._marco_tarjeta = QWidget()
        en_marco = QHBoxLayout(self._marco_tarjeta)
        en_marco.setContentsMargins(0, 0, 0, 0)
        en_marco.addWidget(tarjeta, 0, Qt.AlignmentFlag.AlignHCenter)
        derecha = QVBoxLayout()
        derecha.addStretch(1)
        derecha.addWidget(self._marco_tarjeta, 0, Qt.AlignmentFlag.AlignHCenter)
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
        self.btn_ir_a_registro.clicked.connect(self._ir_a_registro)
        self.btn_ir_a_entrar.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_ir_a_olvido.clicked.connect(lambda: self.mostrar_formulario(2))
        self.btn_volver.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_ver_pregunta.clicked.connect(self._ver_pregunta)
        self.btn_pedir_clave.clicked.connect(self._pedir_clave)
        self.txt_confirmacion_olvido.returnPressed.connect(self._pedir_clave)
        self.txt_clave_nueva.textChanged.connect(self._medir_fuerza)
        self._acciones: dict[QLineEdit, object] = {}
        self._preparar_validacion(self.txt_usuario, lambda x: (3 <= len(x) <= 30 and bool(re.fullmatch(r"[\w.\-]+", x))) if x else None)
        self._preparar_validacion(self.txt_clave, lambda x: (len(x) >= 8 and bool(re.search(r"[A-Za-z]", x)) and bool(re.search(r"\d", x))) if x else None)
        self._preparar_validacion(self.txt_usuario_nuevo, lambda x: (3 <= len(x) <= 30 and bool(re.fullmatch(r"[\w.\-]+", x))) if x else None)
        self._preparar_validacion(self.txt_correo, lambda x: ("@" in x and "." in x.split("@")[-1]) if x else None)
        self._preparar_validacion(self.txt_clave_nueva, lambda x: (len(x) >= 8 and bool(re.search(r"[A-Za-z]", x)) and bool(re.search(r"\d", x))) if x else None)
        self._preparar_validacion(self.txt_confirmacion, lambda x: (x == self.txt_clave_nueva.text() and len(x) >= 8) if x else None)
        self._ya_animado = False
        motion.sombra(tarjeta, "#000000", 30, 10, 120)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if not self._ya_animado:
            self._ya_animado = True
            if widgets.ANIMAR:
                motion.desvanecer(self._marca_panel, 0.0, 1.0, 300)
                motion.desvanecer(self._tarjeta, 0.0, 1.0, 380)
        QTimer.singleShot(0, self._enfocar)
        QTimer.singleShot(380, self._enfocar)

    def _enfocar(self) -> None:
        if not self.isVisible():
            return
        campo = {0: self.txt_usuario, 1: self.txt_nombre, 2: self.txt_usuario_olvido}.get(self.formularios.currentIndex())
        if campo is not None:
            campo.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _alternar_clave(self) -> None:
        self._ojo_abierto = not self._ojo_abierto
        self.txt_clave.setEchoMode(QLineEdit.EchoMode.Normal if self._ojo_abierto else QLineEdit.EchoMode.Password)
        self._accion_ojo.setIcon(_icono_ojo(self._ojo_abierto))
        self._accion_ojo.setToolTip(t("Ocultar contraseña") if self._ojo_abierto else t("Mostrar contraseña"))

    def _formulario(self, titulo: str, ayuda: str, campos, boton: QPushButton, pregunta: str, enlace: QPushButton,
                    extra: QPushButton | None = None) -> QWidget:
        pagina = QWidget()
        pagina.setObjectName("formulario")
        lay = QVBoxLayout(pagina)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("tituloAcceso")
        texto = QLabel(t(ayuda))
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
        etiqueta = QLabel(t(pregunta))
        etiqueta.setObjectName("ayuda")
        enlace.setObjectName("enlace")
        enlace.setCursor(Qt.CursorShape.PointingHandCursor)
        pie.addWidget(etiqueta)
        pie.addWidget(enlace)
        pie.addStretch(1)
        lay.addLayout(pie)
        lay.addStretch(1)
        return pagina

    # ------------------------------------------------------------------ validación viva
    def _preparar_validacion(self, campo: QLineEdit, regla) -> None:
        accion = campo.addAction(QIcon(), QLineEdit.ActionPosition.TrailingPosition)
        accion.setVisible(False)
        self._acciones[campo] = (accion, regla)
        campo.textChanged.connect(lambda x, c=campo: self._validar(c, x))

    def _validar(self, campo: QLineEdit, texto: str) -> None:
        accion, regla = self._acciones[campo]
        estado = regla(texto)
        if estado is None:
            accion.setVisible(False)
            campo.setProperty("valido", False)
            campo.setProperty("invalido", False)
        else:
            accion.setVisible(True)
            accion.setIcon(_icono_estado(bool(estado)))
            campo.setProperty("valido", bool(estado))
            campo.setProperty("invalido", not estado)
        campo.style().unpolish(campo)
        campo.style().polish(campo)

    def _medir_fuerza(self, clave: str) -> None:
        nivel = auth.fuerza(clave)
        self.barra_fuerza.setValue(nivel)
        colores = {0: "#2E2E2E", 1: "#F87171", 2: "#FBBF24", 3: "#34D399", 4: "#10B981"}
        self.barra_fuerza.setStyleSheet(
            f"QProgressBar {{ border: none; background: #232323; border-radius: 3px; }}"
            f"QProgressBar::chunk {{ background: {colores[nivel]}; border-radius: 3px; }}")
        self.lbl_fuerza.setText(t(FUERZA[nivel]) if clave else t(FUERZA[0]))
        self.lbl_fuerza.setStyleSheet(f"color: {colores[nivel] if clave else '#8A8A8A'}; background: transparent;")

    # ------------------------------------------------------------------ API
    def mostrar_formulario(self, indice: int) -> None:
        """0 = iniciar sesión, 1 = crear cuenta, 2 = contraseña olvidada."""
        self.formularios.setCurrentIndex(indice)
        self._error("")
        if indice == 1:
            self._consultar_primer_admin()

    def limpiar(self) -> None:
        for campo in (self.txt_usuario, self.txt_clave, self.txt_nombre, self.txt_usuario_nuevo, self.txt_correo,
                      self.txt_clave_nueva, self.txt_confirmacion, self.txt_usuario_olvido, self.txt_clave_olvido,
                      self.txt_confirmacion_olvido, self.txt_respuesta, self.txt_respuesta_olvido):
            campo.clear()
        self.combo_pregunta.setCurrentIndex(0)
        if self._ojo_abierto:
            self._alternar_clave()
        self.mostrar_formulario(0)

    # ------------------------------------------------------------- internos
    def _error(self, mensaje: str) -> None:
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
        self.lbl_error.setStyleSheet("")

    def _aviso(self, mensaje: str) -> None:
        self.lbl_error.setObjectName("avisoFormulario")
        self.lbl_error.setText(mensaje)
        self.lbl_error.setStyleSheet("color: #34D399; background: transparent;")
        self.lbl_error.show()

    def _ocupado(self, ocupado: bool) -> None:
        for boton in (self.btn_entrar, self.btn_crear, self.btn_pedir_clave):
            boton.setEnabled(not ocupado)

    def _lanzar(self, operacion, *args) -> None:
        self._error("")
        self._ocupado(True)
        self._runner.run(operacion, self._listo, self._fallo, *args, key="acceso")

    def _ir_a_registro(self) -> None:
        self.mostrar_formulario(1)

    def _consultar_primer_admin(self) -> None:
        self._runner.run(auth.hay_admin, self._primer_admin, lambda _m: None, key="primer-admin")

    def _primer_admin(self, hay: bool) -> None:
        self._primero = not hay
        self._bloque_admin.setVisible(self._primero)
        if self._primero:
            self.combo_pregunta.setCurrentIndex(0)

    def _entrar(self) -> None:
        if not self.txt_usuario.text().strip() or not self.txt_clave.text():
            self._error(t("Escribe tu usuario y tu contraseña."))
            motion.sacudir(self._marco_tarjeta, 9)
            return
        self._lanzar(_entrar_o_estado, self.txt_usuario.text(), self.txt_clave.text())

    def _crear(self) -> None:
        if self.txt_clave_nueva.text() != self.txt_confirmacion.text():
            self._error(t("Las contraseñas no coinciden."))
            motion.sacudir(self._marco_tarjeta, 9)
            return
        if self._primero and not self.combo_pregunta.currentData():
            self._error(t("Elige una pregunta de seguridad."))
            return
        self._lanzar(_registrar_o_estado, self.txt_usuario_nuevo.text(), self.txt_nombre.text(),
                     self.txt_clave_nueva.text(), self.txt_confirmacion.text(), self.txt_correo.text(),
                     self.combo_pregunta.currentData() or "", self.txt_respuesta.text())

    def _ver_pregunta(self) -> None:
        usuario = self.txt_usuario_olvido.text().strip()
        if not usuario:
            self._error(t("Escribe tu usuario."))
            return
        self._runner.run(auth.pregunta_de, self._mostrar_pregunta, lambda _m: None, usuario, key="pregunta")

    def _mostrar_pregunta(self, pregunta: str | None) -> None:
        if pregunta:
            self.lbl_pregunta.setText(t("Pregunta: {pregunta}", pregunta=t(pregunta)))
            self.txt_respuesta_olvido.show()
        else:
            self.lbl_pregunta.setText(t("Esta cuenta no usa pregunta de seguridad: la solicitud se enviará para aprobación."))
            self.txt_respuesta_olvido.hide()
            self.txt_respuesta_olvido.clear()

    def _pedir_clave(self) -> None:
        self._lanzar(auth.recuperar, self.txt_usuario_olvido.text(), self.txt_clave_olvido.text(),
                     self.txt_confirmacion_olvido.text(), self.txt_respuesta_olvido.text())

    def _listo(self, resultado) -> None:
        self._ocupado(False)
        self.limpiar()
        if isinstance(resultado, auth.Sesion):
            self.entro.emit(resultado)
        elif isinstance(resultado, auth.CuentaSinAcceso):
            self.sin_acceso.emit(resultado)
        else:
            self._aviso(str(resultado))
            if self.formularios.currentIndex() == 2:
                self.mostrar_formulario(0)

    def _fallo(self, mensaje: str) -> None:
        self._ocupado(False)
        self._error(mensaje)
        motion.sacudir(self._marco_tarjeta, 9)


# Corren fuera del hilo de la interfaz. El estado de la cuenta vuelve como resultado (no como error): los errores
# solo llegan como texto y la pantalla del estado necesita sus datos.
def _entrar_o_estado(usuario: str, clave: str) -> auth.Sesion | auth.CuentaSinAcceso:
    try:
        return auth.iniciar_sesion(usuario, clave)
    except auth.CuentaSinAcceso as cuenta:
        return cuenta


def _registrar_o_estado(usuario: str, nombre: str, clave: str, confirmacion: str, correo: str,
                        pregunta: str, respuesta: str) -> auth.Sesion | auth.CuentaSinAcceso:
    sesion = auth.registrar(usuario, nombre, clave, confirmacion, correo, pregunta, respuesta)
    return sesion if sesion is not None else auth.consultar_cuenta(usuario)
