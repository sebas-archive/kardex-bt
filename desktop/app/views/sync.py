"""Pantalla «Sincronización»: el estado del servicio Bluetooth (que corre aparte), pausarlo o reanudarlo,
el código de emparejamiento si lo pide, y las lecturas que quedaron con error.

Procesar y reprocesar lo pueden hacer Administrador e Inventario (matriz: Gestión en ``sync``). Dar de alta
un SKU desconocido es solo del Administrador y se hace desde la lectura en error: crea el producto con
stock 0 en el conteo ``ACTUAL`` y vuelve a reprocesar.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
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
from ..i18n import registrar, t
from ..tema import colores
from .base import QueryRunner, StateBanner
from .isla import isla
from .bluetooth_vivo import BarrasTrafico, BotonReintentar, Diagrama
from .widgets import Indicador, Pasos

registrar({
    "Sincronizar con el celular": "Sync with the phone",
    "Esperando": "Waiting",
    "Conectado": "Connected",
    "Recibiendo": "Receiving",
    "Procesando": "Processing",
    "Listo": "Ready",
    "Pausar": "Pause",
    "Reanudar": "Resume",
    "Aceptar código": "Accept code",
    "Rechazar": "Reject",
    "Reintentar": "Retry",
    "Procesar ahora": "Process now",
    "Reprocesar errores": "Reprocess errors",
    "Dar de alta el SKU": "Create the SKU",
    "Lecturas con error": "Readings with errors",
    "Todos los motivos": "All reasons",
    "Dispositivo": "Device",
    "Seq": "Seq",
    "SKU": "SKU",
    "Motivo": "Reason",
    "Recibida": "Received",
    "Flujo de datos": "Data flow",
    "Tráfico de lecturas": "Reading traffic",
    "Servicio Bluetooth activo · visible como «gestion_inventario»":
        "Bluetooth service active · visible as “gestion_inventario”",
    "desde {fecha}": "since {fecha}",
    "Confirma que el celular muestra este código:": "Confirm that the phone shows this code:",
    "Celular conectado.": "Phone connected.",
    "Recibiendo lecturas…": "Receiving readings…",
    "Procesando las lecturas…": "Processing readings…",
    "Pausando: termina la sincronización en curso…": "Pausing: finishing the current sync…",
    "Servicio Bluetooth en pausa: no recibe teléfonos.": "Bluetooth service paused: it does not receive phones.",
    "El servicio Bluetooth no está corriendo": "The Bluetooth service is not running",
    "En el Bluetooth del celular busca «gestion_inventario» y conéctate desde la app.":
        "In the phone's Bluetooth, look for “gestion_inventario” and connect from the app.",
    "Arráncalo en el PC con «docker compose up -d bluetooth».":
        "Start it on the PC with “docker compose up -d bluetooth”.",
    "Lecturas recibidas: {n}": "Readings received: {n}",
    "Aún no ha llegado ninguna sincronización.": "No synchronization has arrived yet.",
    "Última sincronización: {dispositivo}, {n} lecturas, {fecha}":
        "Last sync: {dispositivo}, {n} readings, {fecha}",
    "Bluetooth no disponible": "Bluetooth unavailable",
    "Error al procesar las lecturas": "Error processing readings",
    "Error durante la sincronización": "Error during synchronization",
    "Alta de SKU": "Create SKU",
    "El SKU no existe en el catálogo. Al darlo de alta se crea con stock 0; luego se reprocesa la lectura.":
        "The SKU is not in the catalog. Creating it sets stock 0; then the reading is reprocessed.",
    "Nombre del producto": "Product name",
    "Categoría": "Category",
    "Crear y reprocesar": "Create and reprocess",
    "Cancelar": "Cancel",
    "El SKU, el nombre y la categoría son obligatorios.": "SKU, name and category are required.",
    "Dar de alta un SKU": "Create a SKU",
    "Pasa la lectura a error de nuevo para reintentar.": "Send the reading back to error to retry.",
    "Selecciona una lectura con error de SKU desconocido.": "Select a reading with an unknown-SKU error.",
    "Aún no se ha procesado nada": "Nothing has been processed yet.",
    "· último procesamiento {fecha} UTC ({origen}) · {pendientes} pendientes, {errores} con error":
        "· last run {fecha} UTC ({origen}) · {pendientes} pending, {errores} with error",
    "Cómo sincronizar": "How to sync",
    "1. Mientras el servicio está activo, el PC se anuncia como gestion_inventario, aunque esta ventana esté cerrada.<br>"
    "2. En el celular abre Sincronizar.<br>"
    "3. Al terminar, Oracle procesa las lecturas y todas las pantallas se actualizan solas.":
        "1. While the service is active, the PC announces itself as gestion_inventario, even if this window is closed.<br>"
        "2. On the phone, open Sync.<br>"
        "3. When it finishes, Oracle processes the readings and every screen refreshes by itself.",
    "Vuelve a sondear el servicio y a intentar la conexión": "Polls the service again and retries the connection",
    "SKU_DESCONOCIDO": "Unknown SKU",
    "CANTIDAD_INVALIDA": "Invalid quantity",
    "DANADOS_INVALIDO": "Invalid damaged quantity",
    "FORMATO_INVALIDO": "Invalid format",
})

PASOS_ES = ["Esperando", "Conectado", "Recibiendo", "Procesando", "Listo"]
PASO_DE = {
    IDLE: None,
    ESPERANDO_EMPAREJAMIENTO: 0,
    CONFIRMAR_CODIGO: 0,
    CONECTADO: 1,
    RECIBIENDO: 2,
    PROCESANDO: 3,
    LISTO: 4,
    ERROR: None,
    PAUSANDO: None,
    PAUSADO: None,
    DETENIDO: None,
}
MODO_DE = {
    IDLE: "reposo",
    ESPERANDO_EMPAREJAMIENTO: "radar",
    CONFIRMAR_CODIGO: "radar",
    CONECTADO: "progreso",
    RECIBIENDO: "progreso",
    PROCESANDO: "progreso",
    LISTO: "listo",
    ERROR: "error",
    PAUSANDO: "progreso",
    PAUSADO: "reposo",
    DETENIDO: "error",
}

ENCABEZADOS_ERRORES = ("Dispositivo", "Seq", "SKU", "Motivo", "Recibida")
TODOS_LOS_MOTIVOS = "Todos los motivos"


def titulo_de_error(ultimo_error: str | None) -> str:
    if ultimo_error and ultimo_error.startswith("BATCH:"):
        return t("Error al procesar las lecturas")
    if ultimo_error and ultimo_error.startswith("SESION:"):
        return t("Error durante la sincronización")
    return t("Bluetooth no disponible")


def _cargar_errores():
    return db.fetch_estado_batch(), db.fetch_errores()


def texto_ultima(ultima) -> str:
    if ultima is None:
        return t("Aún no ha llegado ninguna sincronización.")
    return t("Última sincronización: {dispositivo}, {n} lecturas, {fecha}",
             dispositivo=ultima.dispositivo, n=ultima.recibidos, fecha=f"{ultima.fin:%d/%m %H:%M}")


class AltaSku(QDialog):
    """Datos mínimos para dar de alta el SKU que el operador no encontró en el catálogo."""

    def __init__(self, sku: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("Dar de alta un SKU"))
        self.txt_sku = QLineEdit(sku)
        self.txt_nombre = QLineEdit()
        self.txt_categoria = QLineEdit()
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        forma = QFormLayout()
        forma.addRow(t("SKU"), self.txt_sku)
        forma.addRow(t("Nombre del producto"), self.txt_nombre)
        forma.addRow(t("Categoría"), self.txt_categoria)
        ayuda = QLabel(t("El SKU no existe en el catálogo. Al darlo de alta se crea con stock 0; "
                         "luego se reprocesa la lectura."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        botones.button(QDialogButtonBox.StandardButton.Ok).setText(t("Crear y reprocesar"))
        botones.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancelar"))
        botones.accepted.connect(self._aceptar)
        botones.rejected.connect(self.reject)
        raiz = QVBoxLayout(self)
        raiz.addWidget(ayuda)
        raiz.addLayout(forma)
        raiz.addWidget(self.lbl_error)
        raiz.addWidget(botones)

    def _aceptar(self) -> None:
        if not self.datos()[0] or not self.datos()[1] or not self.datos()[2]:
            self.lbl_error.setText(t("El SKU, el nombre y la categoría son obligatorios."))
            self.lbl_error.show()
            return
        self.accept()

    def datos(self) -> tuple[str, str, str]:
        return self.txt_sku.text().strip().upper(), self.txt_nombre.text().strip(), self.txt_categoria.text().strip()


class SyncView(QWidget):
    datos_cambiados = pyqtSignal()
    detalle = pyqtSignal(str)

    def __init__(self, remoto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._remoto = remoto
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._errores: list = []
        self._visibles: list = []
        self._colores = colores()

        self.lbl_titulo = QLabel(t("Sincronizar con el celular"))
        self.lbl_titulo.setObjectName("seccion")
        self.indicador = Indicador()
        self._pasos_texto = [t(p) for p in PASOS_ES]
        self.pasos = Pasos(self._pasos_texto)
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
        self.lbl_aviso.setStyleSheet(f"color: {self._colores['error']};")
        self.progreso = QProgressBar()
        self.progreso.setRange(0, 0)
        self.progreso.setTextVisible(False)
        self.lbl_recibidos = QLabel("")
        self.lbl_ultima = QLabel("")
        self.lbl_ultima.setObjectName("subtitulo")

        self.btn_pausar = QPushButton(t("Pausar"))
        self.btn_pausar.setMinimumHeight(42)
        self.btn_aceptar = QPushButton(t("Aceptar código"))
        self.btn_rechazar = QPushButton(t("Rechazar"))
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
        self.lbl_titulo.setToolTip(
            "<b>" + t("Cómo sincronizar") + "</b><br>"
            + t("1. Mientras el servicio está activo, el PC se anuncia como gestion_inventario, "
                "aunque esta ventana esté cerrada.<br>"
                "2. En el celular abre Sincronizar.<br>"
                "3. Al terminar, Oracle procesa las lecturas y todas las pantallas se actualizan solas."))
        self.lbl_titulo.setToolTipDuration(12000)
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        en_tarjeta = QVBoxLayout(tarjeta)
        en_tarjeta.setContentsMargins(22, 20, 22, 20)
        en_tarjeta.addLayout(columna)
        arriba = QHBoxLayout()
        arriba.setSpacing(24)
        arriba.addWidget(tarjeta, 3)
        arriba.addLayout(dibujo, 2)

        self.diagrama = Diagrama()
        self.diagrama.elegido.connect(self.detalle.emit)
        self.trafico = BarrasTrafico()
        self.btn_reintentar = BotonReintentar(t("Reintentar"))
        self.btn_reintentar.setToolTip(t("Vuelve a sondear el servicio y a intentar la conexión"))
        self.btn_reintentar.clicked.connect(self._reintentar)
        self.btn_reintentar.hide()
        flujo = QFrame()
        flujo.setObjectName("card")
        en_flujo = QVBoxLayout(flujo)
        en_flujo.setContentsMargins(16, 12, 16, 12)
        rotulo_flujo = QLabel(t("Flujo de datos"))
        rotulo_flujo.setObjectName("seccion")
        en_flujo.addWidget(rotulo_flujo)
        fila_flujo = QHBoxLayout()
        fila_flujo.setSpacing(16)
        fila_flujo.addWidget(self.diagrama, 2)
        columna_trafico = QVBoxLayout()
        etiqueta_trafico = QLabel(t("Tráfico de lecturas"))
        etiqueta_trafico.setObjectName("subtitulo")
        columna_trafico.addWidget(etiqueta_trafico)
        columna_trafico.addWidget(self.trafico, 1)
        columna_trafico.addWidget(self.btn_reintentar)
        fila_flujo.addLayout(columna_trafico, 1)
        en_flujo.addLayout(fila_flujo)

        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_ultimo_run = QLabel("")
        self.lbl_ultimo_run.setObjectName("subtitulo")
        self.combo_motivo = QComboBox()
        self.combo_motivo.addItem(t(TODOS_LOS_MOTIVOS))
        self.combo_motivo.setMinimumWidth(210)
        self.btn_reprocesar = QPushButton(t("Reprocesar errores"))
        self.btn_procesar = QPushButton(t("Procesar ahora"))
        self.btn_alta = QPushButton(t("Dar de alta el SKU"))
        self.btn_alta.setObjectName("primario")
        self.btn_alta.setEnabled(False)
        self.tabla_errores = QTableWidget(0, len(ENCABEZADOS_ERRORES))
        self.tabla_errores.setHorizontalHeaderLabels([t(c) for c in ENCABEZADOS_ERRORES])
        self.tabla_errores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_errores.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_errores.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_errores.verticalHeader().hide()
        self.tabla_errores.horizontalHeader().setStretchLastSection(True)
        self.tabla_errores.setMinimumHeight(140)
        titulo_errores = QLabel(t("Lecturas con error"))
        titulo_errores.setObjectName("seccion")
        barra_errores = QHBoxLayout()
        barra_errores.addWidget(titulo_errores)
        barra_errores.addStretch(1)
        barra_errores.addWidget(self.btn_alta)
        barra_errores.addWidget(self.combo_motivo)
        barra_errores.addWidget(self.btn_reprocesar)
        barra_errores.addWidget(self.btn_procesar)
        tarjeta_errores = QFrame()
        tarjeta_errores.setObjectName("card")
        en_errores = QVBoxLayout(tarjeta_errores)
        en_errores.setContentsMargins(16, 14, 16, 14)
        en_errores.addLayout(barra_errores)
        en_errores.addWidget(self.lbl_ultimo_run)
        en_errores.addWidget(self.banner)
        en_errores.addWidget(self.tabla_errores)

        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(14)
        raiz.addLayout(arriba, 4)
        raiz.addWidget(flujo, 2)
        raiz.addWidget(tarjeta_errores, 2)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(self._contenido)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(desplazable)
        self.combo_motivo.currentIndexChanged.connect(lambda _: self._filtrar())
        self.tabla_errores.itemSelectionChanged.connect(self._seleccion)
        self.btn_procesar.clicked.connect(lambda: self._accion(db.procesar_ahora))
        self.btn_reprocesar.clicked.connect(lambda: self._accion(db.reprocesar_errores))
        self.btn_alta.clicked.connect(self._alta)
        columna.setSizeConstraint(columna.SizeConstraint.SetMinimumSize)

        remoto.status_changed.connect(self._actualizar)
        self._actualizar(remoto.status())

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._actualizar(self._remoto.status())
        self._seleccion()
        if sesion is not None:
            self.refresh()

    def refresh(self) -> None:
        self._remoto.sondear()
        self._actualizar(self._remoto.status())
        if self._sesion is not None:
            self._runner.run(_cargar_errores, self._mostrar_errores, self.banner.show_error, key="errores")

    def errores(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla_errores.item(f, c).text() if self.tabla_errores.item(f, c) else ""
                      for c in range(len(ENCABEZADOS_ERRORES)))
                for f in range(self.tabla_errores.rowCount())]

    # ------------------------------------------------------------- internos
    def _mostrar_errores(self, datos) -> None:
        estado, errores = datos
        self.banner.clear()
        self.lbl_ultimo_run.setText(
            t("Aún no se ha procesado nada") if estado.ultimo_run is None else
            t("· último procesamiento {fecha} UTC ({origen}) · {pendientes} pendientes, {errores} con error",
              fecha=f"{estado.ultimo_run:%Y-%m-%d %H:%M}", origen=estado.ultimo_origen,
              pendientes=estado.pendientes, errores=estado.errores))
        self._errores = list(errores)
        motivos = sorted({e.mensaje_error for e in errores if e.mensaje_error})
        actual = self.combo_motivo.currentText()
        self.combo_motivo.blockSignals(True)
        self.combo_motivo.clear()
        self.combo_motivo.addItem(t(TODOS_LOS_MOTIVOS))
        for motivo in motivos:
            self.combo_motivo.addItem(t(motivo), motivo)
        indice = self.combo_motivo.findText(actual)
        self.combo_motivo.setCurrentIndex(indice if indice >= 0 else 0)
        self.combo_motivo.blockSignals(False)
        self._filtrar()

    def _filtrar(self) -> None:
        motivo = self.combo_motivo.currentData()
        self._visibles = [e for e in self._errores if motivo is None or e.mensaje_error == motivo]
        self.tabla_errores.clearSelection()
        self.tabla_errores.setRowCount(len(self._visibles))
        for fila, e in enumerate(self._visibles):
            celdas = (e.uuid_dispositivo, str(e.seq), e.sku, t(e.mensaje_error or ""),
                      f"{e.fecha_recepcion:%Y-%m-%d %H:%M}" if e.fecha_recepcion else "")
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                self.tabla_errores.setItem(fila, columna, item)
        self.tabla_errores.resizeColumnsToContents()
        self._seleccion()

    def _seleccion(self) -> None:
        error = self._error_seleccionado()
        self.btn_alta.setVisible(self._es_admin())
        self.btn_alta.setEnabled(self._es_admin() and error is not None
                                 and error.mensaje_error == "SKU_DESCONOCIDO")

    def _error_seleccionado(self):
        filas = {i.row() for i in self.tabla_errores.selectionModel().selectedIndexes()} \
            if self.tabla_errores.selectionModel() else set()
        if len(filas) != 1:
            return None
        fila = filas.pop()
        return self._visibles[fila] if 0 <= fila < len(self._visibles) else None

    def _es_admin(self) -> bool:
        return self._sesion is not None and self._sesion.es_admin

    def _alta(self) -> None:
        error = self._error_seleccionado()
        if error is None or not self._es_admin():
            return
        dialogo = AltaSku(error.sku, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted or self._sesion is None:
            return
        sku, nombre, categoria = dialogo.datos()
        self.btn_alta.setEnabled(False)
        self._runner.run(db.crear_producto, self._alta_creada, self._alta_fallo,
                         self._sesion, sku, nombre, categoria)

    def _alta_creada(self, _resultado) -> None:
        self._accion(db.reprocesar_errores)

    def _alta_fallo(self, mensaje: str) -> None:
        self.btn_alta.setEnabled(True)
        self.banner.show_error(mensaje)

    def _reintentar(self) -> None:
        self.btn_reintentar.iniciar()
        self._remoto.sondear()
        self.refresh()
        QTimer.singleShot(900, self.btn_reintentar.detener)

    def _accion(self, operacion) -> None:
        self.btn_procesar.setEnabled(False)
        self.btn_reprocesar.setEnabled(False)
        self._proceso = isla.cargando(t("Procesando lecturas…"))
        self._runner.run(operacion, self._accion_lista, self._accion_fallo)

    def _terminar_proceso(self, tipo: str, titulo: str, descripcion: str = "") -> None:
        id_, self._proceso = getattr(self, "_proceso", None), None
        if id_ is None:
            getattr(isla, tipo)(titulo, descripcion)
        else:
            isla.actualizar(id_, tipo, titulo, descripcion)

    def _accion_lista(self, _resultado) -> None:
        self._terminar_proceso("exito", t("Procesamiento completado"))
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self.refresh()
        self.datos_cambiados.emit()

    def _accion_fallo(self, mensaje: str) -> None:
        self._terminar_proceso("error", t("No se pudo procesar"), mensaje)
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)

    def _puede_gestionar(self) -> bool:
        return self._sesion is not None and self._sesion.puede("sync", "GESTION")

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
        if mensaje:
            isla.error(t("No se pudo controlar el servicio Bluetooth"), mensaje)

    def _actualizar(self, status: dict) -> None:
        estado, recibidos = status["estado"], status["recibidos"]
        error = status["ultimo_error"]
        desde = status.get("desde")
        activo = t("Servicio Bluetooth activo · visible como «gestion_inventario»") + (
            " · " + t("desde {fecha}", fecha=f"{desde:%d/%m %H:%M}") if desde is not None else "")
        textos = {
            IDLE: activo,
            ESPERANDO_EMPAREJAMIENTO: activo,
            CONFIRMAR_CODIGO: t("Confirma que el celular muestra este código:"),
            CONECTADO: t("Celular conectado."),
            RECIBIENDO: t("Recibiendo lecturas…"),
            PROCESANDO: t("Procesando las lecturas…"),
            LISTO: activo,
            ERROR: titulo_de_error(error),
            PAUSANDO: t("Pausando: termina la sincronización en curso…"),
            PAUSADO: t("Servicio Bluetooth en pausa: no recibe teléfonos."),
            DETENIDO: t("El servicio Bluetooth no está corriendo"),
        }
        self.lbl_estado.setText(textos.get(estado, estado))
        ayuda = {
            ESPERANDO_EMPAREJAMIENTO: t("En el Bluetooth del celular busca «gestion_inventario» y conéctate desde la app."),
            DETENIDO: t("Arráncalo en el PC con «docker compose up -d bluetooth»."),
        }.get(estado, "")
        self.lbl_ayuda.setText(ayuda)
        self.lbl_ayuda.setVisible(bool(ayuda))

        gestiona = self._puede_gestionar()
        self.lbl_codigo.setText(status["codigo"] or "")
        self.lbl_codigo.setVisible(estado == CONFIRMAR_CODIGO and bool(status["codigo"]))
        self.btn_aceptar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)
        self.btn_rechazar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)
        self.btn_procesar.setVisible(gestiona)
        self.btn_reprocesar.setVisible(gestiona)
        self.btn_alta.setVisible(self._es_admin())

        self.progreso.setVisible(estado in (CONECTADO, RECIBIENDO, PROCESANDO, PAUSANDO))
        self.lbl_recibidos.setText(t("Lecturas recibidas: {n}", n=recibidos))
        self.lbl_recibidos.setVisible(estado in (RECIBIENDO, PROCESANDO, PAUSANDO) and recibidos > 0)
        self.lbl_ultima.setText(texto_ultima(status.get("ultima")))
        self.lbl_aviso.setText(error or "")  # el error del servicio lo muestra la Isla (estado persistente de Bluetooth)

        paso = PASO_DE.get(estado)
        self.pasos.set_actual(self._pasos_texto[paso] if paso is not None else None)
        self.indicador.set_modo(MODO_DE.get(estado, "reposo"))
        self.diagrama.set_estado(estado)
        self.trafico.agregar(recibidos)
        self.btn_reintentar.setVisible(estado == ERROR and gestiona)

        self.btn_pausar.setText(t("Reanudar") if estado in (PAUSADO, PAUSANDO) else t("Pausar"))
        self.btn_pausar.setVisible(gestiona and estado != DETENIDO)
        self.btn_pausar.setEnabled(True)
