"""Pantalla «Dashboard»: el avance del conteo continuo, personalizable por cada persona.

Cada usuario arma su propio espacio: agrega widgets del catálogo (indicadores, paneles y gráficos con datos reales),
los reordena arrastrando, cambia su tamaño y configura cada gráfico (tipo, período, orden…). La distribución se guarda
por usuario. Un widget solo se ofrece si el rol de la persona puede consultar su módulo.

No hay cierres: el conteo siempre está abierto y este panel se recalcula con cada sincronización.
"""

from __future__ import annotations

import copy
import time
from functools import partial

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout,
                             QWidget)

from .. import auth, db
from .. import dashboard_prefs as prefs
from ..dashboard_datos import Datos, construir
from ..i18n import registrar, t
from ..models import fmt_num, fmt_pct
from ..tema import colores
from . import components
from .base import QueryRunner, StateBanner
from .dashboard_paneles import CatalogoWidgets, ConfigGrafico
from .grafico_personal import GraficoPersonal
from .iconos import icono
from .isla import isla
from .rejilla_personal import Baldosa, RejillaPersonal
from . import widgets
from .widgets import VERDE, TarjetaKpi

registrar({
    "Conteo continuo": "Continuous count",
    "Avance del inventario físico, sin cierres ni tareas. Se actualiza con cada sincronización.":
        "Progress of the physical inventory, with no closures or tasks. It updates with every sync.",
    "Avance": "Progress", "Contados": "Counted", "Faltantes": "Short", "Sobrantes": "Over",
    "Estado del batch": "Batch status", "Sin datos": "No data", "SKU contados": "SKUs counted", "de": "of",
    "SKU": "SKU", "Valor": "Value", "Desglose": "Breakdown", "Alcance": "Scope",
    "Todavía no se ha procesado ninguna sincronización.": "No synchronization has been processed yet.",
    "Último procesamiento": "Last run", "lecturas procesadas": "readings processed", "con error": "with error",
    "pendientes": "pending",
    "Personalizar dashboard": "Customize dashboard", "Restaurar predeterminado": "Restore default",
    "Arrastra para reordenar. Usa ⋯ para cambiar el tamaño o configurar.":
        "Drag to reorder. Use ⋯ to resize or configure.",
    "Configurar gráfico…": "Configure chart…", "Cambiar tipo": "Change type", "Cambiar período": "Change period",
    "Tamaño": "Size", "Actualizar información": "Refresh data", "Duplicar gráfico": "Duplicate chart",
    "Eliminar del dashboard": "Remove from dashboard", "Personalizado…": "Custom…",
    "Restaurar dashboard predeterminado": "Restore default dashboard",
    "Se perderá la distribución que armaste y volverá la inicial. Tus datos no se tocan.":
        "Your layout will be lost and the initial one will return. Your data is not touched.",
    "Restaurar": "Restore", "Dashboard restaurado": "Dashboard restored", "Sin actividad registrada.": "No activity recorded.",
    "con error:": "with error:",
    "Se perdió la conexión con los datos de los gráficos.": "Chart data could not be loaded.",
})

TARJETAS = (
    ("avance", "Avance", VERDE),
    ("contados", "Contados", VERDE),
    ("faltantes", "Faltantes", "#F04438"),
    ("sobrantes", "Sobrantes", "#F79009"),
)
FUENTES_SERIES = {"avance_categoria", "lecturas_categoria", "danados", "contados_pendientes", "lecturas_tiempo",
                  "batch_corridas"}
FUENTES_ACTIVIDAD = {"operador", "operador_tiempo"}


INTENTOS = 3        # un fallo suelto de Oracle (p. ej. ORA-12516 al abrir conexiones seguidas) no deja el widget vacío
ESPERA_REINTENTO = 0.4


