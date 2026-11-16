"""Pantalla «Inventario»: producto a producto, lo contado contra lo que dice el sistema.

Cinco columnas y nada más: SKU, producto, categoría, cantidad contada y cantidad del sistema. El conteo
es ciego para el operador, pero quien mira el escritorio ve ambas cifras. No hay diferencia, porcentaje,
clasificación ni etiquetas; la cantidad contada queda vacía si nadie contó el SKU.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import auth, db
from ..i18n import registrar, t
from ..models import Lectura, fmt_num
from ..tema import colores
from . import widgets
from .base import QueryRunner, StateBanner
from .foto import leer_foto, ver_foto
from .iconos import icono
from .isla import isla

registrar({
    "Buscar por SKU o nombre del producto": "Search by SKU or product name",
    "Exportar CSV": "Export CSV",
    "Exportar inventario": "Export inventory",
    "Inventario físico": "Physical inventory",
    "SKU, producto, categoría, cantidad contada y cantidad del sistema. Haz doble clic para ver las lecturas.":
        "SKU, product, category, counted quantity and system quantity. Double-click to see the readings.",
    "SKU": "SKU",
    "Producto": "Product",
    "Categoría": "Category",
    "Contada": "Counted",
    "Sistema": "System",
    "Ver foto": "View photo",
    "Foto": "Photo",
    "Cantidad": "Quantity",
    "Operador": "Operator",
    "Fecha (UTC)": "Date (UTC)",
    "Vigente": "Current",
    "Nota": "Note",
    "Sí": "Yes",
    "No": "No",
    "Sin lecturas para este SKU": "No readings for this SKU",
    "Lecturas de {sku} — {nombre}": "Readings for {sku} — {nombre}",
    "SKU contados": "SKUs counted",
    "sin contar": "not counted",
    "Filtrado por categoría: {categoria}": "Filtered by category: {categoria}",
    "Doble clic para ver las lecturas del SKU": "Double-click to see the SKU readings",
    "Quitar el filtro de búsqueda": "Clear the search filter",
    "Todavía no hay lecturas": "There are no readings yet",
    "Cuando un teléfono sincronice una lectura de este producto, aparecerá aquí.":
        "When a phone syncs a reading for this product, it will show up here.",
    "Total de lecturas": "Total readings", "Cantidad vigente": "Current quantity", "No vigentes": "Not current",
    "Última lectura": "Latest reading", "{n} lecturas": "{n} readings", "1 lectura": "1 reading",
    "Coincide": "Matches", "Faltante": "Short", "Sobrante": "Over", "Sin contar": "Not counted",
    "Ver fotografía": "View photo", "Ver detalles de la lectura": "View reading details",
    "Consultar nota": "View note", "Nota de la lectura": "Reading note", "Sin foto": "No photo",
    "Detalles de la lectura": "Reading details", "No vigente": "Not current",
    "La foto no se pudo cargar": "The photo could not be loaded",
})

COLUMNAS = ("SKU", "Producto", "Categoría", "Contada", "Sistema")


def estado_producto(fila) -> tuple[str, str]:
    """(texto, estado de la insignia) según lo contado frente al sistema; ``("", "")`` si no hay datos del producto."""
    if fila is None:
        return "", ""
    if fila.cant_contada is None:
        return t("Sin contar"), ""
    if fila.cant_sistema is None or fila.cant_contada == fila.cant_sistema:
        return t("Coincide"), "ACTIVO"
    return (t("Faltante"), "SUSPENDIDO") if fila.cant_contada < fila.cant_sistema else (t("Sobrante"), "PENDIENTE")


class _DelegadoVigente(QStyledItemDelegate):
    """Dibuja «Vigente» como una insignia: verde si cuenta, gris si fue reemplazada. El texto de la celda no cambia."""

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        texto = opt.text
        opt.text = ""
        estilo = opt.widget.style() if opt.widget is not None else QApplication.style()
        estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        vigente = bool(index.data(Qt.ItemDataRole.UserRole))
        c = colores()
        base = QColor(c["acento"] if vigente else c["texto_suave"])
        fondo = QColor(base)
        fondo.setAlpha(38 if vigente else 34)
        fuente = QFont(option.font)
        fuente.setPixelSize(11)
        fuente.setBold(True)
        ancho = QFontMetrics(fuente).horizontalAdvance(texto) + 22
        caja = QRectF(option.rect.left() + 10, option.rect.center().y() - 11, ancho, 22)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fondo)
        painter.drawRoundedRect(caja, 11, 11)
        painter.setPen(base)
        painter.setFont(fuente)
        painter.drawText(caja, int(Qt.AlignmentFlag.AlignCenter), texto)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(96, 40)


class Miniatura(QPushButton):
    """Miniatura de la foto de una lectura: recorte centrado con esquinas redondeadas. Un clic abre el visor."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("miniatura")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mapa = QPixmap()
        self._error = False

    def poner_mapa(self, mapa: QPixmap) -> None:
        self._mapa, self._error = mapa, False
        self.update()

    def poner_error(self) -> None:
        self._mapa, self._error = QPixmap(), True
        self.update()

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        c = colores()
        ancho, alto = 64, 40
        caja = QRectF((self.width() - ancho) / 2, (self.height() - alto) / 2, ancho, alto)
        ruta = QPainterPath()
        ruta.addRoundedRect(caja, 8, 8)
        if self._mapa.isNull():
            p.fillPath(ruta, QColor(c["tarjeta_alt"]))
            nombre = "imagen_no" if self._error else "imagen"
            p.drawPixmap(int(caja.center().x()) - 10, int(caja.center().y()) - 10,
                         icono(nombre, color=c["texto_tenue"], tam=20).pixmap(20, 20))
        else:
            p.setClipPath(ruta)
            escalado = self._mapa.scaled(QSize(ancho, alto), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                         Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(caja.left()) + (ancho - escalado.width()) // 2,
                         int(caja.top()) + (alto - escalado.height()) // 2, escalado)
            p.setClipping(False)
        p.setPen(QColor(c["acento"] if self.underMouse() else c["borde_fuerte"]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(ruta)
        p.end()


class _Mini(QFrame):
    """Indicador compacto: icono discreto, cifra destacada y rótulo."""

    def __init__(self, nombre_icono: str, rotulo: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self._icono = QLabel()
        self._icono.setFixedSize(34, 34)
        self._icono.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icono.setObjectName("miniIcono")
        self._icono.setPixmap(icono(nombre_icono, color=colores()["acento"], tam=18).pixmap(18, 18))
        self.valor = QLabel("—")
        self.valor.setObjectName("miniValor")
        titulo = QLabel(rotulo)
        titulo.setObjectName("cardTitulo")
        textos = QVBoxLayout()
        textos.setSpacing(0)
        textos.addWidget(self.valor)
        textos.addWidget(titulo)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(10)
        lay.addWidget(self._icono)
        lay.addLayout(textos, 1)


class EstadoVacio(QWidget):
    """Sin lecturas: un icono, un mensaje claro y una frase que explica cómo llegan. Sin botones inventados."""

    def __init__(self) -> None:
        super().__init__()
        marca = QLabel()
        marca.setObjectName("vacioIcono")
        marca.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marca.setPixmap(icono("imagen", color=colores()["texto_tenue"], tam=40).pixmap(40, 40))
        titulo = QLabel(t("Todavía no hay lecturas"))
        titulo.setObjectName("vacioTitulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detalle = QLabel(t("Cuando un teléfono sincronice una lectura de este producto, aparecerá aquí."))
        detalle.setObjectName("ayuda")
        detalle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        detalle.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        lay.addWidget(marca)
        lay.addWidget(titulo)
        lay.addWidget(detalle)
        lay.addStretch(1)


class DetalleLecturas(QDialog):
    """Todas las lecturas de un SKU: encabezado con el producto, resumen, tabla y detalle de la lectura elegida.

    La vigente es la más reciente. Las fotos se ven con miniaturas y se abren en el visor (que puede recorrer las
    fotos del SKU). Cerrar el visor devuelve aquí, con la selección y la posición intactas.
    """

    def __init__(self, sku: str, nombre: str, parent: QWidget | None = None, fila=None) -> None:
        super().__init__(parent)
        self._sku, self._nombre, self._fila = sku, nombre, fila
        self._lecturas: list[Lectura] = []
        self._aparecido = False
        self.setWindowTitle(t("Lecturas de {sku} — {nombre}", sku=sku, nombre=nombre))
        self.resize(940, 620)
        self.setMinimumSize(660, 460)
        self._runner = QueryRunner(self)
        self.banner = StateBanner()
        self.banner.retry.connect(lambda: self._cargar(self._sku))

        # ---- encabezado
        self.lbl_nombre = QLabel(nombre)
        self.lbl_nombre.setObjectName("tituloLecturas")
        self.lbl_sku = QLabel(sku)
        self.lbl_sku.setObjectName("chipDato")
        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addWidget(self.lbl_sku)
        categoria = getattr(fila, "categoria", "") if fila is not None else ""
        if categoria:
            lbl_cat = QLabel(categoria)
            lbl_cat.setObjectName("chipDato")
            chips.addWidget(lbl_cat)
        self.lbl_conteo = QLabel("")
        self.lbl_conteo.setObjectName("subtitulo")
        chips.addWidget(self.lbl_conteo)
        chips.addStretch(1)
        textos = QVBoxLayout()
        textos.setSpacing(6)
        textos.addWidget(self.lbl_nombre)
        textos.addLayout(chips)
        self.lbl_estado = QLabel("")
        self.lbl_estado.setObjectName("insignia")
        texto_estado, clave_estado = estado_producto(fila)
        self.lbl_estado.setText(texto_estado)
        self.lbl_estado.setProperty("estado", clave_estado)
        self.lbl_estado.setVisible(bool(texto_estado))
        encabezado = QHBoxLayout()
        encabezado.addLayout(textos, 1)
        encabezado.addWidget(self.lbl_estado, 0, Qt.AlignmentFlag.AlignTop)

        # ---- resumen
        self.mini_total = _Mini("Tareasdeconteo", t("Total de lecturas"))
        self.mini_vigente = _Mini("check", t("Cantidad vigente"))
        self.mini_no_vigentes = _Mini("rotate_ccw", t("No vigentes"))
        self.mini_ultima = _Mini("Movimientos", t("Última lectura"))
        resumen = QHBoxLayout()
        resumen.setSpacing(10)
        for m in (self.mini_total, self.mini_vigente, self.mini_no_vigentes, self.mini_ultima):
            resumen.addWidget(m, 1)

        # ---- tabla
        self.tabla = QTableWidget(0, 6)
        self.tabla.setHorizontalHeaderLabels([t("Cantidad"), t("Operador"), t("Fecha (UTC)"), t("Vigente"),
                                              t("Nota"), t("Foto")])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.setShowGrid(False)
        self.tabla.setAlternatingRowColors(False)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(48)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(False)
        for col, modo in ((0, QHeaderView.ResizeMode.ResizeToContents), (1, QHeaderView.ResizeMode.ResizeToContents),
                          (2, QHeaderView.ResizeMode.ResizeToContents), (3, QHeaderView.ResizeMode.ResizeToContents),
                          (4, QHeaderView.ResizeMode.Stretch), (5, QHeaderView.ResizeMode.Fixed)):
            cabecera.setSectionResizeMode(col, modo)
        self.tabla.setColumnWidth(5, 96)
        self.tabla.setItemDelegateForColumn(3, _DelegadoVigente(self.tabla))
        self.tabla.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu)
        self.tabla.itemSelectionChanged.connect(self._seleccion)
        self.tabla.cellDoubleClicked.connect(lambda fila, _c: self._mostrar_detalle(fila))
        self.vacio = EstadoVacio()
        self.pila = QStackedWidget()
        self.pila.addWidget(self.tabla)
        self.pila.addWidget(self.vacio)

        # ---- detalle de la lectura elegida
        self.panel = QFrame()
        self.panel.setObjectName("card")
        self._rejilla = QGridLayout(self.panel)
        self._rejilla.setContentsMargins(16, 12, 16, 12)
        self._rejilla.setHorizontalSpacing(24)
        self._rejilla.setVerticalSpacing(2)
        self.panel.hide()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(24, 22, 24, 20)
        raiz.setSpacing(14)
        raiz.addLayout(encabezado)
        raiz.addLayout(resumen)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.pila, 1)
        raiz.addWidget(self.panel)
        self._cargar(sku)

    # ------------------------------------------------------------------ datos
    def _cargar(self, sku: str) -> None:
        self.banner.show_loading()
        self._runner.run(db.fetch_lecturas, self._mostrar, self.banner.show_error, sku, key="lecturas")

    def fotos_del_sku(self) -> list[dict]:
        """Las fotos de este SKU con sus metadatos, en el orden de la tabla (el visor navega entre ellas)."""
        return [{"ruta": l.ruta_foto, "producto": self._nombre, "sku": self._sku, "cantidad": fmt_num(l.cantidad),
                 "operador": l.operador or "—", "fecha": l.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                 "estado": t("Vigente") if l.vigente else t("No vigente"), "nota": l.nota or ""}
                for l in self._lecturas if l.ruta_foto]

    def _mostrar(self, lecturas: list[Lectura]) -> None:
        seleccion = self.tabla.currentRow()
        self._lecturas = list(lecturas)
        n = len(lecturas)
        self.lbl_conteo.setText(t("1 lectura") if n == 1 else t("{n} lecturas", n=n))
        vigente = next((l for l in reversed(lecturas) if l.vigente), None)
        self.mini_total.valor.setText(str(n))
        self.mini_vigente.valor.setText(fmt_num(vigente.cantidad) if vigente else "—")
        self.mini_no_vigentes.valor.setText(str(sum(1 for l in lecturas if not l.vigente)))
        self.mini_ultima.valor.setText(max(l.fecha_captura for l in lecturas).strftime("%d/%m/%Y %H:%M") if lecturas else "—")
        if not lecturas:
            self.banner.clear()
            self.banner.registrar(t("Sin lecturas para este SKU"))
            self.tabla.setRowCount(0)
            self.pila.setCurrentWidget(self.vacio)
            return
        self.banner.clear()
        self.pila.setCurrentWidget(self.tabla)
        self.tabla.setRowCount(n)
        tenue = QColor(colores()["texto_suave"])
        for fila, lectura in enumerate(lecturas):
            celdas = (
                fmt_num(lectura.cantidad),
                lectura.operador or "—",
                lectura.fecha_captura.strftime("%Y-%m-%d %H:%M:%S"),
                t("Sí") if lectura.vigente else t("No"),
                lectura.nota or "",
            )
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if columna == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if lectura.vigente:
                        fuente = item.font()
                        fuente.setBold(True)
                        item.setFont(fuente)
                if columna == 3:
                    item.setData(Qt.ItemDataRole.UserRole, lectura.vigente)
                if not lectura.vigente and columna != 3:
                    item.setForeground(QBrush(tenue))
                self.tabla.setItem(fila, columna, item)
            self._celda_foto(fila, lectura)
        if 0 <= seleccion < n:
            self.tabla.selectRow(seleccion)
        self.tabla.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _celda_foto(self, fila: int, lectura: Lectura) -> None:
        if not lectura.ruta_foto:
            sin = QTableWidgetItem(t("Sin foto"))
            sin.setForeground(QBrush(QColor(colores()["texto_tenue"])))
            self.tabla.setItem(fila, 5, sin)
            return
        boton = Miniatura()
        boton.setToolTip(t("Ver foto"))
        boton.clicked.connect(lambda _c=False, ruta=lectura.ruta_foto: self._abrir_foto(ruta))
        self.tabla.setCellWidget(fila, 5, boton)
        self._runner.run(leer_foto, lambda datos, b=boton: self._miniatura(b, datos),
                         lambda mensaje, b=boton: self._miniatura_falla(b, mensaje), lectura.ruta_foto,
                         key=f"miniatura-{fila}")

    def _miniatura(self, boton: "Miniatura", datos: bytes) -> None:
        mapa = QPixmap()
        if not mapa.loadFromData(datos):
            self._miniatura_falla(boton, t("El archivo no es una imagen válida."))
            return
        boton.poner_mapa(mapa)

    def _miniatura_falla(self, boton: "Miniatura", mensaje: str) -> None:
        boton.poner_error()
        boton.setToolTip(f"{t('La foto no se pudo cargar')}: {mensaje}")

    def _abrir_foto(self, ruta: str) -> None:
        ver_foto(self, ruta, f"{self._sku} · {self._nombre}")

    # ------------------------------------------------------------------ selección, detalle y menú contextual
    def _seleccion(self) -> None:
        fila = self.tabla.currentRow()
        if 0 <= fila < len(self._lecturas) and self.tabla.selectedItems():
            self._mostrar_detalle(fila)
        else:
            self.panel.hide()

    def _mostrar_detalle(self, fila: int) -> None:
        if not 0 <= fila < len(self._lecturas):
            return
        l = self._lecturas[fila]
        while self._rejilla.count():
            item = self._rejilla.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        datos = ((t("Cantidad"), fmt_num(l.cantidad)), (t("Operador"), l.operador or "—"),
                 (t("Fecha (UTC)"), l.fecha_captura.strftime("%Y-%m-%d %H:%M:%S")),
                 (t("Estado"), t("Vigente") if l.vigente else t("No vigente")), (t("Nota"), l.nota or "—"))
        for columna, (etiqueta, valor) in enumerate(datos):
            e = QLabel(etiqueta)
            e.setObjectName("cardTitulo")
            v = QLabel(valor)
            v.setObjectName("datoLectura")
            v.setWordWrap(True)
            self._rejilla.addWidget(e, 0, columna)
            self._rejilla.addWidget(v, 1, columna)
        self._rejilla.setColumnStretch(4, 2)
        self.panel.show()

    def _menu(self, pos) -> None:
        fila = self.tabla.rowAt(pos.y())
        if not 0 <= fila < len(self._lecturas):
            return
        self.tabla.selectRow(fila)
        l = self._lecturas[fila]
        menu = QMenu(self)
        ver = menu.addAction(t("Ver fotografía"), lambda: self._abrir_foto(l.ruta_foto))
        ver.setEnabled(bool(l.ruta_foto))
        menu.addAction(t("Ver detalles de la lectura"), lambda: self._mostrar_detalle(fila))
        nota = menu.addAction(t("Consultar nota"), lambda: isla.info(t("Nota de la lectura"), l.nota or ""))
        nota.setEnabled(bool(l.nota))
        menu.exec(self.tabla.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ apertura suave
    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        if not self._aparecido:
            self._aparecido = True
            if widgets.ANIMAR:
                self.setWindowOpacity(0.0)
                widgets.animar(self, 0.0, 1.0, 180, self.setWindowOpacity)


def _cargar(texto: str):
    return db.fetch_conciliacion(texto=texto or None)


class InventarioView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._cargado = False
        self._filas: list = []
        self.detalle: DetalleLecturas | None = None

        ayuda = QLabel(t("SKU, producto, categoría, cantidad contada y cantidad del sistema. "
                         "Haz doble clic para ver las lecturas."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText(t("Buscar por SKU o nombre del producto"))
        self.txt_buscar.setClearButtonEnabled(True)
        self.btn_exportar = QPushButton(t("Exportar CSV"))
        barra = QHBoxLayout()
        barra.addWidget(self.txt_buscar, 1)
        barra.addWidget(self.btn_exportar)

        self.tabla = QTableWidget(0, len(COLUMNAS))
        self.tabla.setHorizontalHeaderLabels([t(c) for c in COLUMNAS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        cabecera = self.tabla.horizontalHeader()
        cabecera.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for columna in (0, 2, 3, 4):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeMode.ResizeToContents)
        self.tabla.setToolTip(t("Doble clic para ver las lecturas del SKU"))
        self.lbl_resumen = QLabel("")
        self.lbl_resumen.setObjectName("resumen")

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(10)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addLayout(barra)
        raiz.addWidget(self.tabla, 1)
        raiz.addWidget(self.lbl_resumen)

        self._retardo = QTimer(self)
        self._retardo.setSingleShot(True)
        self._retardo.setInterval(250)
        self.txt_buscar.textChanged.connect(lambda _: self._retardo.start())
        self._retardo.timeout.connect(self.refresh)
        self.btn_exportar.clicked.connect(self._elegir_archivo)
        self.tabla.doubleClicked.connect(self._doble_clic)

    # ------------------------------------------------------------------ API
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._filas = []
            self.tabla.setRowCount(0)
            self.banner.show_empty(t("Sin datos"))
        else:
            self.refresh()

    def refresh(self) -> None:
        if self._sesion is None:
            return
        if not self._cargado:
            self.banner.show_loading()
        self._runner.run(_cargar, self._mostrar, self.banner.show_error,
                         self.txt_buscar.text().strip(), key="inventario")

    def buscar(self, texto: str) -> None:
        self.txt_buscar.setText(texto)
        self.txt_buscar.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.refresh()

    def limpiar_filtros(self) -> None:
        self.txt_buscar.clear()
        self.refresh()

    def filas(self) -> list[tuple[str, ...]]:
        """Las filas visibles, para las pruebas."""
        return [tuple(self.tabla.item(f, c).text() if self.tabla.item(f, c) else "" for c in range(len(COLUMNAS)))
                for f in range(self.tabla.rowCount())]

    def abrir_detalle(self, sku: str) -> None:
        fila = next((f for f in self._filas if f.sku == sku), None)
        if fila is None:
            return
        self.detalle = DetalleLecturas(sku, fila.nombre, self, fila)
        self.detalle.show()

    def exportar_csv(self, ruta: str | Path) -> None:
        """Las filas que se están viendo, con separador «;» y BOM: abre bien en Excel."""
        with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.writer(fh, delimiter=";")
            escritor.writerow(COLUMNAS)
            for fila in self._filas:
                escritor.writerow([fila.sku, fila.nombre, fila.categoria,
                                   "" if fila.cant_contada is None else fmt_num(fila.cant_contada),
                                   "" if fila.cant_sistema is None else fmt_num(fila.cant_sistema)])

    def acciones_paleta(self):
        from .paleta import Atajo

        return [
            Atajo("inventario:exportar", t("Exportar inventario"), t("Inventario"), "", self._elegir_archivo),
            Atajo("inventario:limpiar", t("Quitar el filtro de búsqueda"), t("Inventario"), "", self.limpiar_filtros),
        ]

    # ------------------------------------------------------------- internos
    def _mostrar(self, filas) -> None:
        self._cargado = True
        self._filas = list(filas)
        self.tabla.setRowCount(len(self._filas))
        contados = sum(1 for f in self._filas if f.cant_contada is not None)
        for numero, fila in enumerate(self._filas):
            celdas = (fila.sku, fila.nombre, fila.categoria,
                      "" if fila.cant_contada is None else fmt_num(fila.cant_contada),
                      "" if fila.cant_sistema is None else fmt_num(fila.cant_sistema))
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if columna >= 3:
                    item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                if columna == 3 and fila.cant_contada is None:
                    item.setForeground(QBrush(QColor(colores()["texto_suave"])))
                self.tabla.setItem(numero, columna, item)
        self.lbl_resumen.setText(
            f"{len(self._filas)} {t('SKU')} · {contados} {t('SKU contados').lower()} · "
            f"{len(self._filas) - contados} {t('sin contar')}")
        if self._filas:
            self.banner.clear()
        else:
            self.banner.show_empty(t("Sin datos"))

    def _doble_clic(self, indice) -> None:
        if indice.isValid() and 0 <= indice.row() < len(self._filas):
            self.abrir_detalle(self._filas[indice.row()].sku)

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, t("Exportar inventario"), "inventario.csv", "CSV (*.csv)")
        if ruta:
            self.exportar_csv(ruta)
