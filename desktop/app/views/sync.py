"""Pantalla «Sincronización»: centro de control del servicio Bluetooth (que corre aparte).

Muestra el estado real del servicio, lo pausa o reanuda, el flujo Android → Bluetooth → PC servidor → Oracle, las
etapas de la sincronización, la actividad (gráficas con datos de Oracle) y las lecturas que quedaron con error.

Todo lo que se ve sale de datos reales: ``ServicioRemoto.status()`` (estado, código, recibidos, última sesión),
``v_estado_batch`` y ``captura_transito``/``registros_procesados`` (contadores y actividad). No hay temporizadores
que avancen etapas ni tráfico simulado. Las consultas corren en ``QueryRunner`` (hilos) y entregan por señal.

Procesar y reprocesar lo pueden hacer Administrador e Inventario (matriz: Gestión en ``sync``). Un SKU desconocido
**ya no termina en error**: queda en ``NUEVO_SKU`` y se decide en el aviso flotante «Nuevo SKU» de la ventana
(«Crear y procesar» o «No crear»); esta pantalla solo informa cuántos esperan decisión.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
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

from .. import auth, db, sync_datos
from ..i18n import registrar, t
from ..tema import colores
from . import motion, sync_ui, widgets
from .base import QueryRunner, StateBanner
from .isla import isla
from .sync_ui import (
    BotonActualizar,
    EstadoVacio,
    Etapas,
    FlujoDatos,
    GraficaActividad,
    IconoBluetooth,
    Odometro,
    Pildora,
    TablaErrores,
)

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
    "Cancelar": "Cancel",
    "Aún no se ha procesado nada": "Nothing has been processed yet.",
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



registrar({
    "Sincronización": "Synchronization",
    "Estado y actividad de transferencia de datos": "Status and data transfer activity",
    "Actualizar": "Refresh",
    "Última actualización {hora}": "Last updated {hora}",
    "Oracle conectado": "Oracle connected",
    "Oracle sin conexión": "Oracle offline",
    "Comprobando Oracle…": "Checking Oracle…",
    "Bluetooth activo": "Bluetooth active",
    "Bluetooth en pausa": "Bluetooth paused",
    "Bluetooth pausando…": "Bluetooth pausing…",
    "Bluetooth con error": "Bluetooth error",
    "Bluetooth detenido": "Bluetooth stopped",
    "Esperando dispositivo": "Waiting for device",
    "Dispositivo conectado": "Device connected",
    "Recibiendo lecturas": "Receiving readings",
    "Procesando información": "Processing information",
    "Sincronización completada": "Synchronization completed",
    "Buscando dispositivos...": "Looking for devices...",
    "El PC se anuncia como «gestion_inventario». Abre Sincronizar en el celular.":
        "The PC announces itself as “gestion_inventario”. Open Sync on the phone.",
    "Confirma el código": "Confirm the code",
    "El celular está conectado y listo para enviar el conteo.": "The phone is connected and ready to send the count.",
    "Las lecturas del celular están llegando al PC.": "Readings from the phone are arriving at the PC.",
    "Procesando datos": "Processing data",
    "Oracle está validando y guardando las lecturas.": "Oracle is validating and saving the readings.",
    "Todas las lecturas recibidas se procesaron.": "All received readings were processed.",
    "Pausando servicio": "Pausing service",
    "El servicio Bluetooth está pausado": "The Bluetooth service is paused",
    "No se reciben lecturas de los celulares hasta que reanudes el servicio.":
        "No readings are received from phones until you resume the service.",
    "Pausar servicio": "Pause service",
    "Reanudar servicio": "Resume service",
    "Último dispositivo: {nombre}": "Last device: {nombre}",
    "Aún no se ha conectado ningún dispositivo": "No device has connected yet",
    "Última sincronización: {fecha} · {n} lecturas": "Last sync: {fecha} · {n} readings",
    "Lecturas recibidas": "Readings received",
    "Lecturas procesadas": "Readings processed",
    "Lecturas pendientes": "Readings pending",
    "Lecturas con error": "Readings with errors",
    "hoy": "today",
    "por procesar": "to process",
    "sin resolver": "unresolved",
    "Recibiendo lecturas · {n}": "Receiving readings · {n}",
    "En espera": "Idle",
    "Conectado": "Connected",
    "Sin conexión": "Offline",
    "Sin dispositivo": "No device",
    "Confirmando código": "Confirming code",
    "Canal activo": "Channel active",
    "Transfiriendo": "Transferring",
    "En pausa": "Paused",
    "Pausando": "Pausing",
    "Detenido": "Stopped",
    "Con error": "Error",
    "Esperando": "Waiting",
    "Recibiendo": "Receiving",
    "Procesando": "Processing",
    "Error al procesar": "Processing error",
    "Comprobando": "Checking",
    "Disponible": "Available",
    "{n} pendientes": "{n} pending",
    "{n} recibidas": "{n} received",
    "{n} procesadas": "{n} processed",
    "Flujo de datos": "Data flow",
    "Android → Bluetooth → PC servidor → Oracle": "Android → Bluetooth → PC server → Oracle",
    "PC servidor": "PC server",
    "Actividad": "Activity",
    "15 min": "15 min",
    "1 hora": "1 hour",
    "24 horas": "24 hours",
    "7 días": "7 days",
    "Últimos 15 minutos": "Last 15 minutes",
    "Última hora": "Last hour",
    "Últimas 24 horas": "Last 24 hours",
    "Últimos 7 días": "Last 7 days",
    "Recibidas": "Received",
    "Procesadas": "Processed",
    "Errores registrados": "Recorded errors",
    "Actividad por minuto": "Activity per minute",
    "Última sincronización": "Last synchronization",
    "{v} /min": "{v} /min",
    "Sin actividad en este periodo": "No activity in this period",
    "Cuando lleguen lecturas, aparecerán aquí.": "When readings arrive, they will show up here.",
    "Cargando…": "Loading…",
    "{n} errores pendientes": "{n} pending errors",
    "1 error pendiente": "1 pending error",
    "Sin errores pendientes": "No pending errors",
    "Dispositivo": "Device",
    "Secuencia": "Sequence",
    "Fecha de recepción": "Received on",
    "Estado": "Status",
    "Acción": "Action",
    "Todo está en orden": "Everything is in order",
    "No hay lecturas pendientes de revisión": "There are no readings waiting for review",
    "Ninguna lectura con este motivo": "No readings with this reason",
    "Cambia el filtro para ver los demás errores.": "Change the filter to see the other errors.",
    "Reprocesando errores…": "Reprocessing errors…",
    "Errores reprocesados": "Errors reprocessed",
    "{n} lecturas resueltas": "{n} readings resolved",
    "{n} reprocesados · {m} siguen con error": "{n} reprocessed · {m} still in error",
    "Sin cambios": "No changes",
    "Las {n} lecturas siguen con error": "The {n} readings are still in error",
    "No había errores que reprocesar": "There were no errors to reprocess",
    "Bluetooth reanudado": "Bluetooth resumed",
    "Oracle desconectado": "Oracle disconnected",
    "Oracle conectado de nuevo": "Oracle reconnected",
    "No se pudo consultar Oracle": "Could not query Oracle",
    "Actualizado": "Updated",
})

PASOS_ES = ["Esperando dispositivo", "Dispositivo conectado", "Recibiendo lecturas", "Procesando información",
            "Sincronización completada"]
PASO_DE = {
    IDLE: 0,
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

ENCABEZADOS_ERRORES = ("Dispositivo", "Secuencia", "SKU", "Motivo", "Fecha de recepción", "Estado")
TODOS_LOS_MOTIVOS = "Todos los motivos"
RANGOS_ES = (("15m", "15 min", "Últimos 15 minutos"), ("1h", "1 hora", "Última hora"),
             ("24h", "24 horas", "Últimas 24 horas"), ("7d", "7 días", "Últimos 7 días"))


MOTIVOS_ES = {"SKU_DESCONOCIDO": "SKU desconocido", "CANTIDAD_INVALIDA": "Cantidad inválida",
              "DANADOS_INVALIDO": "Cantidad de dañados inválida", "FORMATO_INVALIDO": "Formato inválido"}


def motivo_legible(motivo: str | None) -> str:
    """El motivo del batch en lenguaje de persona (el código crudo solo se ve si no hay traducción)."""
    if not motivo:
        return ""
    texto = t(motivo)
    return MOTIVOS_ES.get(motivo, motivo) if texto == motivo else texto


def titulo_de_error(ultimo_error: str | None) -> str:
    if ultimo_error and ultimo_error.startswith("BATCH:"):
        return t("Error al procesar las lecturas")
    if ultimo_error and ultimo_error.startswith("SESION:"):
        return t("Error durante la sincronización")
    return t("Bluetooth no disponible")


def texto_ultima(ultima) -> str:
    if ultima is None:
        return t("Aún no ha llegado ninguna sincronización.")
    return t("Última sincronización: {dispositivo}, {n} lecturas, {fecha}",
             dispositivo=ultima.dispositivo, n=ultima.recibidos, fecha=f"{ultima.fin:%d/%m %H:%M}")


# ------------------------------------------------------------------ modelos puros (estado real → lo que se ve)
def modelo_etapas(estado: str, paso_previo: int | None = None) -> tuple[int | None, int, int | None]:
    """(etapa en curso, etapas completadas, etapa con error). Solo depende del estado real del servicio."""
    if estado == LISTO:
        return None, len(PASOS_ES), None
    if estado == ERROR:
        e = paso_previo if paso_previo is not None else 0
        return None, e, e
    paso = PASO_DE.get(estado)
    if paso is None:        # en pausa, pausando o detenido: nada avanza
        return None, 0, None
    return paso, paso, None


def estado_bluetooth(estado: str, error: str | None = None) -> tuple[str, str]:
    """(tono, texto) de la píldora de Bluetooth. Un error del batch (Oracle) no es un fallo del canal Bluetooth."""
    if estado == ERROR and (error or "").startswith("BATCH:"):
        return "ok", t("Bluetooth activo")
    if estado == DETENIDO:
        return "error", t("Bluetooth detenido")
    if estado == PAUSADO:
        return "pausa", t("Bluetooth en pausa")
    if estado == PAUSANDO:
        return "aviso", t("Bluetooth pausando…")
    if estado == ERROR:
        return "error", t("Bluetooth con error")
    return "ok", t("Bluetooth activo")


def modo_icono(estado: str) -> str:
    return {IDLE: "activo", CONECTADO: "activo", RECIBIENDO: "activo", PROCESANDO: "activo", LISTO: "activo",
            ESPERANDO_EMPAREJAMIENTO: "buscando", CONFIRMAR_CODIGO: "buscando", PAUSANDO: "pausado",
            PAUSADO: "pausado", ERROR: "error", DETENIDO: "detenido"}.get(estado, "pausado")


def textos_hero(estado: str, error: str | None) -> tuple[str, str]:
    """(título, descripción) del panel principal según el estado."""
    return {
        IDLE: (t("Esperando dispositivo"), t("El PC se anuncia como «gestion_inventario». Abre Sincronizar en el celular.")),
        ESPERANDO_EMPAREJAMIENTO: (t("Esperando dispositivo"), t("Buscando dispositivos...")),
        CONFIRMAR_CODIGO: (t("Confirma el código"), t("Confirma que el celular muestra este código:")),
        CONECTADO: (t("Dispositivo conectado"), t("El celular está conectado y listo para enviar el conteo.")),
        RECIBIENDO: (t("Recibiendo lecturas"), t("Las lecturas del celular están llegando al PC.")),
        PROCESANDO: (t("Procesando datos"), t("Oracle está validando y guardando las lecturas.")),
        LISTO: (t("Sincronización completada"), t("Todas las lecturas recibidas se procesaron.")),
        ERROR: (titulo_de_error(error), error or ""),
        PAUSANDO: (t("Pausando servicio"), t("Pausando: termina la sincronización en curso…")),
        PAUSADO: (t("El servicio Bluetooth está pausado"),
                  t("No se reciben lecturas de los celulares hasta que reanudes el servicio.")),
        DETENIDO: (t("El servicio Bluetooth no está corriendo"),
                   t("Arráncalo en el PC con «docker compose up -d bluetooth».")),
    }.get(estado, (estado, ""))


def modelo_flujo(status: dict, oracle_ok: bool | None, procesando: bool, batch, cont, tasa: float | None) -> dict:
    """Nodos, enlaces y etiquetas del flujo a partir de datos reales. ``procesando`` es el procesamiento manual."""
    estado, error = status["estado"], status.get("ultimo_error")
    ultima = status.get("ultima")
    conectado = estado in (CONECTADO, RECIBIENDO, PROCESANDO, LISTO)
    nodos = []
    if estado == CONFIRMAR_CODIGO:
        nodos.append({"tono": "aviso", "estado": t("Confirmando código")})
    elif conectado:
        nodos.append({"tono": "ok", "estado": t("Conectado")})
    else:
        nodos.append({"tono": "pausa", "estado": t("Sin conexión")})
    nodos[0]["detalle"] = ultima.dispositivo if ultima is not None else t("Sin dispositivo")
    batch_error = estado == ERROR and (error or "").startswith("BATCH:")
    bt = {PAUSADO: ("pausa", t("En pausa")), PAUSANDO: ("aviso", t("Pausando")), DETENIDO: ("aviso", t("Detenido")),
          ERROR: ("ok", t("Canal activo")) if batch_error else ("error", t("Con error")), RECIBIENDO: ("ok", t("Transfiriendo")),
          CONECTADO: ("ok", t("Canal activo")), PROCESANDO: ("ok", t("Canal activo")), LISTO: ("ok", t("Canal activo"))
          }.get(estado, ("ok", t("Esperando")))
    nodos.append({"tono": bt[0], "estado": bt[1], "detalle": ""})
    if batch_error:
        pc = ("error", t("Error al procesar"))
    elif estado == RECIBIENDO:
        pc = ("ok", t("Recibiendo"))
    elif estado == PROCESANDO or procesando:
        pc = ("ok", t("Procesando"))
    else:
        pc = ("pausa", t("Esperando"))
    pendientes = (batch.pendientes + batch.procesando) if batch is not None else 0
    nodos.append({"tono": pc[0], "estado": pc[1], "detalle": t("{n} pendientes", n=pendientes) if pendientes else ""})
    if oracle_ok is None:
        nodos.append({"tono": "pausa", "estado": t("Comprobando"), "detalle": ""})
    elif oracle_ok:
        nodos.append({"tono": "ok", "estado": t("Conectado"), "detalle": t("Disponible")})
    else:
        nodos.append({"tono": "error", "estado": t("Sin conexión"), "detalle": ""})
    # enlaces: solo «activo» (con paquetes) cuando hay transferencia real
    if estado == RECIBIENDO:
        l0 = l1 = "activo"
    elif estado in (CONECTADO, PROCESANDO, LISTO):
        l0 = l1 = "enlazado"
    else:
        l0 = l1 = "off"
    if oracle_ok is False:
        l2 = "off"
    elif estado == PROCESANDO or procesando:
        l2 = "activo"
    else:
        l2 = "enlazado" if oracle_ok else "off"
    etiquetas = ["", t("{n} recibidas", n=sync_ui.formato_miles(cont.recibidas)) if cont and cont.recibidas else "",
                 t("{n} procesadas", n=sync_ui.formato_miles(cont.procesadas)) if cont and cont.procesadas else ""]
    error_nodo = 3 if oracle_ok is False else (2 if batch_error else (1 if estado == ERROR else None))
    velocidad = 1.0 if tasa is None else min(2.5, 0.8 + tasa / 12)
    return {"nodos": nodos, "enlaces": [l0, l1, l2], "etiquetas": etiquetas, "velocidad": velocidad, "error": error_nodo}


def _cargar_todo(rango: str) -> dict:
    """Todo lo que necesita la pantalla de Oracle, en un solo hilo secundario."""
    actividad = sync_datos.fetch_actividad(rango)
    return {
        "batch": db.fetch_estado_batch(),
        "errores": db.fetch_errores(),
        "contadores": sync_datos.fetch_contadores_dia(),
        "actividad": actividad,
        "tasa": sync_datos.lecturas_por_minuto(actividad if rango == "15m" else sync_datos.fetch_actividad("15m")),
    }



def _tarjeta(nombre: str = "tarjetaSync") -> QFrame:
    f = QFrame()
    f.setObjectName(nombre)
    return f


def _etiqueta(texto: str = "", objeto: str | None = None, ajustar: bool = False) -> QLabel:
    e = QLabel(texto)
    if objeto:
        e.setObjectName(objeto)
    e.setWordWrap(ajustar)
    return e


class SyncView(QWidget):
    datos_cambiados = pyqtSignal()
    detalle = pyqtSignal(str)
    cabecera_propia = True   # la ventana oculta su fila de título/estados/«Actualizar»: esta pantalla trae los suyos

    def __init__(self, remoto, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._remoto = remoto
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._errores: list = []
        self._visibles: list = []
        self._colores = colores()
        # lo último que se sabe de Oracle (None = aún sin comprobar)
        self._oracle_ok: bool | None = None
        self._batch = None
        self._cont = None
        self._actividad = None
        self._tasa: float | None = None
        self._rango = sync_datos.RANGO_INICIAL
        self._paso_previo: int | None = None
        self._procesando_manual = False
        self._proceso: int | None = None
        self._esperando_resultado = False
        self._antes_reproceso: int | None = None
        self._intencion: str | None = None
        self._servicio_ocupado = False   # orden pausar/reanudar en curso: se ignoran clics (sin quitar el foco al botón)
        self._ultimo_recibidos = -1
        self._ultimo_estado = ""
        self._entrada_hecha = False
        self._ultima_actualizacion: datetime | None = None
        self._temporizador_datos = QTimer(self)
        self._temporizador_datos.setSingleShot(True)
        self._temporizador_datos.setInterval(700)
        self._temporizador_datos.timeout.connect(self._recargar)

        # ---------------------------------------------------------- A. cabecera
        self.lbl_titulo = _etiqueta(t("Sincronización"), "tituloSync")
        self.lbl_subtitulo = _etiqueta(t("Estado y actividad de transferencia de datos"), "subtitulo")
        self.lbl_actualizado = _etiqueta("", "subtitulo")
        self.pill_oracle = Pildora(t("Comprobando Oracle…"), "pausa")
        self.pill_bluetooth = Pildora(t("Bluetooth en pausa"), "pausa")
        self.btn_actualizar = BotonActualizar(t("Actualizar"))
        self.btn_actualizar.setToolTip(t("Vuelve a sondear el servicio y a intentar la conexión"))
        self.btn_actualizar.clicked.connect(self._clic_actualizar)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(self.lbl_titulo)
        fila_sub = QHBoxLayout()
        fila_sub.setSpacing(10)
        fila_sub.addWidget(self.lbl_subtitulo)
        fila_sub.addWidget(self.lbl_actualizado)
        fila_sub.addStretch(1)
        textos.addLayout(fila_sub)
        self.cabecera = QWidget()
        en_cabecera = QHBoxLayout(self.cabecera)
        en_cabecera.setContentsMargins(4, 0, 4, 0)
        en_cabecera.setSpacing(10)
        en_cabecera.addLayout(textos, 1)
        en_cabecera.addWidget(self.pill_oracle)
        en_cabecera.addWidget(self.pill_bluetooth)
        en_cabecera.addWidget(self.btn_actualizar)
        self.lbl_titulo.setToolTip(
            "<b>" + t("Cómo sincronizar") + "</b><br>"
            + t("1. Mientras el servicio está activo, el PC se anuncia como gestion_inventario, "
                "aunque esta ventana esté cerrada.<br>"
                "2. En el celular abre Sincronizar.<br>"
                "3. Al terminar, Oracle procesa las lecturas y todas las pantallas se actualizan solas."))
        self.lbl_titulo.setToolTipDuration(12000)

        # ---------------------------------------------------------- B. centro de control Bluetooth
        self.icono = IconoBluetooth()
        self.lbl_estado = _etiqueta("", "estadoHeroSync", True)
        self.lbl_ayuda = _etiqueta("", "ayuda", True)
        self.lbl_codigo = QLabel("")
        self.lbl_codigo.setObjectName("codigoSync")
        self.lbl_codigo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        codigo = self.lbl_codigo.font()
        codigo.setPointSize(30)
        codigo.setBold(True)
        codigo.setFamily("DejaVu Sans Mono")
        self.lbl_codigo.setFont(codigo)
        self.lbl_ultima = _etiqueta("", "subtitulo", True)
        self.lbl_dispositivo = _etiqueta("", "subtitulo", True)
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.setStyleSheet(f"color: {self._colores['error']};")
        self.btn_pausar = QPushButton(t("Pausar servicio"))
        self.btn_pausar.setObjectName("primario")
        self.btn_pausar.setMinimumHeight(40)
        self.btn_aceptar = QPushButton(t("Aceptar código"))
        self.btn_rechazar = QPushButton(t("Rechazar"))
        self.btn_reintentar = QPushButton(t("Reintentar"))
        self.btn_reintentar.hide()
        self.btn_pausar.clicked.connect(self._clic_pausar)
        self.btn_aceptar.clicked.connect(lambda: self._responder(True))
        self.btn_rechazar.clicked.connect(lambda: self._responder(False))
        self.btn_reintentar.clicked.connect(self._clic_actualizar)
        remoto.fallo.connect(self._fallo_servicio)
        botones = QHBoxLayout()
        botones.setSpacing(8)
        for b in (self.btn_pausar, self.btn_aceptar, self.btn_rechazar, self.btn_reintentar):
            botones.addWidget(b)
        botones.addStretch(1)
        izquierda = QVBoxLayout()
        izquierda.setSpacing(6)
        for w in (self.lbl_estado, self.lbl_ayuda, self.lbl_codigo):
            izquierda.addWidget(w)
        izquierda.addSpacing(4)
        izquierda.addWidget(self.lbl_ultima)
        izquierda.addWidget(self.lbl_dispositivo)
        izquierda.addWidget(self.lbl_aviso)
        izquierda.addStretch(1)
        izquierda.addLayout(botones)
        zona_izquierda = QHBoxLayout()
        zona_izquierda.setSpacing(22)
        zona_izquierda.addWidget(self.icono, 0, Qt.AlignmentFlag.AlignVCenter)
        zona_izquierda.addLayout(izquierda, 1)

        self.pill_actividad = Pildora(t("Esperando dispositivo"), "pausa")
        self.contadores: dict[str, Odometro] = {}
        rejilla = QGridLayout()
        rejilla.setSpacing(12)
        for k, (clave, titulo, sub, color) in enumerate((
                ("recibidas", "Lecturas recibidas", "hoy", "texto_fuerte"),
                ("procesadas", "Lecturas procesadas", "hoy", "acento"),
                ("pendientes", "Lecturas pendientes", "por procesar", "aviso"),
                ("errores", "Lecturas con error", "sin resolver", "error"))):
            caja = _tarjeta("contadorSync")
            en_caja = QVBoxLayout(caja)
            en_caja.setContentsMargins(16, 12, 16, 12)
            en_caja.setSpacing(0)
            odometro = Odometro(0, 38, color)
            self.contadores[clave] = odometro
            en_caja.addWidget(odometro)
            en_caja.addWidget(_etiqueta(t(titulo), "seccion"))
            en_caja.addWidget(_etiqueta(t(sub), "subtitulo"))
            rejilla.addWidget(caja, k // 2, k % 2)
        divisor = QFrame()
        divisor.setObjectName("divisorSync")
        derecha = QVBoxLayout()
        derecha.setSpacing(12)
        derecha.addWidget(self.pill_actividad, 0, Qt.AlignmentFlag.AlignLeft)
        derecha.addLayout(rejilla, 1)
        self.hero = _tarjeta()
        en_hero = QHBoxLayout(self.hero)
        en_hero.setContentsMargins(26, 22, 26, 22)
        en_hero.setSpacing(26)
        en_hero.addLayout(zona_izquierda, 5)
        en_hero.addWidget(divisor)
        en_hero.addLayout(derecha, 4)
        self.hero.setMinimumHeight(240)

        # ---------------------------------------------------------- C. flujo de datos + etapas
        self.flujo = FlujoDatos()
        self.flujo.elegido.connect(lambda i: self.detalle.emit("celular" if i == 0 else "pc") if i in (0, 2) else None)
        self.etapas = Etapas([t(p) for p in PASOS_ES])
        self.tarjeta_flujo = _tarjeta()
        en_flujo = QVBoxLayout(self.tarjeta_flujo)
        en_flujo.setContentsMargins(22, 18, 22, 16)
        en_flujo.setSpacing(6)
        cab_flujo = QHBoxLayout()
        cab_flujo.addWidget(_etiqueta(t("Flujo de datos"), "seccion"))
        cab_flujo.addWidget(_etiqueta(t("Android → Bluetooth → PC servidor → Oracle"), "subtitulo"))
        cab_flujo.addStretch(1)
        en_flujo.addLayout(cab_flujo)
        self.flujo.setMaximumHeight(200)
        en_flujo.addWidget(self.flujo)
        en_flujo.addStretch(1)
        en_flujo.addWidget(self.etapas)

        # ---------------------------------------------------------- D. actividad y estadísticas
        self.grafica = GraficaActividad()
        self.grafica.textos(t("Sin actividad en este periodo"), t("Cuando lleguen lecturas, aparecerán aquí."),
                            t("Cargando…"))
        self.botones_rango: dict[str, QPushButton] = {}
        segmentado = QFrame()
        segmentado.setObjectName("segmentado")
        en_seg = QHBoxLayout(segmentado)
        en_seg.setContentsMargins(3, 3, 3, 3)
        en_seg.setSpacing(2)
        grupo = QButtonGroup(self)
        grupo.setExclusive(True)
        for clave, corto, largo in RANGOS_ES:
            b = QPushButton(t(corto))
            b.setObjectName("segmento")
            b.setCheckable(True)
            b.setToolTip(t(largo))
            b.setChecked(clave == self._rango)
            b.clicked.connect(lambda _=False, c=clave: self._cambiar_rango(c))
            grupo.addButton(b)
            en_seg.addWidget(b)
            self.botones_rango[clave] = b
        self._grupo_rango = grupo
        self.stats: dict[str, QLabel] = {}
        fila_stats = QHBoxLayout()
        fila_stats.setSpacing(10)
        for clave, titulo in (("recibidas", "Recibidas"), ("procesadas", "Procesadas"),
                              ("errores", "Errores registrados"), ("minuto", "Actividad por minuto"),
                              ("ultima", "Última sincronización")):
            caja = _tarjeta("contadorSync")
            en_caja = QVBoxLayout(caja)
            en_caja.setContentsMargins(14, 9, 14, 9)
            en_caja.setSpacing(0)
            en_caja.addWidget(_etiqueta(t(titulo), "subtitulo"))
            valor = _etiqueta("—", "valorStatSync")
            self.stats[clave] = valor
            en_caja.addWidget(valor)
            fila_stats.addWidget(caja, 1)
        self.tarjeta_actividad = _tarjeta()
        en_act = QVBoxLayout(self.tarjeta_actividad)
        en_act.setContentsMargins(22, 18, 22, 16)
        en_act.setSpacing(12)
        cab_act = QHBoxLayout()
        cab_act.addWidget(_etiqueta(t("Actividad"), "seccion"))
        cab_act.addStretch(1)
        cab_act.addWidget(segmentado)
        en_act.addLayout(cab_act)
        en_act.addLayout(fila_stats)
        en_act.addWidget(self.grafica, 1)

        # ---------------------------------------------------------- E. lecturas con error
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_cuenta = _etiqueta("", "badgeSync")
        self.lbl_ultimo_run = _etiqueta("", "subtitulo")
        self.chip_nuevos = Pildora(t("Nuevos SKU: 0"), "pausa")
        self.chip_nuevos.setToolTip(
            t("Lecturas con un SKU que no está en el catálogo: se deciden en el aviso flotante "
              "(«Crear y procesar» o «No crear») y no cuentan como error."))
        self.lbl_nuevos = _etiqueta(t("No hay SKU nuevos pendientes de decisión."), "subtitulo", True)
        self.combo_motivo = QComboBox()
        self.combo_motivo.addItem(t(TODOS_LOS_MOTIVOS))
        self.combo_motivo.setMinimumWidth(200)
        self.btn_reprocesar = QPushButton(t("Reprocesar errores"))
        self.btn_procesar = QPushButton(t("Procesar ahora"))
        self.progreso = QProgressBar()
        self.progreso.setObjectName("progresoSync")
        self.progreso.setRange(0, 0)
        self.progreso.setTextVisible(False)
        self.progreso.hide()
        self.tabla_errores = TablaErrores(len(ENCABEZADOS_ERRORES))
        self.tabla_errores.setHorizontalHeaderLabels([t(c) for c in ENCABEZADOS_ERRORES])
        self.tabla_errores.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla_errores.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla_errores.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla_errores.verticalHeader().hide()
        self.tabla_errores.horizontalHeader().setStretchLastSection(True)
        self.tabla_errores.horizontalHeader().setHighlightSections(False)
        self.tabla_errores.setMinimumHeight(150)
        self.vacio = EstadoVacio(t("Todo está en orden"), t("No hay lecturas pendientes de revisión"))
        self.pila = QStackedWidget()
        self.pila.addWidget(self.tabla_errores)
        self.pila.addWidget(self.vacio)
        barra = QHBoxLayout()
        barra.setSpacing(8)
        barra.addWidget(_etiqueta(t("Lecturas con error"), "seccion"))
        barra.addWidget(self.lbl_cuenta)
        barra.addWidget(self.chip_nuevos)
        barra.addStretch(1)
        for w in (self.combo_motivo, self.btn_reprocesar, self.btn_procesar):
            barra.addWidget(w)
        self.tarjeta_errores = _tarjeta()
        en_errores = QVBoxLayout(self.tarjeta_errores)
        en_errores.setContentsMargins(22, 18, 22, 14)
        en_errores.setSpacing(8)
        en_errores.addLayout(barra)
        en_errores.addWidget(self.lbl_ultimo_run)
        en_errores.addWidget(self.lbl_nuevos)
        en_errores.addWidget(self.progreso)
        en_errores.addWidget(self.banner)
        en_errores.addWidget(self.pila, 1)

        # ---------------------------------------------------------- composición
        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 8, 8)
        raiz.setSpacing(16)
        raiz.addWidget(self.cabecera)
        raiz.addWidget(self.hero, 3)
        raiz.addWidget(self.tarjeta_flujo, 4)
        raiz.addWidget(self.tarjeta_actividad, 4)
        raiz.addWidget(self.tarjeta_errores, 4)
        self.tarjeta_actividad.setMinimumHeight(340)
        self.tarjeta_errores.setMinimumHeight(330)
        self.tarjeta_flujo.setMinimumHeight(330)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(self._contenido)
        self._desplazable = desplazable
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(desplazable)
        self.combo_motivo.currentIndexChanged.connect(lambda _: self._filtrar())
        self.btn_procesar.clicked.connect(lambda: self._accion(db.procesar_ahora))
        self.btn_reprocesar.clicked.connect(lambda: self._accion(db.reprocesar_errores, reprocesa=True))

        remoto.status_changed.connect(self._actualizar)
        self._poner_cuenta()
        self._pintar_oracle()
        self._actualizar(remoto.status())

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if not self._entrada_hecha:
            self._entrada_hecha = True
            sync_ui.entrada_escalonada([self.cabecera, self.hero, self.tarjeta_flujo, self.tarjeta_actividad,
                                        self.tarjeta_errores])

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._actualizar(self._remoto.status())
        if sesion is not None:
            self.refresh()

    def refresh(self) -> None:
        self._remoto.sondear()
        self._actualizar(self._remoto.status())
        if self._sesion is not None:
            self.btn_actualizar.iniciar()
            self._recargar()
        else:
            self.btn_actualizar.detener()

    def errores(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla_errores.item(f, c).text() if self.tabla_errores.item(f, c) else ""
                      for c in range(len(ENCABEZADOS_ERRORES)))
                for f in range(self.tabla_errores.rowCount())]

    # ------------------------------------------------------------- carga desde Oracle
    def _recargar(self) -> None:
        if self._sesion is None:
            return
        self._runner.run(_cargar_todo, self._mostrar, self._fallo_carga, self._rango, key="sync")

    def _programar_recarga(self) -> None:
        if self._sesion is not None and not self._temporizador_datos.isActive():
            self._temporizador_datos.start()

    def _clic_actualizar(self) -> None:
        self.refresh()

    def _fallo_carga(self, mensaje: str) -> None:
        self.btn_actualizar.detener()
        habia = self._oracle_ok is not False
        self._oracle_ok = False
        self._pintar_oracle()
        self._refrescar_flujo()
        if habia:
            isla.estado("oracle-sync", "error", t("Oracle desconectado"), mensaje)
        if self._esperando_resultado:
            self._esperando_resultado = False
            self._terminar_proceso("error", t("No se pudo consultar Oracle"), mensaje)
            self.progreso.hide()

    def _mostrar(self, datos: dict) -> None:
        if self._oracle_ok is False:
            isla.quitar_estado("oracle-sync")
            isla.exito(t("Oracle conectado de nuevo"))
        self._oracle_ok = True
        self.banner.clear()
        self.btn_actualizar.detener()
        self._batch, self._cont, self._tasa = datos["batch"], datos["contadores"], datos["tasa"]
        self._actividad = datos["actividad"]
        self._ultima_actualizacion = datetime.now()
        self.lbl_actualizado.setText("· " + t("Última actualización {hora}", hora=f"{self._ultima_actualizacion:%H:%M:%S}"))
        self._pintar_oracle()
        self._poner_contadores()
        self._poner_nuevos()
        self._pintar_actividad()
        estado = self._batch
        self.lbl_ultimo_run.setText(
            t("Aún no se ha procesado nada") if estado.ultimo_run is None else
            t("· último procesamiento {fecha} UTC ({origen}) · {pendientes} pendientes, {errores} con error, "
              "{nuevos} nuevos, {descartados} descartados",
              fecha=f"{estado.ultimo_run:%Y-%m-%d %H:%M}", origen=estado.ultimo_origen,
              pendientes=estado.pendientes, errores=estado.errores,
              nuevos=estado.nuevos, descartados=estado.descartados))
        nuevos = list(datos["errores"])
        quitados = [i for i, e in enumerate(self._visibles) if e.id_transito not in {n.id_transito for n in nuevos}]
        self._errores_nuevos = nuevos
        self.tabla_errores.desvanecer_filas(quitados, lambda: self._aplicar_errores(nuevos))
        self._refrescar_flujo()

    def _aplicar_errores(self, errores: list) -> None:
        self._errores = list(errores)
        motivos = sorted({e.mensaje_error for e in errores if e.mensaje_error})
        actual = self.combo_motivo.currentData()
        self.combo_motivo.blockSignals(True)
        self.combo_motivo.clear()
        self.combo_motivo.addItem(t(TODOS_LOS_MOTIVOS))
        for motivo in motivos:
            self.combo_motivo.addItem(motivo_legible(motivo), motivo)
        indice = self.combo_motivo.findData(actual) if actual else 0
        self.combo_motivo.setCurrentIndex(indice if indice >= 0 else 0)
        self.combo_motivo.blockSignals(False)
        self._filtrar()
        self._poner_cuenta()
        self._terminar_resultado()

    def _terminar_resultado(self) -> None:
        """Comunica por la Isla qué pasó con el procesamiento/reprocesamiento que lanzó esta pantalla."""
        if not self._esperando_resultado:
            return
        self._esperando_resultado = False
        self.progreso.hide()
        antes, ahora = self._antes_reproceso, len(self._errores)
        self._antes_reproceso = None
        if antes is None:
            self._terminar_proceso("exito", t("Procesamiento completado"))
        elif antes == 0:
            self._terminar_proceso("info", t("No había errores que reprocesar"))
        elif ahora == 0:
            self._terminar_proceso("exito", t("Errores reprocesados"), t("{n} lecturas resueltas", n=antes))
        elif ahora < antes:
            self._terminar_proceso("advertencia", t("Errores reprocesados"),
                                   t("{n} reprocesados · {m} siguen con error", n=antes - ahora, m=ahora))
        else:
            self._terminar_proceso("advertencia", t("Sin cambios"), t("Las {n} lecturas siguen con error", n=ahora))

    def _poner_cuenta(self) -> None:
        n = len(self._errores)
        self.lbl_cuenta.setText(t("1 error pendiente") if n == 1 else
                                t("{n} errores pendientes", n=n) if n else t("Sin errores pendientes"))
        self.lbl_cuenta.setProperty("vacio", "true" if n == 0 else "false")
        self.lbl_cuenta.style().unpolish(self.lbl_cuenta)
        self.lbl_cuenta.style().polish(self.lbl_cuenta)

    def _poner_contadores(self) -> None:
        if self._cont is not None:
            self.contadores["recibidas"].set_valor(self._cont.recibidas)
            self.contadores["procesadas"].set_valor(self._cont.procesadas)
        if self._batch is not None:
            self.contadores["pendientes"].set_valor(self._batch.pendientes + self._batch.procesando)
            self.contadores["errores"].set_valor(self._batch.errores)

    def _poner_nuevos(self) -> None:
        """Chip «Nuevos SKU» con el conteo de ``v_estado_batch.nuevos`` y su ayuda, sin contarlos como error."""
        nuevos = self._batch.nuevos if self._batch is not None else 0
        self.chip_nuevos.set_estado("aviso" if nuevos else "ok", t("Nuevos SKU: {n}", n=nuevos))
        self.lbl_nuevos.setText(
            t("Los SKU nuevos esperan tu decisión en el aviso flotante («Crear y procesar» o «No crear»). "
              "Ya no cuentan como error.") if nuevos
            else t("No hay SKU nuevos pendientes de decisión."))

    def _pintar_oracle(self) -> None:
        if self._oracle_ok is None:
            self.pill_oracle.set_estado("pausa", t("Comprobando Oracle…"))
        elif self._oracle_ok:
            self.pill_oracle.set_estado("ok", t("Oracle conectado"))
        else:
            self.pill_oracle.set_estado("error", t("Oracle sin conexión"))

    # ------------------------------------------------------------- actividad
    def _cambiar_rango(self, clave: str) -> None:
        if clave == self._rango:
            return
        self._rango = clave
        for k, b in self.botones_rango.items():
            b.setChecked(k == clave)
        if self._sesion is not None:
            self._runner.run(sync_datos.fetch_actividad, self._actividad_lista, self._fallo_carga, clave,
                             key="actividad")

    def _actividad_lista(self, act) -> None:
        if act.rango != self._rango:
            return
        self._actividad = act
        self._pintar_actividad()

    def _poner_stat(self, clave: str, texto: str) -> None:
        etiqueta = self.stats[clave]
        if etiqueta.text() != texto:
            etiqueta.setText(texto)
            if widgets.ANIMAR and etiqueta.isVisible():
                motion.desvanecer(etiqueta, 0.25, 1.0, 220, lambda e=etiqueta: e.setGraphicsEffect(None))

    def _pintar_actividad(self) -> None:
        act = self._actividad
        self.grafica.set_actividad(act)
        if act is None:
            return
        self._poner_stat("recibidas", sync_ui.formato_miles(sum(act.recibidas)))
        self._poner_stat("procesadas", sync_ui.formato_miles(sum(act.procesadas)))
        self._poner_stat("errores", sync_ui.formato_miles(sum(act.errores)))
        tasa = sync_datos.lecturas_por_minuto(act)
        self._poner_stat("minuto", "—" if tasa is None else t("{v} /min", v=f"{tasa:.1f}".replace(".", ",")))
        ultima = self._remoto.status().get("ultima")
        self._poner_stat("ultima", "—" if ultima is None else f"{ultima.fin:%d/%m %H:%M}")

    # ------------------------------------------------------------- tabla de errores
    def _filtrar(self) -> None:
        motivo = self.combo_motivo.currentData()
        self._visibles = [e for e in self._errores if motivo is None or e.mensaje_error == motivo]
        self.tabla_errores.clearSelection()
        self.tabla_errores.setRowCount(len(self._visibles))
        for fila, e in enumerate(self._visibles):
            celdas = (e.uuid_dispositivo, str(e.seq), e.sku, motivo_legible(e.mensaje_error),
                      f"{e.fecha_recepcion:%d/%m/%Y %H:%M}" if e.fecha_recepcion else "", t("Con error"))
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                item.setToolTip(texto)
                self.tabla_errores.setItem(fila, columna, item)
        cab = self.tabla_errores.horizontalHeader()
        self.tabla_errores.resizeColumnsToContents()
        for c in range(len(ENCABEZADOS_ERRORES)):
            cab.resizeSection(c, max(cab.sectionSize(c) + 28, 96))
        self._pila_vacia()

    def _pila_vacia(self) -> None:
        hay = bool(self._visibles)
        if not hay:
            sin_filtro = not self._errores
            self.vacio.lbl_titulo.setText(t("Todo está en orden") if sin_filtro else t("Ninguna lectura con este motivo"))
            self.vacio.lbl_desc.setText(t("No hay lecturas pendientes de revisión") if sin_filtro
                                        else t("Cambia el filtro para ver los demás errores."))
        self.pila.setCurrentWidget(self.tabla_errores if hay else self.vacio)

    # ------------------------------------------------------------- procesar / reprocesar
    def _accion(self, operacion, reprocesa: bool = False) -> None:
        barra = self._desplazable.verticalScrollBar()
        posicion = barra.value()
        self.btn_procesar.setEnabled(False)
        self.btn_reprocesar.setEnabled(False)
        barra.setValue(posicion)   # deshabilitar el botón con foco lo pasa a otro widget y el scroll saltaba
        self.progreso.show()
        self._antes_reproceso = len(self._errores) if reprocesa else None
        self._proceso = isla.cargando(t("Reprocesando errores…") if reprocesa else t("Procesando lecturas…"))
        self._procesando_manual = True
        self._refrescar_flujo()
        self._runner.run(operacion, self._accion_lista, self._accion_fallo)

    def _terminar_proceso(self, tipo: str, titulo: str, descripcion: str = "") -> None:
        id_, self._proceso = self._proceso, None
        if id_ is None:
            getattr(isla, tipo)(titulo, descripcion)
        else:
            isla.actualizar(id_, tipo, titulo, descripcion)

    def _accion_lista(self, _resultado) -> None:
        self._procesando_manual = False
        self._esperando_resultado = True
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self._refrescar_flujo()
        self.refresh()
        self.datos_cambiados.emit()

    def _accion_fallo(self, mensaje: str) -> None:
        self._procesando_manual = False
        self._esperando_resultado = False
        self.progreso.hide()
        self._terminar_proceso("error", t("No se pudo procesar"), mensaje)
        self.btn_procesar.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self._refrescar_flujo()

    # ------------------------------------------------------------- servicio Bluetooth
    def _puede_gestionar(self) -> bool:
        return self._sesion is not None and self._sesion.puede("sync", "GESTION")

    def _clic_pausar(self) -> None:
        if self._sesion is None or self._servicio_ocupado:
            return
        self.lbl_aviso.hide()
        # No se deshabilita el botón: al perder el foco, Qt lo pasa a un widget de más abajo y el QScrollArea
        # desplaza la pantalla hasta él (la vista saltaba al pulsar Pausar/Reanudar).
        self._servicio_ocupado = True
        if self._remoto.status()["estado"] in (PAUSADO, PAUSANDO):
            self._intencion = "reanudar"
            self._remoto.reanudar(self._sesion)
        else:
            self._intencion = "pausar"
            self._remoto.pausar(self._sesion)

    def _responder(self, aceptar: bool) -> None:
        if self._sesion is not None:
            self._remoto.responder(self._sesion, aceptar)

    def _fallo_servicio(self, mensaje: str) -> None:
        self._intencion = None
        self._servicio_ocupado = False
        self.lbl_aviso.setText(mensaje)
        self.lbl_aviso.setVisible(bool(mensaje))
        if mensaje:
            isla.error(t("No se pudo controlar el servicio Bluetooth"), mensaje)

    def _refrescar_flujo(self) -> None:
        m = modelo_flujo(self._remoto.status(), self._oracle_ok, self._procesando_manual, self._batch, self._cont,
                         self._tasa)
        self.flujo.set_modelo(m["nodos"], m["enlaces"], m["etiquetas"], m["velocidad"], m["error"])

    def _actualizar(self, status: dict) -> None:
        estado, recibidos = status["estado"], status["recibidos"]
        error = status["ultimo_error"]
        gestiona = self._puede_gestionar()
        titulo, descripcion = textos_hero(estado, error)
        self.lbl_estado.setText(titulo)
        self.lbl_ayuda.setText(descripcion)
        self.lbl_ayuda.setVisible(bool(descripcion))
        self.icono.set_modo(modo_icono(estado))
        self.lbl_codigo.setText(status["codigo"] or "")
        self.lbl_codigo.setVisible(estado == CONFIRMAR_CODIGO and bool(status["codigo"]))
        self.btn_aceptar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)
        self.btn_rechazar.setVisible(estado == CONFIRMAR_CODIGO and gestiona)
        self.btn_procesar.setVisible(gestiona)
        self.btn_reprocesar.setVisible(gestiona)
        self.btn_reintentar.setVisible(estado in (ERROR, DETENIDO) and gestiona)

        ultima = status.get("ultima")
        self.lbl_ultima.setText(
            t("Aún no ha llegado ninguna sincronización.") if ultima is None else
            t("Última sincronización: {fecha} · {n} lecturas", fecha=f"{ultima.fin:%d/%m/%Y %H:%M}", n=ultima.recibidos))
        self.lbl_dispositivo.setText(
            t("Aún no se ha conectado ningún dispositivo") if ultima is None
            else t("Último dispositivo: {nombre}", nombre=ultima.dispositivo))
        self.lbl_aviso.setText(error or "")   # el error del servicio lo muestra la Isla (estado persistente de Bluetooth)
        self.lbl_aviso.setVisible(False)

        tono, texto = estado_bluetooth(estado, error)
        self.pill_bluetooth.set_estado(tono, texto)
        if estado == RECIBIENDO:
            self.pill_actividad.set_estado("ok", t("Recibiendo lecturas · {n}", n=sync_ui.formato_miles(recibidos)))
        else:
            tono_a = {ERROR: "error", DETENIDO: "error", PAUSANDO: "aviso", PAUSADO: "pausa", IDLE: "ok",
                      ESPERANDO_EMPAREJAMIENTO: "ok"}.get(estado, "ok")
            corto = {IDLE: t("Esperando dispositivo"), ESPERANDO_EMPAREJAMIENTO: t("Esperando dispositivo"),
                     CONFIRMAR_CODIGO: t("Confirma el código"), CONECTADO: t("Dispositivo conectado"),
                     PROCESANDO: t("Procesando datos"), LISTO: t("Sincronización completada"),
                     PAUSANDO: t("Pausando"), PAUSADO: t("En pausa"), DETENIDO: t("Detenido"),
                     ERROR: t("Con error")}.get(estado, titulo)
            self.pill_actividad.set_estado(tono_a, corto)

        # etapas: reflejan el estado real; si falla, el error se marca en la última etapa alcanzada
        paso = PASO_DE.get(estado)
        if paso is not None:
            self._paso_previo = paso
        actual, hechas, en_error = modelo_etapas(estado, self._paso_previo)
        self.etapas.set_estado(actual, hechas, en_error)
        self._refrescar_flujo()

        self.btn_pausar.setText(t("Reanudar servicio") if estado in (PAUSADO, PAUSANDO) else t("Pausar servicio"))
        self.btn_pausar.setVisible(gestiona and estado != DETENIDO)
        self._servicio_ocupado = False
        if self._intencion == "reanudar" and estado not in (PAUSADO, PAUSANDO):
            self._intencion = None
            isla.exito(t("Bluetooth reanudado"))
        elif self._intencion == "pausar" and estado in (PAUSADO, PAUSANDO):
            self._intencion = None   # el aviso de «en pausa» ya lo da la Isla global (estado persistente de Bluetooth)

        # los contadores del día siguen al servicio: se recargan cuando cambia el estado o llegan más lecturas
        if estado != self._ultimo_estado or recibidos != self._ultimo_recibidos:
            self._ultimo_estado, self._ultimo_recibidos = estado, recibidos
            self._programar_recarga()