def _con_reintentos(fn, *args, **kwargs):
    for intento in range(1, INTENTOS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if intento == INTENTOS:
                raise
            time.sleep(ESPERA_REINTENTO * intento)


def _cargar(series: bool, actividad: bool, sesion_audit):
    """Corre en un hilo de trabajo: lo básico y, solo si hay widgets que lo piden, series, actividad y auditoría."""
    extra: dict = {}
    if series:
        extra["series"] = _con_reintentos(db.fetch_series, top=40)
    if actividad:
        extra["actividad"] = _con_reintentos(db.fetch_actividad)
    if sesion_audit is not None:
        from .. import auditoria
        try:
            extra["auditoria"] = auditoria.listar(sesion_audit)[:8]
        except Exception:      # sin permiso o sin tabla: el panel simplemente queda sin entradas
            extra["auditoria"] = []
    return (_con_reintentos(db.fetch_resumen), _con_reintentos(db.fetch_estado_batch),
            _con_reintentos(db.fetch_por_categoria), extra)


def _fmt_entero(valor: float) -> str:
    return fmt_num(round(valor, 0))


class _Marco(QFrame):
    """Tarjeta con título para paneles y gráficos."""

    def __init__(self, titulo: str, cuerpo: QWidget) -> None:
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)
        self.rotulo = QLabel(titulo)
        self.rotulo.setObjectName("seccion")
        self.rotulo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._titulo = titulo
        lay.addWidget(self.rotulo)
        lay.addWidget(cuerpo, 1)
        self.cuerpo = cuerpo

    def poner_titulo(self, texto: str) -> None:
        self._titulo = texto
        self._elidir()

    def _elidir(self) -> None:
        # deja sitio a los botones ⋯ y − de la baldosa
        ancho = max(40, self.width() - 36 - 64)
        self.rotulo.setText(self.rotulo.fontMetrics().elidedText(self._titulo, Qt.TextElideMode.ElideRight, ancho))
        self.rotulo.setToolTip(self._titulo if self.rotulo.text() != self._titulo else "")

    def resizeEvent(self, evento) -> None:
        super().resizeEvent(evento)
        self._elidir()


