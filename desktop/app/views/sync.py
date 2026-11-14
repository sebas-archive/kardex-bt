"""Pantalla «Sincronización»: el estado del servicio Bluetooth (que corre aparte), pausarlo o reanudarlo, el código de
emparejamiento si lo pide, y las lecturas que quedaron con error."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
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

from btsync.servicio import DETENIDO, PAUSADO, PAUSANDO

from .. import auth, db
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
    PAUSANDO: (None, "progreso"),
    PAUSADO: (None, "reposo"),
    DETENIDO: (None, "error"),
}


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


def _lecturas(n: int) -> str:
    return f"{n} {'lectura' if n == 1 else 'lecturas'}"


def texto_ultima(ultima) -> str:
    if ultima is None:
        return "Aún no ha llegado ninguna sincronización."
    return f"Última sincronización: {ultima.dispositivo}, {_lecturas(ultima.recibidos)}, {ultima.fin:%d/%m %H:%M}"


class SyncView(QWidget):
    datos_cambiados = pyqtSignal()  # se procesó o reprocesó algo: las demás pantallas deben refrescar

    def __init__(self, remoto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._remoto = remoto
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
        self.lbl_ultima = QLabel("")
        self.lbl_ultima.setObjectName("subtitulo")

        self.btn_pausar = QPushButton("Pausar")
        self.btn_pausar.setMinimumHeight(42)
        self.btn_aceptar = QPushButton("Aceptar código")
        self.btn_rechazar = QPushButton("Rechazar")
        self.btn_pausar.clicked.connect(self._clic_pausar)
        self.btn_aceptar.clicked.connect(lambda: self._responder(True))
        self.btn_rechazar.clicked.connect(lambda: self._responder(False))
        remoto.fallo.connect(self._fallo_servicio)

        botones = QHBoxLayout()
        botones.addWidget(self.btn_aceptar)
        botones.addWidget(self.btn_rechazar)
        columna = QVBoxLayout()
        columna.setSpacing(12)
        for w in (self.lbl_titulo, self.lbl_estado, self.lbl_ayuda, self.lbl_codigo):
            columna.addWidget(w)
        columna.addLayout(botones)
        for w in (self.progreso, self.lbl_recibidos, self.lbl_ultima, self.lbl_aviso, self.btn_pausar):
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
            "1. Mientras el servicio está activo, el PC se anuncia como <b>gestion_inventario</b>, "
            "aunque esta ventana esté cerrada.<br>"
            "2. En el celular abre <b>Sincronizar</b>.<br>"
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

        remoto.status_changed.connect(self._actualizar)
        self._actualizar(remoto.status())

    # ------------------------------------------------- contrato de las vistas
    def refresh(self) -> None:
        self._remoto.sondear()
        self._actualizar(self._remoto.status())
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
        self._actualizar(self._remoto.status())

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

    def _puede_gestionar(self) -> bool:
        return self._sesion is not None and self._sesion.puede("bluetooth", "GESTION")

    def _clic_pausar(self) -> None:
        if self._sesion is None:
            return
        self.lbl_aviso.hide()
        self.btn_pausar.setEnabled(False)
        if self._remoto.status()["estado"] in (PAUSADO, PAUSANDO):
            self._remoto.reanudar(self._sesion)
        else:
            self._remoto.pausar(self._sesion)

    def _responder(self, aceptar: bool) -> None:
        if self._sesion is not None:
            self._remoto.responder(self._sesion, aceptar)

    def _fallo_servicio(self, mensaje: str) -> None:
        self.btn_pausar.setEnabled(True)
        self.lbl_aviso.setText(mensaje)
        self.lbl_aviso.setVisible(bool(mensaje))

    def _actualizar(self, status: dict) -> None:
        estado, recibidos = status["estado"], status["recibidos"]
        error = status["ultimo_error"]
        desde = status.get("desde")
        activo = "Servicio Bluetooth activo · visible como «gestion_inventario»" + (
            f" · desde {desde:%d/%m %H:%M}" if desde is not None else "")
        textos = {
            IDLE: activo,
            ESPERANDO_EMPAREJAMIENTO: activo,
            CONFIRMAR_CODIGO: "Confirma que el celular muestra este código:",
            CONECTADO: "Celular conectado.",
            RECIBIENDO: "Recibiendo lecturas…",
            PROCESANDO: "Procesando las lecturas…",
            LISTO: activo,
            ERROR: titulo_de_error(error),
            PAUSANDO: "Pausando: termina la sincronización en curso…",
            PAUSADO: "Servicio Bluetooth en pausa: no recibe teléfonos.",
            DETENIDO: "El servicio Bluetooth no está corriendo",
        }
        self.lbl_estado.setText(textos.get(estado, estado))
        ayuda = {
            ESPERANDO_EMPAREJAMIENTO: "En el Bluetooth del celular busca «gestion_inventario» y conéctate desde la app.",
            DETENIDO: "Arráncalo en el PC con «docker compose up -d bluetooth».",
        }.get(estado, "")
        self.lbl_ayuda.setText(ayuda)
        self.lbl_ayuda.setVisible(bool(ayuda))

        gestiona = self._puede_gestionar()
        self.lbl_codigo.setText(status["codigo"] or "")
        self.lbl_codigo.setVisible(estado == CONFIRMAR_CODIGO and bool(status["codigo"]))
        self.btn_aceptar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)
        self.btn_rechazar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)

        self.progreso.setVisible(estado in (CONECTADO, RECIBIENDO, PROCESANDO, PAUSANDO))
        self.lbl_recibidos.setText(f"Lecturas recibidas: {recibidos}")
        self.lbl_recibidos.setVisible(estado in (RECIBIENDO, PROCESANDO, PAUSANDO) and recibidos > 0)
        self.lbl_ultima.setText(texto_ultima(status.get("ultima")))
        self.lbl_aviso.setText(error or "")
        self.lbl_aviso.setVisible(bool(error))

        paso, dibujo = VISUAL.get(estado, (None, "reposo"))
        self.pasos.set_actual(paso)
        self.indicador.set_modo(dibujo)

        self.btn_pausar.setText("Reanudar" if estado in (PAUSADO, PAUSANDO) else "Pausar")
        self.btn_pausar.setVisible(gestiona and estado != DETENIDO)
        self.btn_pausar.setEnabled(True)
