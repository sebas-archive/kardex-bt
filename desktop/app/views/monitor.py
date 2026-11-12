"""Vista «Monitoreo»: estado del servicio Bluetooth, del batch y errores recientes."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

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

from .. import db
from ..sync_bridge import SyncBridge
from .base import QueryRunner, StateBanner
from .sync import titulo_de_error

TARJETAS = (("pendientes", "Pendientes"), ("procesando", "Procesando"), ("procesados", "Procesados"),
            ("errores", "Con error"))
ENCABEZADOS = ("ID", "Dispositivo", "Seq", "Motivo", "Línea recibida")


def texto_servicio(status: dict) -> str:
    estado = status["estado"]
    detalle = {
        IDLE: "apagado (sin sincronización abierta)",
        ESPERANDO_EMPAREJAMIENTO: "escuchando como «gestion_inventario»",
        CONFIRMAR_CODIGO: "escuchando, esperando que confirmes el código",
        CONECTADO: "celular conectado",
        RECIBIENDO: "recibiendo lecturas",
        PROCESANDO: "procesando las lecturas",
        LISTO: "última sincronización lista",
        ERROR: f"{titulo_de_error(status['ultimo_error']).lower()} ({status['ultimo_error']})",
    }[estado]
    return f"Servicio Bluetooth: {detalle}"


def _cargar():
    """Corre en un hilo de trabajo: (estado del batch, errores recientes)."""
    return db.fetch_estado_batch(), db.fetch_errores()


class MonitorView(QWidget):
    datos_cambiados = pyqtSignal()  # el batch o un reproceso modificó datos: las demás vistas deben refrescar

    def __init__(self, bridge: SyncBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._cargado = False
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)

        self.lbl_servicio = QLabel("")
        self.lbl_servicio.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.lbl_servicio.setWordWrap(True)
        self.lbl_ultimo_run = QLabel("")
        self.lbl_ultimo_run.setObjectName("subtitulo")

        self.cards: dict[str, QFrame] = {}
        self._valores: dict[str, QLabel] = {}
        fila = QHBoxLayout()
        for clave, titulo in TARJETAS:
            card = QFrame()
            card.setObjectName("card")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(14, 12, 14, 12)
            etiqueta = QLabel(titulo)
            etiqueta.setObjectName("cardTitulo")
            valor = QLabel("—")
            valor.setObjectName("cardValor")
            lay.addWidget(etiqueta)
            lay.addWidget(valor)
            fila.addWidget(card, 1)
            self.cards[clave], self._valores[clave] = card, valor

        self.btn_procesar = QPushButton("Procesar ahora")
        self.btn_reprocesar = QPushButton("Reprocesar errores")
        self.btn_procesar.clicked.connect(lambda: self._accion(db.procesar_ahora))
        self.btn_reprocesar.clicked.connect(lambda: self._accion(db.reprocesar_errores, None))
        acciones = QHBoxLayout()
        acciones.addWidget(QLabel("Errores recientes"))
        acciones.addStretch(1)
        acciones.addWidget(self.btn_reprocesar)
        acciones.addWidget(self.btn_procesar)

        self.tabla_errores = QTableWidget(0, len(ENCABEZADOS))
        self.tabla_errores.setHorizontalHeaderLabels(list(ENCABEZADOS))
        self.tabla_errores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_errores.verticalHeader().hide()
        self.tabla_errores.horizontalHeader().setStretchLastSection(True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(16, 16, 16, 16)
        raiz.setSpacing(12)
        raiz.addWidget(self.lbl_servicio)
        raiz.addWidget(self.banner)
        raiz.addLayout(fila)
        raiz.addWidget(self.lbl_ultimo_run)
        raiz.addLayout(acciones)
        raiz.addWidget(self.tabla_errores, 1)

        bridge.status_changed.connect(self._servicio)
        self._servicio(bridge.status())

    # ------------------------------------------------- contrato de las vistas
    def card_text(self, clave: str) -> str:
        return self._valores[clave].text()

    def set_conteo(self, id_conteo: str | None) -> None:
        """El monitoreo es de todo el tránsito, no de un conteo."""
        self.refresh()

    def refresh(self) -> None:
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, key="monitor")

    # ------------------------------------------------------------- internos
    def _servicio(self, status: dict) -> None:
        self.lbl_servicio.setText(texto_servicio(status))

    def _mostrar(self, datos) -> None:
        estado, errores = datos
        self._cargado = True
        self.banner.clear()
        for clave, valor in (("pendientes", estado.pendientes), ("procesando", estado.procesando),
                             ("procesados", estado.procesados), ("errores", estado.errores)):
            self._valores[clave].setText(str(valor))
        if estado.ultimo_run is None:
            self.lbl_ultimo_run.setText("Último batch: nunca")
        else:
            self.lbl_ultimo_run.setText(
                f"Último batch: {estado.ultimo_run:%Y-%m-%d %H:%M:%S} UTC ({estado.ultimo_origen})")
        self.tabla_errores.setRowCount(len(errores))
        for r, e in enumerate(errores):
            for c, texto in enumerate((str(e.id_transito), e.uuid_dispositivo, str(e.seq),
                                       e.mensaje_error or "", e.datos_raw)):
                self.tabla_errores.setItem(r, c, QTableWidgetItem(texto))
        self.tabla_errores.resizeColumnsToContents()

    def _accion(self, fn, *args) -> None:
        """Procesar o reprocesar en un hilo de trabajo; mientras corre no se puede lanzar otra acción."""
        self.btn_procesar.setEnabled(False)
        self.btn_reprocesar.setEnabled(False)
        self._runner.run(fn, self._accion_lista, self._accion_fallo, *args)

    def _habilitar(self) -> None:
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)

    def _accion_lista(self, _resultado) -> None:
        self._habilitar()
        self.refresh()
        self.datos_cambiados.emit()

    def _accion_fallo(self, mensaje: str) -> None:
        self._habilitar()
        self.banner.show_error(mensaje)
