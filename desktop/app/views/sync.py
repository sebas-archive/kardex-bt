"""Vista «Sincronización»: el botón que abre la ventana de recepción y muestra cómo va."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from btsync.controller import (
    CONECTADO,
    CONFIRMAR_CODIGO,
    ERROR,
    ESPERANDO_EMPAREJAMIENTO,
    IDLE,
    LISTO,
    PROCESANDO,
    RECIBIENDO,
)

from ..sync_bridge import SyncBridge
from .base import StateBanner  # noqa: F401  (misma familia visual de avisos)

TEXTO_INICIAR = "Iniciar sincronización"
EN_CURSO = (ESPERANDO_EMPAREJAMIENTO, CONFIRMAR_CODIGO, CONECTADO, RECIBIENDO, PROCESANDO)


def titulo_de_error(ultimo_error: str | None) -> str:
    """Qué falló, según el prefijo con el que el controlador marca el error."""
    if ultimo_error and ultimo_error.startswith("BATCH:"):
        return "Error al procesar las lecturas"
    if ultimo_error and ultimo_error.startswith("SESION:"):
        return "Error durante la sincronización"
    return "Bluetooth no disponible"


def _minutos(segundos: int) -> str:
    return f"{segundos // 60}:{segundos % 60:02d}"


class SyncView(QWidget):
    def __init__(self, bridge: SyncBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge

        self.lbl_titulo = QLabel("Sincronizar con el celular")
        self.lbl_titulo.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.lbl_estado = QLabel("")
        fuente = self.lbl_estado.font()
        fuente.setPointSize(16)
        fuente.setBold(True)
        self.lbl_estado.setFont(fuente)
        self.lbl_estado.setWordWrap(True)
        self.lbl_ayuda = QLabel("")
        self.lbl_ayuda.setObjectName("subtitulo")
        self.lbl_ayuda.setWordWrap(True)
        self.lbl_codigo = QLabel("")
        self.lbl_codigo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        codigo = self.lbl_codigo.font()
        codigo.setPointSize(36)
        codigo.setBold(True)
        codigo.setFamily("DejaVu Sans Mono")
        self.lbl_codigo.setFont(codigo)
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setStyleSheet("color: #b42318;")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)           # total desconocido: barra indeterminada
        self.progreso.setTextVisible(False)
        self.lbl_recibidos = QLabel("")
        self.lbl_restante = QLabel("")
        self.lbl_restante.setObjectName("subtitulo")

        self.btn_iniciar = QPushButton(TEXTO_INICIAR)
        self.btn_aceptar = QPushButton("Aceptar")
        self.btn_rechazar = QPushButton("Rechazar")
        self.btn_iniciar.clicked.connect(self._clic_iniciar)
        self.btn_aceptar.clicked.connect(lambda: bridge.confirm(True))
        self.btn_rechazar.clicked.connect(lambda: bridge.confirm(False))

        botones = QHBoxLayout()
        botones.addWidget(self.btn_aceptar)
        botones.addWidget(self.btn_rechazar)
        columna = QVBoxLayout()
        columna.setSpacing(12)
        for w in (self.lbl_titulo, self.lbl_estado, self.lbl_ayuda, self.lbl_codigo):
            columna.addWidget(w)
        columna.addLayout(botones)
        for w in (self.progreso, self.lbl_recibidos, self.lbl_restante, self.lbl_aviso, self.btn_iniciar):
            columna.addWidget(w)
        columna.addStretch(1)
        raiz = QHBoxLayout(self)
        raiz.setContentsMargins(24, 24, 24, 24)
        raiz.addLayout(columna, 3)
        raiz.addStretch(1)
        columna.setSizeConstraint(columna.SizeConstraint.SetMinimumSize)

        self._activo = False
        bridge.status_changed.connect(self._actualizar)
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(self.refresh)   # la cuenta regresiva baja cada segundo sin avisos del controlador
        self._reloj.start(1000)
        self._actualizar(bridge.status())

    # ------------------------------------------------- contrato de las vistas
    def refresh(self) -> None:
        self._actualizar(self._bridge.status())

    def set_conteo(self, id_conteo: str | None) -> None:
        """La sincronización no depende del conteo elegido."""

    # ------------------------------------------------------------- internos
    def _clic_iniciar(self) -> None:
        if self._activo:
            self._bridge.cancel()
        else:
            self._bridge.start()

    def _actualizar(self, status: dict) -> None:
        estado, recibidos = status["estado"], status["recibidos"]
        error = status["ultimo_error"]
        self._activo = estado in EN_CURSO

        textos = {
            IDLE: "Listo para sincronizar. Pulsa «Iniciar sincronización».",
            ESPERANDO_EMPAREJAMIENTO: "Esperando al celular…",
            CONFIRMAR_CODIGO: "Confirma que el celular muestra este código:",
            CONECTADO: "Celular conectado.",
            RECIBIENDO: "Recibiendo lecturas…",
            PROCESANDO: "Procesando las lecturas…",
            LISTO: f"Sincronización lista: {recibidos} {'lectura recibida' if recibidos == 1 else 'lecturas recibidas'}.",
            ERROR: titulo_de_error(error),
        }
        self.lbl_estado.setText(textos[estado])
        ayuda = ""
        if estado == ESPERANDO_EMPAREJAMIENTO:
            ayuda = "En el Bluetooth del celular busca «gestion_inventario» y conéctate desde la app."
        self.lbl_ayuda.setText(ayuda)
        self.lbl_ayuda.setVisible(bool(ayuda))

        self.lbl_codigo.setText(status["codigo"] or "")
        self.lbl_codigo.setVisible(estado == CONFIRMAR_CODIGO and bool(status["codigo"]))
        self.btn_aceptar.setVisible(estado == CONFIRMAR_CODIGO)
        self.btn_rechazar.setVisible(estado == CONFIRMAR_CODIGO)

        self.progreso.setVisible(estado in (CONECTADO, RECIBIENDO, PROCESANDO))
        mostrar_recibidos = estado in (RECIBIENDO, PROCESANDO, LISTO) or recibidos > 0
        self.lbl_recibidos.setText(f"Lecturas recibidas: {recibidos}")
        self.lbl_recibidos.setVisible(mostrar_recibidos)
        abierta = estado in (ESPERANDO_EMPAREJAMIENTO, CONFIRMAR_CODIGO)
        self.lbl_restante.setText(f"Ventana abierta: {_minutos(status['restante_s'])}")
        self.lbl_restante.setVisible(abierta)
        self.lbl_aviso.setText(error or "")
        self.lbl_aviso.setVisible(bool(error))

        self.btn_iniciar.setText("Cancelar" if self._activo else TEXTO_INICIAR)
        self.btn_iniciar.setEnabled(True)
