"""Pantalla de una cuenta que no puede entrar: PENDIENTE o RECHAZADA.

El Administrador nunca pasa por aquí: su cuenta no se puede suspender ni rechazar. Una cuenta pendiente espera al
Administrador; una rechazada muestra el motivo. El botón vuelve al acceso.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import auth
from ..i18n import t

MENSAJE = {
    auth.PENDIENTE: "Tu cuenta espera aprobación del administrador",
    auth.RECHAZADO: "El administrador rechazó tu solicitud de cuenta",
    auth.SUSPENDIDO: "El administrador suspendió tu cuenta",
}
COLOR = {auth.PENDIENTE: "#FBBF24", auth.RECHAZADO: "#F87171", auth.SUSPENDIDO: "#F87171"}
NOMBRE_ESTADO = {auth.PENDIENTE: "Pendiente", auth.RECHAZADO: "Rechazada", auth.SUSPENDIDO: "Suspendida"}


class EstadoCuentaView(QWidget):
    volver = pyqtSignal()   # vuelve al formulario de inicio de sesión

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.lbl_logo = QLabel(t("Kardex — Gestión de inventario"))
        self.lbl_logo.setObjectName("tituloAcceso")
        self.lbl_nombre = QLabel("")
        self.lbl_nombre.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.lbl_usuario = QLabel("")
        self.lbl_usuario.setObjectName("ayuda")
        self.lbl_estado = QLabel("")
        self.lbl_estado.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mensaje = QLabel("")
        self.lbl_mensaje.setWordWrap(True)
        self.lbl_motivo = QLabel("")
        self.lbl_motivo.setWordWrap(True)
        self.lbl_motivo.setTextFormat(Qt.TextFormat.PlainText)   # lo escribió una persona: nunca se interpreta
        self.lbl_fecha = QLabel("")
        self.lbl_fecha.setObjectName("ayuda")
        self.btn_volver = QPushButton(t("Volver al acceso"))
        self.btn_volver.setObjectName("primario")
        self.btn_volver.setMinimumHeight(40)

        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        tarjeta.setFixedWidth(440)
        en_tarjeta = QVBoxLayout(tarjeta)
        en_tarjeta.setContentsMargins(28, 28, 28, 24)
        en_tarjeta.setSpacing(10)
        for widget in (self.lbl_logo, self.lbl_nombre, self.lbl_usuario):
            en_tarjeta.addWidget(widget)
        en_tarjeta.addSpacing(6)
        en_tarjeta.addWidget(self.lbl_estado, 0, Qt.AlignmentFlag.AlignLeft)
        for widget in (self.lbl_mensaje, self.lbl_motivo, self.lbl_fecha):
            en_tarjeta.addWidget(widget)
        en_tarjeta.addSpacing(8)
        en_tarjeta.addWidget(self.btn_volver)

        raiz = QVBoxLayout(self)
        raiz.addStretch(1)
        raiz.addWidget(tarjeta, 0, Qt.AlignmentFlag.AlignHCenter)
        raiz.addStretch(1)

        self.btn_volver.clicked.connect(self.volver)

    def mostrar(self, cuenta: auth.CuentaSinAcceso) -> None:
        self.lbl_nombre.setText(cuenta.nombre)
        self.lbl_usuario.setText(f"@{cuenta.usuario}")
        self.lbl_estado.setText(t(NOMBRE_ESTADO.get(cuenta.estado, cuenta.estado)))
        color = COLOR.get(cuenta.estado, "#9CA3AF")
        self.lbl_estado.setStyleSheet(f"color: {color}; border: 1px solid {color}; border-radius: 10px; "
                                      "padding: 2px 10px; font-weight: 600;")
        self.lbl_mensaje.setText(t(MENSAJE.get(cuenta.estado, "")))
        pendiente = cuenta.estado == auth.PENDIENTE
        self.lbl_motivo.setText(t("Motivo: {motivo}", motivo=cuenta.motivo) if cuenta.motivo else "")
        self.lbl_motivo.setVisible(not pendiente and bool(cuenta.motivo))
        self.lbl_fecha.setText(t("Registrada el {fecha}", fecha=f"{cuenta.registrado:%d/%m/%Y}") if cuenta.registrado else "")
        self.btn_volver.setText(t("Volver al acceso"))
