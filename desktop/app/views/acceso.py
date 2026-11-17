"""Pantalla de Acceso: tarjeta de dos paneles (marca azul + formulario) con login, registro y recuperación.

La tarjeta se centra sobre un fondo azul y se desplaza si no cabe. La izquierda es siempre azul (degradado y
círculos pintados); la derecha sigue el tema claro/oscuro. El medidor de fuerza es una guía visual: la política
del backend no cambia (``auth._validar_clave``).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSettings, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QApplication, QMenu, QScrollArea, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import auth, fortaleza, i18n, tema
from ..i18n import t
from . import motion, motion_global, widgets
from .base import QueryRunner
from .iconos import icono
from .isla import isla


# Textos del proceso en la Isla: (mientras trabaja, al terminar bien, al fallar).
OP_ENTRAR = ("Iniciando sesión…", "Inicio de sesión exitoso", "No se pudo iniciar sesión")
OP_REGISTRO = ("Registrando usuario…", "Usuario registrado correctamente", "No se pudo crear la cuenta")
OP_RECUPERAR = ("Enviando solicitud…", "Solicitud enviada", "No se pudo recuperar la contraseña")


class FondoAcceso(QWidget):
    """Fondo limpio del tema, sin decoración exterior; solo la sombra de la tarjeta."""

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(tema.colores()["fondo"]))
        tarjeta = getattr(self, "_tarjeta", None)
        if tarjeta is not None:
            geo = QRectF(tarjeta.geometry())
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(10, 0, -1):
                p.setBrush(QColor(0, 0, 0, 6))
                p.drawRoundedRect(geo.adjusted(-i, -i + 6, i, i + 6), 18 + i, 18 + i)
        p.end()


class PanelMarca(QFrame):
    """Panel izquierdo 40 %: degradado azul, forma de superficie, esfera y círculo azules."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(360)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        # Sin fondo propio: la hoja global pintaba un cuadrado que asomaba en las esquinas redondeadas.
        self.setStyleSheet("PanelMarca { background: transparent; border: none; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 40, 20, 34)
        lay.setSpacing(10)
        self.lbl_marca = QLabel(t("GESTIÓN DE INVENTARIO"))
        self.lbl_marca.setStyleSheet("color: rgba(255,255,255,0.72); font-size: 10px; font-weight: 700; "
                                     "letter-spacing: 1.4px; background: transparent;")
        self.lbl_bienvenida = QLabel(t("BIENVENIDO"))
        self.lbl_bienvenida.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: 800; background: transparent;")
        self.lbl_bienvenida.setWordWrap(True)
        self.lbl_bienvenida.setMaximumWidth(235)
        self.lbl_imagen = QLabel(t("Conteo físico sin red.\nEl PC recibe por Bluetooth y Oracle concilia."))
        self.lbl_imagen.setStyleSheet("color: rgba(255,255,255,0.88); font-size: 12px; background: transparent;")
        self.lbl_imagen.setWordWrap(True)
        self.lbl_imagen.setMaximumWidth(160)
        lay.addStretch(1)
        lay.addWidget(self.lbl_marca)
        lay.addWidget(self.lbl_bienvenida)
        lay.addSpacing(4)
        lay.addWidget(self.lbl_imagen)
        lay.addStretch(2)

    def retraducir(self) -> None:
        self.lbl_marca.setText(t("GESTIÓN DE INVENTARIO"))
        self.lbl_bienvenida.setText(t("BIENVENIDO"))
        self.lbl_imagen.setText(t("Conteo físico sin red.\nEl PC recibe por Bluetooth y Oracle concilia."))

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ancho, alto = float(self.width()), float(self.height())
        r = 18.0

        # Recorte exterior: esquinas izquierdas redondeadas (la superficie del formulario queda a la derecha).
        recorte = QPainterPath()
        # Rectángulo redondeado circular (mismo radio que la tarjeta); las esquinas derechas quedan fuera del widget.
        recorte.addRoundedRect(QRectF(0, 0, ancho + r, alto), r, r)
        p.setClipPath(recorte)

        # Base: superficie del formulario, para que el panel se funda con el área blanca de la derecha.
        p.setPen(Qt.PenStyle.NoPen)
        # Empieza pasadas las esquinas redondeadas: el borde antialiasado del recorte dejaría un filo blanco.
        p.fillRect(QRectF(r, 0, ancho - r, alto), QColor(tema.colores()["tarjeta"]))

        # Gran círculo azul (como la referencia): sale por arriba/izquierda y su borde derecho es una curva
        # convexa continua que se queda dentro del panel; debajo de él se ve la superficie.
        cx, cy, radio = 40.0, alto * 0.39, 305.0
        g = QLinearGradient(0, 0, ancho * 0.45, cy + radio)
        g.setColorAt(0.0, QColor("#052E25"))
        g.setColorAt(0.55, QColor("#07503F"))
        g.setColorAt(1.0, QColor("#059669"))
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), radio, radio)

        # Círculo azul parcial desde la esquina inferior izquierda (se solapa con el grande).
        gradiente = QRadialGradient(40, alto * 0.80, 260)
        gradiente.setColorAt(0.0, QColor("#10B981"))
        gradiente.setColorAt(1.0, QColor("#047857"))
        p.setBrush(gradiente)
        p.drawEllipse(QPointF(-20, alto * 0.90), 210, 210)

        # Esfera azul clara abajo a la derecha, recortada por el borde del panel.
        esfera = QPointF(222, alto * 0.85)
        gradiente = QRadialGradient(QPointF(esfera.x() - 45, esfera.y() - 60), 190)
        gradiente.setColorAt(0.0, QColor("#6EE7B7"))
        gradiente.setColorAt(0.6, QColor("#10B981"))
        gradiente.setColorAt(1.0, QColor("#059669"))
        p.setBrush(gradiente)
        p.drawEllipse(esfera, 130, 130)
        p.end()



