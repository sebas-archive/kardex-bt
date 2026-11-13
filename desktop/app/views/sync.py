"""Pantalla «Sincronización»: el botón que abre la ventana de recepción, cómo va, y las lecturas que quedaron con error."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
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

from .. import auth, db
from ..sync_bridge import SyncBridge
from .base import QueryRunner, StateBanner
from .widgets import Indicador, Pasos

PASOS = ["Esperando", "Conectado", "Recibiendo", "Procesando", "Listo"]
# Estado del controlador → (paso marcado, dibujo del indicador)
VISUAL = {
    IDLE: (None, "reposo"),
    ESPERANDO_EMPAREJAMIENTO: ("Esperando", "radar"),
    CONFIRMAR_CODIGO: ("Esperando", "radar"),
    CONECTADO: ("Conectado", "progreso"),
    RECIBIENDO: ("Recibiendo", "progreso"),
    PROCESANDO: ("Procesando", "progreso"),
    LISTO: ("Listo", "listo"),
    ERROR: (None, "error"),
}

TEXTO_INICIAR = "Iniciar sincronización"
EN_CURSO = (ESPERANDO_EMPAREJAMIENTO, CONFIRMAR_CODIGO, CONECTADO, RECIBIENDO, PROCESANDO)


def titulo_de_error(ultimo_error: str | None) -> str:
    """Qué falló, según el prefijo con el que el controlador marca el error."""
    if ultimo_error and ultimo_error.startswith("BATCH:"):
        return "Error al procesar las lecturas"
    if ultimo_error and ultimo_error.startswith("SESION:"):
        return "Error durante la sincronización"
    return "Bluetooth no disponible"


ENCABEZADOS_ERRORES = ("Dispositivo", "Seq", "Motivo", "Línea recibida")
TODOS_LOS_MOTIVOS = "Todos los motivos"


def _cargar_errores():
    """Corre en un hilo de trabajo: (estado del batch, lecturas que el batch dejó con error)."""
    return db.fetch_estado_batch(), db.fetch_errores()


def _minutos(segundos: int) -> str:
    return f"{segundos // 60}:{segundos % 60:02d}"


class SyncView(QWidget):
    datos_cambiados = pyqtSignal()  # se procesó o reprocesó algo: las demás pantallas deben refrescar

    def __init__(self, bridge: SyncBridge, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._errores: list = []

        self.lbl_titulo = QLabel("Sincronizar con el celular")
        self.lbl_titulo.setObjectName("seccion")
        self.indicador = Indicador()
        self.pasos = Pasos(PASOS)
        self.lbl_estado = QLabel("")
        fuente = self.lbl_estado.font()
        fuente.setPointSize(16)
        fuente.setBold(True)
        self.lbl_estado.setFont(fuente)
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setObjectName("estadoSync")
        self.lbl_ayuda = QLabel("")
        self.lbl_ayuda.setObjectName("ayuda")
        self.lbl_ayuda.setWordWrap(True)
        self.lbl_codigo = QLabel("")
        self.lbl_codigo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        codigo = self.lbl_codigo.font()
        codigo.setPointSize(36)
        codigo.setBold(True)
        codigo.setFamily("DejaVu Sans Mono")
        self.lbl_codigo.setFont(codigo)
        self.lbl_codigo.setObjectName("codigoSync")
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setStyleSheet("color: #F87171;")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)           # total desconocido: barra indeterminada
        self.progreso.setTextVisible(False)
        self.lbl_recibidos = QLabel("")
        self.lbl_restante = QLabel("")
        self.lbl_restante.setObjectName("subtitulo")

        self.btn_iniciar = QPushButton(TEXTO_INICIAR)
        self.btn_iniciar.setObjectName("primario")
        self.btn_iniciar.setMinimumHeight(42)
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
        dibujo = QVBoxLayout()
        dibujo.addStretch(1)
        dibujo.addWidget(self.indicador, 0, Qt.AlignmentFlag.AlignHCenter)
        dibujo.addSpacing(12)
        dibujo.addWidget(self.pasos)
        dibujo.addStretch(1)
        pasos_ayuda = QLabel(
            "<b>Cómo sincronizar</b><br>"
            "1. Pulsa «Iniciar sincronización»: el PC se anuncia como <b>gestion_inventario</b> durante 2 minutos.<br>"
            "2. En el celular abre <b>Sincronizar</b>. No hay claves ni códigos.<br>"
            "3. Al terminar, Oracle procesa las lecturas y todas las pantallas se actualizan solas.")
        pasos_ayuda.setObjectName("ayuda")
        pasos_ayuda.setWordWrap(True)
        columna.insertWidget(columna.count() - 1, pasos_ayuda)
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        en_tarjeta = QVBoxLayout(tarjeta)
        en_tarjeta.setContentsMargins(22, 20, 22, 20)
        en_tarjeta.addLayout(columna)
        arriba = QHBoxLayout()
        arriba.setSpacing(24)
        arriba.addWidget(tarjeta, 3)
        arriba.addLayout(dibujo, 2)

        # ---- lecturas con error (lo que antes estaba en «Monitoreo»)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_ultimo_run = QLabel("")
        self.lbl_ultimo_run.setObjectName("subtitulo")
        self.combo_motivo = QComboBox()
        self.combo_motivo.addItem(TODOS_LOS_MOTIVOS)
        self.combo_motivo.setMinimumWidth(210)
        self.btn_reprocesar = QPushButton("Reprocesar errores")
        self.btn_procesar = QPushButton("Procesar ahora")
        self.tabla_errores = QTableWidget(0, len(ENCABEZADOS_ERRORES))
        self.tabla_errores.setHorizontalHeaderLabels(list(ENCABEZADOS_ERRORES))
        self.tabla_errores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_errores.verticalHeader().hide()
        self.tabla_errores.horizontalHeader().setStretchLastSection(True)
        self.tabla_errores.setMinimumHeight(120)
        titulo_errores = QLabel("Lecturas con error")
        titulo_errores.setObjectName("seccion")
        barra_errores = QHBoxLayout()
        barra_errores.addWidget(titulo_errores)
        barra_errores.addWidget(self.lbl_ultimo_run)
        barra_errores.addStretch(1)
        barra_errores.addWidget(self.combo_motivo)
        barra_errores.addWidget(self.btn_reprocesar)
        barra_errores.addWidget(self.btn_procesar)
        tarjeta_errores = QFrame()
        tarjeta_errores.setObjectName("card")
        en_errores = QVBoxLayout(tarjeta_errores)
        en_errores.setContentsMargins(16, 14, 16, 14)
        en_errores.addLayout(barra_errores)
        en_errores.addWidget(self.banner)
        en_errores.addWidget(self.tabla_errores)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(14)
        raiz.addLayout(arriba, 3)
        raiz.addWidget(tarjeta_errores, 2)
        self.combo_motivo.currentIndexChanged.connect(lambda _: self._filtrar())
        self.btn_procesar.clicked.connect(lambda: self._accion(db.procesar_ahora))
        self.btn_reprocesar.clicked.connect(lambda: self._accion(db.reprocesar_errores, None))
        columna.setSizeConstraint(columna.SizeConstraint.SetMinimumSize)

        self._activo = False
        bridge.status_changed.connect(self._actualizar)
        self._reloj = QTimer(self)
        self._reloj.timeout.connect(lambda: self._actualizar(self._bridge.status()))  # la cuenta regresiva baja cada segundo
        self._reloj.start(1000)
        self._actualizar(bridge.status())

    # ------------------------------------------------- contrato de las vistas
    def refresh(self) -> None:
        self._actualizar(self._bridge.status())
        self._runner.run(_cargar_errores, self._mostrar_errores, self.banner.show_error, key="errores")

    def set_conteo(self, id_conteo: str | None) -> None:
        """La sincronización no depende del conteo elegido."""
        self.refresh()

    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        """Procesar y reprocesar es cosa del administrador."""
        self._sesion = sesion
        es_admin = sesion is not None and sesion.es_admin
        self.btn_procesar.setVisible(es_admin)
        self.btn_reprocesar.setVisible(es_admin)

    def errores(self) -> list[tuple[str, str, str, str]]:
        """Las filas que muestra la tabla de errores (con el filtro puesto)."""
        return [tuple(self.tabla_errores.item(f, c).text() for c in range(len(ENCABEZADOS_ERRORES)))
                for f in range(self.tabla_errores.rowCount())]

    # ------------------------------------------------------------- internos
    def _mostrar_errores(self, datos) -> None:
        estado, errores = datos
        self.banner.clear()
        self.lbl_ultimo_run.setText(
            "· aún no se ha procesado nada" if estado.ultimo_run is None else
            f"· último procesamiento {estado.ultimo_run:%Y-%m-%d %H:%M} UTC ({estado.ultimo_origen}) · "
            f"{estado.pendientes} pendientes, {estado.errores} con error")
        self._errores = list(errores)
        motivos = sorted({e.mensaje_error for e in errores if e.mensaje_error})
        actual = self.combo_motivo.currentText()
        self.combo_motivo.blockSignals(True)
        self.combo_motivo.clear()
        self.combo_motivo.addItem(TODOS_LOS_MOTIVOS)
        self.combo_motivo.addItems(motivos)
        self.combo_motivo.setCurrentIndex(max(self.combo_motivo.findText(actual), 0))
        self.combo_motivo.blockSignals(False)
        self._filtrar()

    def _filtrar(self) -> None:
        motivo = self.combo_motivo.currentText()
        visibles = [e for e in self._errores if motivo == TODOS_LOS_MOTIVOS or e.mensaje_error == motivo]
        self.tabla_errores.setRowCount(len(visibles))
        for fila, e in enumerate(visibles):
            for columna, texto in enumerate((e.uuid_dispositivo, str(e.seq), e.mensaje_error or "", e.datos_raw)):
                self.tabla_errores.setItem(fila, columna, QTableWidgetItem(texto))
        self.tabla_errores.resizeColumnsToContents()

    def _accion(self, operacion, *args) -> None:
        """Procesar o reprocesar en un hilo de trabajo; mientras corre no se puede lanzar otra acción."""
        self.btn_procesar.setEnabled(False)
        self.btn_reprocesar.setEnabled(False)
        self._runner.run(operacion, self._accion_lista, self._accion_fallo, *args)

    def _accion_lista(self, _resultado) -> None:
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self.refresh()
        self.datos_cambiados.emit()

    def _accion_fallo(self, mensaje: str) -> None:
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self.banner.show_error(mensaje)

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

        paso, dibujo = VISUAL[estado]
        self.pasos.set_actual(paso)
        self.indicador.set_modo(dibujo)

        self.btn_iniciar.setText("Cancelar" if self._activo else TEXTO_INICIAR)
        self.btn_iniciar.setEnabled(True)