class DashboardView(QWidget):
    conteo_cerrado = pyqtSignal(str)   # compatibilidad: ya no existe el cierre de conteo
    filtro = pyqtSignal(str, str)      # clic en una barra: (categoría, etiqueta)
    detalle = pyqtSignal(str)          # clic en una tarjeta: clave del KPI

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._cargado = False
        self._categorias: list[tuple[str, float]] = []
        self._colores = colores()
        self._resumen = None
        self._batch = None
        self._crudo: dict = {}
        self._items: list[prefs.Item] = []
        self._graficos: dict[str, GraficoPersonal] = {}
        self._marcos: dict[str, _Marco] = {}
        self.cards: dict[str, TarjetaKpi] = {}
        self._hojas: dict[str, QWidget] = {}
        self._edicion = False
        self._fallo = False     # la última carga falló (tras los reintentos): los widgets dejan de decir «Cargando…»

        self.titulo = QLabel(t("Conteo continuo"))
        self.titulo.setObjectName("seccion")
        self.subtitulo = QLabel(t("Avance del inventario físico, sin cierres ni tareas. Se actualiza con cada sincronización."))
        self.subtitulo.setObjectName("subtitulo")
        self.subtitulo.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self._etiquetas: dict[str, QLabel] = {}   # texto de los paneles que hay ahora mismo (batch, actividad)

        textos = QVBoxLayout()
        textos.setSpacing(2)
        textos.addWidget(self.titulo)
        textos.addWidget(self.subtitulo)
        self.btn_personalizar = QPushButton(" " + t("Personalizar dashboard"))
        self.btn_personalizar.setIcon(icono("sliders", tam=16))
        self.btn_personalizar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_personalizar.clicked.connect(lambda: self.set_edicion(True))
        encabezado = QHBoxLayout()
        encabezado.addLayout(textos, 1)
        encabezado.addWidget(self.btn_personalizar, 0, Qt.AlignmentFlag.AlignTop)

        self.barra_edicion = QFrame()
        self.barra_edicion.setObjectName("barraEdicion")
        fila = QHBoxLayout(self.barra_edicion)
        fila.setContentsMargins(14, 8, 8, 8)
        fila.setSpacing(8)
        pista = QLabel(t("Arrastra para reordenar. Usa ⋯ para cambiar el tamaño o configurar."))
        pista.setObjectName("ayuda")
        self.btn_agregar = QPushButton(" " + t("Agregar widget"))
        self.btn_restaurar = QPushButton(" " + t("Restaurar predeterminado"))
        self.btn_listo = QPushButton(" " + t("Listo"))
        self.btn_listo.setObjectName("primario")
        self.btn_agregar.setIcon(icono("plus", tam=16))
        self.btn_restaurar.setIcon(icono("rotate_ccw", tam=16))
        self.btn_listo.setIcon(icono("check", color="#04130E", tam=16))
        for b in (self.btn_agregar, self.btn_restaurar, self.btn_listo):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        fila.addWidget(pista, 1)
        fila.addWidget(self.btn_agregar)
        fila.addWidget(self.btn_restaurar)
        fila.addWidget(self.btn_listo)
        self.barra_edicion.hide()
        self.btn_agregar.clicked.connect(self._abrir_catalogo)
        self.btn_restaurar.clicked.connect(self.restaurar)
        self.btn_listo.clicked.connect(lambda: self.set_edicion(False))

        self.rejilla = RejillaPersonal()
        self.rejilla.orden_cambiado.connect(self._orden_cambiado)
        self._contenido = QWidget()
        raiz = QVBoxLayout(self._contenido)
        raiz.setContentsMargins(4, 4, 4, 16)
        raiz.setSpacing(12)
        raiz.addLayout(encabezado)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.barra_edicion)
        raiz.addWidget(self.rejilla)
        raiz.addStretch(1)

        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(self._contenido)
        exterior = QVBoxLayout(self)
        exterior.setContentsMargins(0, 0, 0, 0)
        exterior.addWidget(desplazable)

    # ------------------------------------------------------------------ API de la vista
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self._cargado = False
        if sesion is None:
            self._items = []
            self._reconstruir()
            self.banner.show_empty(t("Sin datos"))
            return
        self._items = prefs.cargar(sesion.usuario, sesion)
        self._reconstruir()
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None:
            return
        if not self._cargado:
            self.banner.show_loading()
        claves = {i.clave for i in self._items}
        audit = self._sesion if "actividad_reciente" in claves else None
        self._fallo = False
        self._runner.run(_cargar, self._mostrar, self._fallo_carga, bool(claves & FUENTES_SERIES),
                         bool(claves & FUENTES_ACTIVIDAD), audit, key="dashboard")

    def _fallo_carga(self, mensaje: str) -> None:
        self._fallo = True
        self.banner.show_error(mensaje)
        for item in self._items:
            if item.definicion.tipo == prefs.GRAFICO:
                self._pintar_grafico(item)

    def _esperando(self, item: prefs.Item) -> bool:
        """El gráfico aún no tiene su dato porque la consulta está en curso."""
        if self._fallo or self._sesion is None:
            return False
        if self._resumen is None:
            return True
        if item.clave in FUENTES_SERIES:
            return self._crudo.get("series") is None
        if item.clave in FUENTES_ACTIVIDAD:
            return self._crudo.get("actividad") is None
        return False

    def card_text(self, clave: str) -> str:
        """El valor de una tarjeta (el final, aunque la cifra aún esté contando)."""
        return self.cards[clave].texto()

    def categorias(self) -> list[tuple[str, float]]:
        """Lo que muestra la gráfica de diferencia: ``[(categoría, diferencia en unidades), …]``."""
        return list(self._categorias)

    def detalle_de(self, clave: str) -> list[tuple[str, str]]:
        """Pares etiqueta/valor que resumen un KPI para el panel lateral."""
        card = self.cards.get(clave)
        if card is None:
            return []
        filas = [(t("Valor"), card.texto())]
        if card.detalle():
            filas.append((t("Desglose"), card.detalle()))
        if self.subtitulo.text():
            filas.append((t("Alcance"), self.subtitulo.text()))
        return filas

    # ------------------------------------------------------------------ personalización (API pública)
    def items(self) -> list[prefs.Item]:
        return list(self._items)

    def item(self, id_: str) -> prefs.Item | None:
        return next((i for i in self._items if i.id == id_), None)

    def set_edicion(self, si: bool) -> None:
        self._edicion = si
        self.rejilla.set_edicion(si)
        self.barra_edicion.setVisible(si)
        self.btn_personalizar.setVisible(not si)

    def en_edicion(self) -> bool:
        return self._edicion

    def agregar_widget(self, clave: str) -> prefs.Item | None:
        d = prefs.POR_CLAVE.get(clave)
        if d is None or not prefs.permitido(d, self._sesion) or (d.unico and any(i.clave == clave for i in self._items)):
            return None
        item = prefs.nuevo(clave)
        self._items.append(item)
        self.rejilla.agregar(self._baldosa(item))
        self._aplicar_datos()
        self._persistir()
        if self._precisa_datos(item):
            self.refresh()
        return item

    def quitar_widget(self, id_: str) -> None:
        item = self.item(id_)
        if item is None:
            return
        self._items.remove(item)
        self.cards.pop(item.clave, None) if item.definicion.tipo == prefs.KPI else None
        self._graficos.pop(id_, None)
        self._marcos.pop(id_, None)
        self.rejilla.quitar(id_)
        self._persistir()

    def cambiar_tam(self, id_: str, tam: str) -> None:
        item = self.item(id_)
        if item is None or tam not in item.definicion.tams or item.tam == tam:
            return
        item.tam = tam
        self.rejilla.cambiar_tam(id_, tam)
        self._persistir()

    def mover_widget(self, id_: str, indice: int) -> None:
        self.rejilla.mover(id_, indice)

    def cambiar_opciones(self, id_: str, **cambios) -> None:
        item = self.item(id_)
        if item is None:
            return
        item.opciones.update(cambios)
        self._pintar_grafico(item)
        self._persistir()
        if "periodo" in cambios:
            self.refresh()

    def duplicar_widget(self, id_: str) -> prefs.Item | None:
        item = self.item(id_)
        if item is None or item.definicion.unico:
            return None
        copia = prefs.Item(item.clave, item.tam, copy.deepcopy(item.opciones))
        self._items.insert(self._items.index(item) + 1, copia)
        self._reconstruir()
        self._persistir()
        return copia

    def restaurar(self) -> bool:
        """Vuelve a la distribución inicial, previa confirmación en la Isla."""
        if self._sesion is None:
            return False
        if not components.Confirmacion.pedir(self, t("Restaurar dashboard predeterminado"),
                                             t("Se perderá la distribución que armaste y volverá la inicial. Tus datos no se tocan."),
                                             t("Restaurar"), peligro=False):
            return False
        self._items = prefs.normalizar(prefs.restaurar(self._sesion.usuario), self._sesion)
        self._reconstruir()
        self.refresh()
        isla.exito(t("Dashboard restaurado"))
        return True

    def datos_de(self, id_: str) -> Datos:
        """Lo que dibuja un gráfico ahora (para pruebas y para la vista previa)."""
        item = self.item(id_)
        return construir(item.clave, item.opciones, self._crudo) if item else Datos()

    # ------------------------------------------------------------------ construcción
    def _precisa_datos(self, item: prefs.Item) -> bool:
        return item.clave in FUENTES_SERIES or item.clave in FUENTES_ACTIVIDAD or item.clave == "actividad_reciente"

    def _reconstruir(self) -> None:
        self.cards.clear()
        self._graficos.clear()
        self._marcos.clear()
        self._etiquetas.clear()
        self.rejilla.poner([self._baldosa(i) for i in self._items])
        self._aplicar_datos()

    def _baldosa(self, item: prefs.Item) -> Baldosa:
        d = item.definicion
        if d.tipo == prefs.KPI:
            color = {"faltantes": self._colores["error"], "con_error": self._colores["error"],
                     "sobrantes": self._colores["aviso"]}.get(d.clave)
            tarjeta = TarjetaKpi(t(d.nombre), color or widgets.VERDE)   # leído ahora: VERDE cambia con el tema
            tarjeta.clicked.connect(lambda c=d.clave: self.detalle.emit(c))
            self.cards[d.clave] = tarjeta
            contenido: QWidget = tarjeta
        elif d.tipo == prefs.PANEL:
            etiqueta = QLabel("")
            etiqueta.setObjectName("subtitulo")
            etiqueta.setWordWrap(True)
            etiqueta.setTextFormat(Qt.TextFormat.PlainText)
            etiqueta.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            self._etiquetas[d.clave] = etiqueta
            marco = _Marco(t(d.nombre), etiqueta)
            self._marcos[item.id] = marco
            contenido = marco
        else:
            grafico = GraficoPersonal()
            grafico.elegido.connect(lambda etiqueta, c=d: self.filtro.emit("categoria", etiqueta) if c.drill else None)
            self._graficos[item.id] = grafico
            marco = _Marco(item.opciones.get("titulo") or t(d.nombre), grafico)
            self._marcos[item.id] = marco
            contenido = marco
        b = Baldosa(item.id, d.tipo, item.tam, contenido)
        b.menu_pedido.connect(self._menu)
        b.quitar.connect(self.quitar_widget)
        return b

    # ------------------------------------------------------------------ datos
    def _mostrar(self, datos) -> None:
        resumen, batch, por_categoria, extra = datos
        if resumen is None:
            self.banner.show_empty(t("Sin datos"))
            return
        self.banner.clear()
        self._cargado = True
        self._resumen, self._batch = resumen, batch
        self._categorias = [(c, float(v)) for c, v in por_categoria]
        self._crudo = {"categorias": self._categorias, "series": extra.get("series"),
                       "actividad": extra.get("actividad"), "auditoria": extra.get("auditoria")}
        self.subtitulo.setText(f"{resumen.skus_totales} {t('SKU')} · {resumen.contados} {t('Contados').lower()}")
        self._aplicar_datos()

    def _valor_kpi(self, clave: str):
        r, b = self._resumen, self._batch
        if clave in ("avance", "contados", "sin_contar", "coincidentes", "faltantes", "sobrantes"):
            if r is None:
                return None
            return {
                "avance": (r.avance_pct, fmt_pct, f"{r.contados} {t('de')} {r.skus_totales} {t('SKU')}"),
                "contados": (r.contados, _fmt_entero, f"{t('SKU contados')}: {r.contados}"),
                "sin_contar": (r.sin_contar, _fmt_entero, f"{r.sin_contar} {t('de')} {r.skus_totales} {t('SKU')}"),
                "coincidentes": (r.ok, _fmt_entero, f"{fmt_pct(r.exactitud_pct)} · {r.ok} {t('de')} {r.contados} {t('Contados').lower()}"),
                "faltantes": (r.faltantes, _fmt_entero, ""),
                "sobrantes": (r.sobrantes, _fmt_entero, ""),
            }[clave]
        if b is None:
            return None
        return {"con_error": (b.errores, _fmt_entero, "")}.get(clave)

    def _aplicar_datos(self) -> None:
        for clave, tarjeta in self.cards.items():
            v = self._valor_kpi(clave)
            if v is None:
                continue
            tarjeta.set_valor(v[0], v[1])
            tarjeta.set_detalle(v[2])
        b = self._batch
        lbl_batch = self._etiquetas.get("batch")
        if b is not None and lbl_batch is not None:
            if b.ultimo_run is None:
                lbl_batch.setText(t("Todavía no se ha procesado ninguna sincronización."))
            else:
                texto = (f"{t('Último procesamiento')}: {b.ultimo_run:%Y-%m-%d %H:%M} UTC · "
                         f"{b.procesados} {t('lecturas procesadas')}")
                if b.errores:
                    texto += f" · {b.errores} {t('con error')}"
                if b.pendientes:
                    texto += f" · {b.pendientes} {t('pendientes')}"
                lbl_batch.setText(texto)
        entradas = self._crudo.get("auditoria")
        lbl_actividad = self._etiquetas.get("actividad_reciente")
        if entradas is not None and lbl_actividad is not None:
            lbl_actividad.setText("\n".join(f"{e.fecha:%d/%m %H:%M} · {e.nombre} · {e.accion}" for e in entradas[:6])
                                       or t("Sin actividad registrada."))
        for item in self._items:
            if item.definicion.tipo == prefs.GRAFICO:
                self._pintar_grafico(item)

    def _pintar_grafico(self, item: prefs.Item) -> None:
        grafico = self._graficos.get(item.id)
        if grafico is None:
            return
        o = item.opciones
        marco = self._marcos.get(item.id)
        if marco is not None:
            marco.poner_titulo(o.get("titulo") or t(item.definicion.nombre))
        grafico.cargando = self._esperando(item)
        grafico.poner(construir(item.clave, o, self._crudo), o.get("tipo", item.definicion.tipo_defecto),
                      bool(o.get("leyenda", True)), bool(o.get("etiquetas", True)), item.definicion.drill)

    # ------------------------------------------------------------------ persistencia y orden
    def _persistir(self) -> None:
        if self._sesion is not None:
            prefs.guardar(self._sesion.usuario, self._items)

    def _orden_cambiado(self, ids: list[str]) -> None:
        por_id = {i.id: i for i in self._items}
        self._items = [por_id[i] for i in ids if i in por_id]
        self._persistir()

    # ------------------------------------------------------------------ menús y paneles
    def _menu(self, id_: str) -> None:
        item = self.item(id_)
        if item is None:
            return
        d = item.definicion
        m = QMenu(self)
        if d.tipo == prefs.GRAFICO:
            m.addAction(t("Configurar gráfico…"), lambda: self._configurar(id_))
            tipos = m.addMenu(t("Cambiar tipo"))
            for tp in d.tipos:
                a = tipos.addAction(t(prefs.NOMBRE_TIPO[tp]), lambda x=tp: self.cambiar_opciones(id_, tipo=x))
                a.setCheckable(True)
                a.setChecked(item.opciones.get("tipo") == tp)
            if d.temporal:
                per = m.addMenu(t("Cambiar período"))
                for p in prefs.PERIODOS:
                    if p == "personalizado":
                        per.addAction(t("Personalizado…"), lambda: self._configurar(id_))
                        continue
                    a = per.addAction(t(prefs.NOMBRE_PERIODO[p]), lambda x=p: self.cambiar_opciones(id_, periodo=x))
                    a.setCheckable(True)
                    a.setChecked(item.opciones.get("periodo") == p)
        tam = m.addMenu(t("Tamaño"))
        for x in d.tams:
            a = tam.addAction(t(prefs.NOMBRE_TAMANO[x]), lambda v=x: self.cambiar_tam(id_, v))
            a.setCheckable(True)
            a.setChecked(item.tam == x)
        if d.tipo == prefs.GRAFICO:
            m.addAction(t("Actualizar información"), self.refresh)
            m.addAction(t("Duplicar gráfico"), lambda: self.duplicar_widget(id_))
        m.addSeparator()
        m.addAction(t("Eliminar del dashboard"), lambda: self.quitar_widget(id_))
        m.exec(QCursor.pos())

    def _hoja(self, clave: str, crear):
        hoja = self._hojas.get(clave)
        if hoja is None:
            hoja = crear(self.window())
            self._hojas[clave] = hoja
            self.destroyed.connect(partial(_borrar, hoja))
        return hoja

    def _abrir_catalogo(self) -> None:
        hoja: CatalogoWidgets = self._hoja("catalogo", CatalogoWidgets)
        try:
            hoja.agregar.disconnect()
        except TypeError:
            pass
        hoja.agregar.connect(self.agregar_widget)
        hoja.abrir_con(self._sesion, [i.clave for i in self._items])

    def _configurar(self, id_: str) -> None:
        item = self.item(id_)
        if item is None:
            return
        hoja: ConfigGrafico = self._hoja("config", lambda v: ConfigGrafico(v, self._proveedor))
        try:
            hoja.cambiado.disconnect()
        except TypeError:
            pass
        hoja.cambiado.connect(self._config_cambiada)
        hoja.abrir_con(item)

    def _proveedor(self, clave: str, opciones: dict) -> Datos:
        return construir(clave, opciones, self._crudo)

    def _config_cambiada(self, id_: str, clave: str, opciones: dict, tam: str) -> None:
        item = self.item(id_)
        if item is None:
            return
        cambia_fuente = clave != item.clave
        item.clave = clave
        item.opciones = opciones
        if tam in item.definicion.tams:
            item.tam = tam
        if cambia_fuente:
            self._reconstruir()
            self.refresh()
        else:
            self.rejilla.cambiar_tam(id_, item.tam)
            self._pintar_grafico(item)
        self._persistir()


def _borrar(hoja: QWidget, *_args) -> None:
    try:
        hoja.deleteLater()
    except RuntimeError:
        pass