class CasillaAcceso(QCheckBox):
    """Casilla de verificación: cuadro con borde que se rellena de azul y muestra una palomita al marcarse."""

    LADO = 18

    def __init__(self, texto: str, parent: QWidget | None = None) -> None:
        super().__init__(texto, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("CasillaAcceso { background: transparent; border: none; }")

    def sizeHint(self) -> QSize:
        self.ensurePolished()  # la fuente de la hoja de estilos debe estar aplicada antes de medir el texto
        ancho = self.LADO + 10 + self.fontMetrics().horizontalAdvance(self.text())
        return QSize(ancho + 12, max(self.LADO, self.fontMetrics().height()) + 6)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def changeEvent(self, evento) -> None:
        super().changeEvent(evento)
        if evento.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.updateGeometry()

    def hitButton(self, _pos) -> bool:
        return True

    def paintEvent(self, _evento) -> None:
        c = tema.colores()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = (self.height() - self.LADO) / 2
        caja = QRectF(1, y, self.LADO - 2, self.LADO - 2)
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["acento"]))
            p.drawRoundedRect(caja, 5, 5)
            pluma = QPen(QColor("#FFFFFF"), 2.0)
            pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
            pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pluma)
            p.drawPolyline([QPointF(caja.left() + 4, caja.center().y() + 0.5),
                            QPointF(caja.left() + 7, caja.center().y() + 3.5),
                            QPointF(caja.right() - 3.5, caja.top() + 4.5)])
        else:
            p.setPen(QPen(QColor(c["borde_fuerte"]), 1.5))
            p.setBrush(QColor(c["tarjeta"]))
            p.drawRoundedRect(caja, 5, 5)
        if self.hasFocus():
            p.setPen(QPen(QColor(c["acento"]), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(caja.adjusted(-2, -2, 2, 2), 7, 7)
        p.setPen(QColor(c["texto"]))
        p.drawText(QRectF(self.LADO + 10, 0, self.width() - self.LADO - 10, self.height()),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), self.text())
        p.end()


class MedidorFuerza(QWidget):
    """Cuatro segmentos, etiqueta de fuerza, reglas con check y aviso de patrón."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("medidorFuerza")
        self.setAccessibleName(t("Seguridad de la contraseña"))
        self.puntaje = 0
        self.resultado = fortaleza.evaluar("")
        self._segmentos: list[QFrame] = []
        self._reglas: list[QLabel] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(5)
        rotulo = QLabel(t("Seguridad de la contraseña"))
        rotulo.setObjectName("ayuda")
        lay.addWidget(rotulo)
        fila = QHBoxLayout()
        fila.setSpacing(4)
        for _ in range(4):
            seg = QFrame()
            seg.setFixedHeight(5)
            seg.setMinimumWidth(40)
            self._segmentos.append(seg)
            fila.addWidget(seg, 1)
        self.lbl_etiqueta = QLabel(t("Vacía"))
        self.lbl_etiqueta.setObjectName("ayuda")
        fila.addWidget(self.lbl_etiqueta)
        lay.addLayout(fila)
        reglas = QGridLayout()
        reglas.setHorizontalSpacing(14)
        reglas.setVerticalSpacing(2)
        for i, (texto, _clave) in enumerate(fortaleza.reglas()):
            lbl = QLabel(f"○ {t(texto)}")
            lbl.setObjectName("ayuda")
            lbl.setWordWrap(True)
            self._reglas.append(lbl)
            reglas.addWidget(lbl, i // 2, i % 2)
        lay.addLayout(reglas)
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setObjectName("errorFormulario")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.hide()
        lay.addWidget(self.lbl_aviso)
        self.actualizar("")

    def etiqueta(self) -> str:
        return self.lbl_etiqueta.text()

    def actualizar(self, clave: str) -> None:
        resultado = fortaleza.evaluar(clave)
        self.resultado = resultado
        self.puntaje = resultado.puntaje
        c = tema.colores()
        color = c["error"] if resultado.aviso else c["acento"]
        for i, seg in enumerate(self._segmentos):
            activo = (not resultado.vacia) and i < resultado.puntaje
            seg.setStyleSheet(f"background: {color if activo else c['texto_suave']}; border-radius: 3px;")
        self.lbl_etiqueta.setText(t(resultado.etiqueta))
        color_etiqueta = c["texto_suave"] if resultado.vacia else (c["error"] if resultado.aviso else color)
        self.lbl_etiqueta.setStyleSheet(
            f"color: {color_etiqueta}; background: transparent; font-weight: 600;")
        for (texto, cumple), lbl in zip(resultado.reglas, self._reglas):
            lbl.setText(("✓ " if cumple else "○ ") + t(texto))
            lbl.setStyleSheet(f"color: {c['texto_suave'] if not cumple else c['acento']}; background: transparent;")
        self.lbl_aviso.setText(t(resultado.aviso) if resultado.aviso else "")
        self.lbl_aviso.setVisible(bool(resultado.aviso))
        self.setAccessibleDescription(
            f"{t('Seguridad de la contraseña')}: {t(resultado.etiqueta)}"
            + (f". {t(resultado.aviso)}" if resultado.aviso else ""))


class AccesoView(QWidget):
    """Login, registro y recuperación en una tarjeta de dos paneles; la validación corre fuera del hilo de la UI."""

    entro = pyqtSignal(object)       # auth.Sesion
    sin_acceso = pyqtSignal(object)  # auth.CuentaSinAcceso

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._primero = False
        self._error_actual = ""
        self._op = OP_ENTRAR
        self._id_proceso: int | None = None
        self._pregunta_actual: str | None = None
        self._pregunta_texto = ""
        self._tema_invitado_elegido = False
        self._idioma_invitado_elegido = False
        self._ajustes = QSettings("GestionInventario", "Acceso")
        self._guest_tema = "claro"
        self._guest_idioma = "es"
        i18n.set_idioma(self._guest_idioma)
        tema.aplicar(QApplication.instance(), self._guest_tema)

        # ---------------------------------------------------------- fondo y tarjeta
        self._fondo = FondoAcceso()
        self._fondo.setObjectName("fondoAcceso")
        self._tarjeta = QFrame()
        self._tarjeta.setObjectName("tarjetaAcceso")
        self._tarjeta.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._tarjeta.setFixedSize(900, 600)
        self._fondo._tarjeta = self._tarjeta
        en_tarjeta = QHBoxLayout(self._tarjeta)
        en_tarjeta.setContentsMargins(0, 0, 0, 0)
        en_tarjeta.setSpacing(0)
        self._marca_panel = PanelMarca()
        self._marca_panel.setMinimumWidth(360)
        self._marca_panel.setMaximumWidth(360)
        self._marca_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._panel_form = QWidget()
        self._panel_form.setObjectName("panelFormulario")
        en_tarjeta.addWidget(self._marca_panel, 0)
        en_tarjeta.addWidget(self._panel_form, 1)
        en_tarjeta.setStretch(0, 0)
        en_tarjeta.setStretch(1, 1)

        en_fondo = QVBoxLayout(self._fondo)
        en_fondo.setContentsMargins(28, 28, 28, 28)
        en_fondo.addStretch(1)
        en_fondo.addWidget(self._tarjeta, 0, Qt.AlignmentFlag.AlignHCenter)
        en_fondo.addStretch(1)
        self._scroll = QScrollArea()
        self._scroll.setObjectName("scrollAcceso")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._fondo)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(self._scroll)
        # ---------------------------------------------------------- páginas
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        self.formularios = QStackedWidget()
        self._scroll_form = QScrollArea()
        self._scroll_form.setObjectName("scrollAcceso")
        self._scroll_form.setWidgetResizable(True)
        self._scroll_form.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_form.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_form.setWidget(self.formularios)
        for transparente in (self._scroll_form.viewport(), self.formularios):
            transparente.setAutoFillBackground(False)
            transparente.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        en_form = QVBoxLayout(self._panel_form)
        en_form.setContentsMargins(32, 40, 40, 24)
        en_form.setSpacing(10)
        en_form.addWidget(self._scroll_form, 1)
        en_form.addWidget(self.lbl_error)

        self._montar_paginas()
        self._conectar()
        self._cargar_recordado()
        self.btn_config = QToolButton(self)
        self.btn_config.setObjectName("configAcceso")
        self.btn_config.setIcon(icono("Configuración", tam=18))
        self.btn_config.setToolTip(t("Apariencia e idioma"))
        self.btn_config.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_config.setFixedSize(36, 36)
        self.btn_config.setAutoRaise(True)
        self.btn_config.clicked.connect(self._menu_config)
        self.btn_config.raise_()

    # ------------------------------------------------------------------ construcción de páginas
    def _pagina(self, titulo: str, subtitulo: str) -> tuple[QWidget, QVBoxLayout]:
        pagina = QWidget()
        pagina.setObjectName("paginaAcceso")
        pagina.setAutoFillBackground(False)
        lay = QVBoxLayout(pagina)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)
        rotulo = QLabel(t(titulo))
        rotulo.setObjectName("tituloFormulario")
        texto = QLabel(t(subtitulo))
        texto.setObjectName("subtituloFormulario")
        texto.setWordWrap(True)
        lay.addWidget(rotulo)
        lay.addWidget(texto)
        lay.addSpacing(8)
        return pagina, lay

    def _campo(self, pista: str, icono_nombre: str, clave: bool = False,
               con_ojo: bool = False) -> tuple[QFrame, QLineEdit, object | None]:
        caja = QFrame()
        caja.setObjectName("campoAcceso")
        fila = QHBoxLayout(caja)
        fila.setContentsMargins(12, 0, 8, 0)
        fila.setSpacing(8)
        imagen = QLabel()
        imagen.setPixmap(icono(icono_nombre, color=tema.colores()["texto_suave"], tam=18).pixmap(18, 18))
        imagen.setFixedSize(18, 18)
        fila.addWidget(imagen)
        campo = QLineEdit()
        campo.setObjectName("campoTexto")
        campo.setPlaceholderText(t(pista))
        campo.setMinimumHeight(40)
        if clave:
            campo.setEchoMode(QLineEdit.EchoMode.Password)
        fila.addWidget(campo, 1)
        accion = None
        if con_ojo:
            accion = campo.addAction(icono("ojo", color=tema.colores()["texto_suave"]), QLineEdit.ActionPosition.TrailingPosition)
            accion.setToolTip(t("Mostrar contraseña"))
            accion.triggered.connect(lambda _c=False, x=campo, a=accion: self._alternar_clave(x, a))
        return caja, campo, accion

    def _construir_login(self) -> QWidget:
        pagina, lay = self._pagina("Iniciar sesión", "Accede con tu cuenta del PC.")
        lay.insertStretch(0, 1)
        caja_u, self.txt_usuario, _ = self._campo("Usuario", "usuario")
        lay.addWidget(caja_u)
        caja_c, self.txt_clave, self._accion_ojo = self._campo("Contraseña", "candado", clave=True, con_ojo=True)
        lay.addWidget(caja_c)
        self.txt_clave.returnPressed.connect(self._entrar)

        fila = QHBoxLayout()
        self.chk_recordar = CasillaAcceso(t("Recordar usuario"))
        self.btn_ir_a_olvido = QPushButton(t("¿Olvidaste tu contraseña?"))
        self.btn_ir_a_olvido.setObjectName("enlaceAzul")
        self.btn_ir_a_olvido.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.addWidget(self.chk_recordar)
        fila.addStretch(1)
        fila.addWidget(self.btn_ir_a_olvido)
        lay.addLayout(fila)

        self.btn_entrar = QPushButton(t("Entrar"))
        self.btn_entrar.setObjectName("botonPrincipal")
        self.btn_entrar.setMinimumHeight(42)
        lay.addWidget(self.btn_entrar)

        lay.addSpacing(4)
        linea_izq = QFrame()
        linea_izq.setObjectName("separadorAcceso")
        linea_izq.setFixedHeight(1)
        linea_der = QFrame()
        linea_der.setObjectName("separadorAcceso")
        linea_der.setFixedHeight(1)
        o = QLabel(t("o"))
        o.setObjectName("oAcceso")
        o.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fila_o = QHBoxLayout()
        fila_o.setSpacing(10)
        fila_o.addWidget(linea_izq, 1)
        fila_o.addWidget(o)
        fila_o.addWidget(linea_der, 1)
        lay.addLayout(fila_o)

        self.btn_ir_a_registro = QPushButton(t("Crear cuenta"))
        self.btn_ir_a_registro.setObjectName("botonSecundario")
        self.btn_ir_a_registro.setMinimumHeight(40)
        lay.addWidget(self.btn_ir_a_registro)
        lay.addStretch(1)
        return pagina

    def _construir_registro(self) -> QWidget:
        pagina, lay = self._pagina(
            "Crear cuenta",
            "La primera cuenta queda como administrador; las demás esperan a que un administrador les asigne el rol.")
        caja_u, self.txt_usuario_nuevo, _ = self._campo("Usuario (3 a 30: letras, números, punto o guion)", "usuario")
        caja_n, self.txt_nombre, _ = self._campo("Nombre completo", "usuario")
        caja_c, self.txt_correo, _ = self._campo("Correo electrónico", "correo")
        caja_p, self.txt_clave_nueva, self._accion_ojo_nueva = self._campo("Contraseña", "candado", clave=True, con_ojo=True)
        caja_pc, self.txt_confirmacion, _ = self._campo("Repite la contraseña", "candado", clave=True)
        for caja in (caja_u, caja_n, caja_c, caja_p, caja_pc):
            lay.addWidget(caja)
        self.medidor = MedidorFuerza()
        lay.addWidget(self.medidor)
        self.txt_clave_nueva.textChanged.connect(self.medidor.actualizar)

        self._bloque_admin = QWidget()
        en_admin = QVBoxLayout(self._bloque_admin)
        en_admin.setContentsMargins(0, 2, 0, 0)
        en_admin.setSpacing(6)
        ayuda = QLabel(t("Solo el Administrador usa pregunta de seguridad. Si eres Inventario, la solicitud va a aprobación."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.combo_pregunta = QComboBox()
        self.combo_pregunta.setObjectName("campoCombo")
        self.combo_pregunta.addItem(t("Elige una pregunta…"), "")
        for pregunta in auth.PREGUNTAS:
            self.combo_pregunta.addItem(t(pregunta), pregunta)
        caja_r, self.txt_respuesta, _ = self._campo("Respuesta de seguridad", "candado")
        en_admin.addWidget(ayuda)
        en_admin.addWidget(self.combo_pregunta)
        en_admin.addWidget(caja_r)
        self._bloque_admin.hide()
        lay.addWidget(self._bloque_admin)

        self.btn_crear = QPushButton(t("Crear cuenta"))
        self.btn_crear.setObjectName("botonPrincipal")
        self.btn_crear.setMinimumHeight(42)
        lay.addWidget(self.btn_crear)
        self.txt_confirmacion.returnPressed.connect(self._crear)
        self.btn_ir_a_entrar = QPushButton(t("Volver a iniciar sesión"))
        self.btn_ir_a_entrar.setObjectName("enlaceAzul")
        self.btn_ir_a_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.btn_ir_a_entrar)
        pie.addStretch(1)
        lay.addLayout(pie)
        lay.addStretch(1)
        return pagina

    def _construir_recuperacion(self) -> QWidget:
        pagina, lay = self._pagina(
            "Recuperar contraseña",
            "El Administrador responde su pregunta de seguridad. Inventario deja la solicitud para aprobación.")
        lay.insertStretch(0, 1)
        caja_u, self.txt_usuario_olvido, _ = self._campo("Usuario", "usuario")
        lay.addWidget(caja_u)
        self.lbl_pregunta = QLabel(t("Escribe tu usuario y pulsa Ver pregunta."))
        self.lbl_pregunta.setObjectName("ayuda")
        self.lbl_pregunta.setWordWrap(True)
        lay.addWidget(self.lbl_pregunta)
        self.btn_ver_pregunta = QPushButton(t("Ver pregunta"))
        self.btn_ver_pregunta.setObjectName("enlaceAzul")
        self.btn_ver_pregunta.setCursor(Qt.CursorShape.PointingHandCursor)
        fila = QHBoxLayout()
        fila.addStretch(1)
        fila.addWidget(self.btn_ver_pregunta)
        lay.addLayout(fila)
        caja_r, self.txt_respuesta_olvido, _ = self._campo("Respuesta de seguridad", "candado")
        caja_r.hide()
        self._caja_respuesta_olvido = caja_r
        lay.addWidget(caja_r)
        caja_n, self.txt_clave_olvido, _ = self._campo("Contraseña nueva", "candado", clave=True, con_ojo=True)
        caja_c, self.txt_confirmacion_olvido, _ = self._campo("Repite la contraseña nueva", "candado", clave=True)
        lay.addWidget(caja_n)
        lay.addWidget(caja_c)
        self.btn_pedir_clave = QPushButton(t("Enviar solicitud"))
        self.btn_pedir_clave.setObjectName("botonPrincipal")
        self.btn_pedir_clave.setMinimumHeight(42)
        lay.addWidget(self.btn_pedir_clave)
        self.txt_confirmacion_olvido.returnPressed.connect(self._pedir_clave)
        self.btn_volver = QPushButton(t("Volver a iniciar sesión"))
        self.btn_volver.setObjectName("enlaceAzul")
        self.btn_volver.setCursor(Qt.CursorShape.PointingHandCursor)
        pie = QHBoxLayout()
        pie.addStretch(1)
        pie.addWidget(self.btn_volver)
        pie.addStretch(1)
        lay.addLayout(pie)
        lay.addStretch(1)
        return pagina

    def _montar_paginas(self) -> None:
        for pagina in (self._construir_login(), self._construir_registro(), self._construir_recuperacion()):
            self.formularios.addWidget(pagina)

    # ------------------------------------------------------------------ engranaje y preferencias de invitado
    def _construir_menu_config(self) -> QMenu:
        menu = QMenu(self)
        self._menu_config_acciones: dict[str, dict[str, object]] = {"tema": {}, "idioma": {}}
        apariencia = menu.addMenu(t("Apariencia"))
        for modo in ("claro", "sistema", "oscuro"):
            accion = apariencia.addAction(t(tema.NOMBRE_MODO[modo]))
            accion.setCheckable(True)
            accion.setChecked(self._guest_tema == modo)
            accion.triggered.connect(lambda _marcada=False, m=modo: self._elegir_tema_invitado(m))
            self._menu_config_acciones["tema"][modo] = accion
        idioma = menu.addMenu(t("Idioma"))
        for codigo, nombre in (("es", "Español"), ("en", "English")):
            accion = idioma.addAction(t(nombre))
            accion.setCheckable(True)
            accion.setChecked(self._guest_idioma == codigo)
            accion.triggered.connect(lambda _marcada=False, c=codigo: self._elegir_idioma_invitado(c))
            self._menu_config_acciones["idioma"][codigo] = accion
        return menu

    def _menu_config(self) -> None:
        menu = self._construir_menu_config()
        menu.exec(self.btn_config.mapToGlobal(QPoint(0, self.btn_config.height() + 4)))

    def _elegir_tema_invitado(self, modo: str) -> None:
        if modo not in tema.MODOS:
            return
        self._guest_tema = modo
        self._tema_invitado_elegido = True
        tema.aplicar(QApplication.instance(), modo)
        self._actualizar_tema()

    def _elegir_idioma_invitado(self, codigo: str) -> None:
        if codigo not in i18n.IDIOMAS:
            return
        self._guest_idioma = codigo
        self._idioma_invitado_elegido = True
        i18n.set_idioma(codigo)
        self._reconstruir_idioma()

    def preferencias_temporales(self) -> tuple[str | None, str | None]:
        """Las elecciones explícitas de Acceso para esta ejecución, sin persistirlas en la cuenta."""
        return (self._guest_tema if self._tema_invitado_elegido else None,
                self._guest_idioma if self._idioma_invitado_elegido else None)

    def _actualizar_tema(self) -> None:
        self._fondo.update()
        self._marca_panel.update()
        self.btn_config.setIcon(icono("Configuración", tam=18))
        self.medidor.actualizar(self.txt_clave_nueva.text())
        self.update()

    def _aplicar_preferencias_invitado(self) -> None:
        if self._guest_idioma != i18n.idioma():
            i18n.set_idioma(self._guest_idioma)
            self._reconstruir_idioma()
        if self._guest_tema != tema.modo():
            tema.aplicar(QApplication.instance(), self._guest_tema)
        self._actualizar_tema()

    def _reconstruir_idioma(self) -> None:
        """Rehace las páginas al cambiar de idioma conservando formulario, modo y valores escritos."""
        indice = self.formularios.currentIndex()
        nombres = ("txt_usuario", "txt_clave", "txt_nombre", "txt_usuario_nuevo", "txt_correo",
                   "txt_clave_nueva", "txt_confirmacion", "txt_usuario_olvido", "txt_clave_olvido",
                   "txt_confirmacion_olvido", "txt_respuesta", "txt_respuesta_olvido")
        valores = {nombre: getattr(self, nombre).text() for nombre in nombres}
        error = self._error_actual
        primero = self._primero
        pregunta, pregunta_texto = self._pregunta_actual, self._pregunta_texto
        recordar = self.chk_recordar.isChecked()
        respuesta_olvido = self.txt_respuesta_olvido.text()
        pregunta_sel = self.combo_pregunta.currentData()
        while self.formularios.count():
            pagina = self.formularios.widget(0)
            self.formularios.removeWidget(pagina)
            pagina.deleteLater()
        self._marca_panel.retraducir()
        self._montar_paginas()
        self._conectar()
        for nombre, texto in valores.items():
            getattr(self, nombre).setText(texto)
        self.combo_pregunta.setCurrentIndex(max(0, self.combo_pregunta.findData(pregunta_sel)))
        self.chk_recordar.setChecked(recordar)
        self._primero = primero
        self._bloque_admin.setVisible(primero)
        self.medidor.actualizar(self.txt_clave_nueva.text())
        if pregunta:
            self._pregunta_actual, self._pregunta_texto = pregunta, pregunta_texto
            self.lbl_pregunta.setText(t("Pregunta: {pregunta}", pregunta=t(pregunta)))
            self._caja_respuesta_olvido.show()
            self.txt_respuesta_olvido.setText(respuesta_olvido)
        self.formularios.setCurrentIndex(indice)
        self._scroll_form.verticalScrollBar().setValue(0)
        if error:
            self._error(t(error))
        else:
            self._error("")
        QTimer.singleShot(0, self._enfocar)

    # ------------------------------------------------------------------ señales
    def _conectar(self) -> None:
        self.btn_entrar.clicked.connect(self._entrar)
        self.btn_crear.clicked.connect(self._crear)
        self.btn_ir_a_registro.clicked.connect(self._ir_a_registro)
        self.btn_ir_a_entrar.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_ir_a_olvido.clicked.connect(lambda: self.mostrar_formulario(2))
        self.btn_volver.clicked.connect(lambda: self.mostrar_formulario(0))
        self.btn_ver_pregunta.clicked.connect(self._ver_pregunta)
        self.btn_pedir_clave.clicked.connect(self._pedir_clave)

    # ------------------------------------------------------------------ API
    def mostrar_formulario(self, indice: int) -> None:
        """0 = iniciar sesión, 1 = crear cuenta, 2 = contraseña olvidada."""
        motion_global.cambiar_pila(self.formularios, indice)
        self._scroll_form.verticalScrollBar().setValue(0)
        self._error_actual = ""
        self._error("")
        if indice == 1:
            self._consultar_primer_admin()
        QTimer.singleShot(0, self._enfocar)

    def limpiar(self) -> None:
        for campo in (self.txt_usuario, self.txt_clave, self.txt_nombre, self.txt_usuario_nuevo, self.txt_correo,
                      self.txt_clave_nueva, self.txt_confirmacion, self.txt_usuario_olvido, self.txt_clave_olvido,
                      self.txt_confirmacion_olvido, self.txt_respuesta, self.txt_respuesta_olvido):
            campo.clear()
        if self.txt_clave.echoMode() == QLineEdit.EchoMode.Normal:
            self._alternar_clave(self.txt_clave, self._accion_ojo)
        if self.txt_clave_nueva.echoMode() == QLineEdit.EchoMode.Normal:
            self._alternar_clave(self.txt_clave_nueva, self._accion_ojo_nueva)
        self.combo_pregunta.setCurrentIndex(0)
        self.medidor.actualizar("")
        self._bloque_admin.hide()
        self._caja_respuesta_olvido.hide()
        self.lbl_pregunta.setText(t("Escribe tu usuario y pulsa Ver pregunta."))
        self._cargar_recordado()
        self.mostrar_formulario(0)

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        if hasattr(self, "_tarjeta"):
            ancho = max(760, min(900, self.width() - 56))
            self._tarjeta.setFixedWidth(ancho)
        if hasattr(self, "btn_config"):
            self.btn_config.move(self.width() - 56, 20)
            self.btn_config.raise_()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if hasattr(self, "_tarjeta"):
            self._tarjeta.setFixedWidth(max(760, min(900, self.width() - 56)))
        if hasattr(self, "btn_config"):
            self.btn_config.move(self.width() - 56, 20)
            self.btn_config.raise_()
            self._aplicar_preferencias_invitado()
        QTimer.singleShot(0, self._enfocar)

    def _enfocar(self) -> None:
        if not self.isVisible():
            return
        campo = {0: self.txt_usuario, 1: self.txt_usuario_nuevo, 2: self.txt_usuario_olvido}.get(self.formularios.currentIndex())
        if campo is not None:
            campo.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    # ------------------------------------------------------------------ recordar usuario
    def _cargar_recordado(self) -> None:
        usuario = str(self._ajustes.value("usuario", "") or "")
        if usuario:
            self.txt_usuario.setText(usuario)
            self.chk_recordar.setChecked(True)
        else:
            self.chk_recordar.setChecked(False)

    def _guardar_recordado(self) -> None:
        usuario = self.txt_usuario.text().strip()
        if self.chk_recordar.isChecked() and usuario:
            self._ajustes.setValue("usuario", usuario)
        else:
            self._ajustes.remove("usuario")

    # ------------------------------------------------------------------ contraseña visible
    def _alternar_clave(self, campo: QLineEdit, accion) -> None:
        visible = campo.echoMode() == QLineEdit.EchoMode.Normal
        campo.setEchoMode(QLineEdit.EchoMode.Password if visible else QLineEdit.EchoMode.Normal)
        accion.setIcon(icono("ojo" if visible else "ojo_off", color=tema.colores()["texto_suave"]))
        accion.setToolTip(t("Mostrar contraseña") if visible else t("Ocultar contraseña"))

    # ------------------------------------------------------------- flujos
    def _error(self, mensaje: str, validacion: bool = False) -> None:
        """Errores y validaciones del formulario van a la Isla; ``""`` cierra el que quedó abierto."""
        self.lbl_error.setText(mensaje)  # el texto sigue consultable; la etiqueta ya no se muestra
        if not mensaje:
            isla.cerrar(clave="acceso-error")
        elif validacion:
            isla.advertencia(mensaje, clave="acceso-error")
        else:
            isla.error(t(self._op[2]), mensaje, clave="acceso-error")

    def _aviso(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        isla.exito(t(self._op[1]), mensaje)

    def _ocupado(self, ocupado: bool) -> None:
        for boton in (self.btn_entrar, self.btn_crear, self.btn_pedir_clave):
            boton.setEnabled(not ocupado)

    def _lanzar(self, operacion, *args) -> None:
        self._error("")
        self._ocupado(True)
        self._id_proceso = isla.cargando(t(self._op[0]))
        self._runner.run(operacion, self._listo, self._fallo, *args, key="acceso")

    def _ir_a_registro(self) -> None:
        self.mostrar_formulario(1)

    def _consultar_primer_admin(self) -> None:
        self._runner.run(auth.hay_admin, self._primer_admin, lambda _m: None, key="primer-admin")

    def _primer_admin(self, hay: bool) -> None:
        self._primero = not hay
        self._bloque_admin.setVisible(self._primero)

    def _entrar(self) -> None:
        if not self.txt_usuario.text().strip() or not self.txt_clave.text():
            self._error(t("Escribe tu usuario y tu contraseña."), validacion=True)
            motion.sacudir(self._tarjeta, 9)
            return
        self._op = OP_ENTRAR
        self._lanzar(_entrar_o_estado, self.txt_usuario.text(), self.txt_clave.text())

    def _crear(self) -> None:
        if self.txt_clave_nueva.text() != self.txt_confirmacion.text():
            self._error(t("Las contraseñas no coinciden."), validacion=True)
            motion.sacudir(self._tarjeta, 9)
            return
        if self._primero and not self.combo_pregunta.currentData():
            self._error(t("Elige una pregunta de seguridad."), validacion=True)
            return
        self._op = OP_REGISTRO
        self._lanzar(_registrar_o_estado, self.txt_usuario_nuevo.text(), self.txt_nombre.text(),
                     self.txt_clave_nueva.text(), self.txt_confirmacion.text(), self.txt_correo.text(),
                     self.combo_pregunta.currentData() or "", self.txt_respuesta.text())

    def _ver_pregunta(self) -> None:
        usuario = self.txt_usuario_olvido.text().strip()
        if not usuario:
            self._error(t("Escribe tu usuario."), validacion=True)
            return
        self._runner.run(auth.pregunta_de, self._mostrar_pregunta, lambda _m: None, usuario, key="pregunta")

    def _mostrar_pregunta(self, pregunta: str | None) -> None:
        if pregunta:
            self.lbl_pregunta.setText(t("Pregunta: {pregunta}", pregunta=t(pregunta)))
            self._caja_respuesta_olvido.show()
        else:
            self.lbl_pregunta.setText(t("Esta cuenta no usa pregunta de seguridad: la solicitud se enviará para aprobación."))
            self._caja_respuesta_olvido.hide()
            self.txt_respuesta_olvido.clear()

    def _pedir_clave(self) -> None:
        self._op = OP_RECUPERAR
        self._lanzar(auth.recuperar, self.txt_usuario_olvido.text(), self.txt_clave_olvido.text(),
                     self.txt_confirmacion_olvido.text(), self.txt_respuesta_olvido.text())

    def _cerrar_proceso(self, tipo: str | None = None, titulo: str = "", descripcion: str = "") -> None:
        """Termina el «Procesando…» de la Isla: lo transforma en éxito o error, o lo cierra si no hay nada que decir."""
        id_, self._id_proceso = self._id_proceso, None
        if id_ is None:
            if tipo:
                getattr(isla, tipo)(titulo, descripcion)
        elif tipo:
            # Los errores comparten clave con las validaciones: el más reciente sustituye al anterior.
            isla.actualizar(id_, tipo, titulo, descripcion, **({"clave": "acceso-error"} if tipo == "error" else {}))
        else:
            isla.cerrar(id_)

    def _listo(self, resultado) -> None:
        self._ocupado(False)
        if isinstance(resultado, auth.Sesion):
            self._cerrar_proceso("exito", t(self._op[1]), t("Bienvenido, {nombre}", nombre=resultado.nombre))
            self._guardar_recordado()
            self.limpiar()
            self.entro.emit(resultado)
            return
        if isinstance(resultado, auth.CuentaSinAcceso):
            self._cerrar_proceso()
            self.limpiar()
            self.sin_acceso.emit(resultado)
            return
        self._cerrar_proceso("exito", t(self._op[1]), t(str(resultado)))
        self.limpiar()
        self.lbl_error.setText(t(str(resultado)))

    def _fallo(self, mensaje: str) -> None:
        self._ocupado(False)
        self._error_actual = mensaje
        self.lbl_error.setText(t(mensaje))
        self._cerrar_proceso("error", t(self._op[2]), t(mensaje))
        motion.sacudir(self._tarjeta, 9)


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
