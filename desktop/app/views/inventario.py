"""Pantalla «Inventario»: producto a producto, lo contado contra lo que dice el sistema.

Cinco columnas y nada más: SKU, producto, categoría, cantidad contada y cantidad del sistema. El conteo
es ciego para el operador, pero quien mira el escritorio ve ambas cifras. No hay diferencia, porcentaje,
clasificación ni etiquetas; la cantidad contada queda vacía si nadie contó el SKU.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import auth, db
from ..i18n import registrar, t
from ..models import Lectura, fmt_num
from ..tema import colores
from .base import QueryRunner, StateBanner
from .capas import abrir_capa
from .isla import isla
from .lecturas import DetalleLecturas

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
    "Filtros": "Filters",
    "Limpiar filtros": "Clear filters",
    "Todas": "All",
    "Todos": "All",
    "Estado": "Status",
    "Sin contar": "Not counted",
    "Contados": "Counted",
    "Cuadran": "Match",
    "No cuadran": "Do not match",
    "mín": "min",
    "máx": "max",
    "Orden": "Sort by",
    "Ascendente": "Ascending",
    "Descendente": "Descending",
    "Cantidad contada": "Counted quantity",
    "Cantidad del sistema": "System quantity",
    "Quitar este filtro": "Remove this filter",
    "de": "of",
})

ESTADOS = (("todos", "Todos"), ("sin_contar", "Sin contar"), ("contados", "Contados"),
           ("cuadran", "Cuadran"), ("no_cuadran", "No cuadran"))
ORDENES = (("sku", "SKU"), ("nombre", "Producto"), ("categoria", "Categoría"),
           ("contada", "Cantidad contada"), ("sistema", "Cantidad del sistema"))


def _numero(texto: str) -> float | None:
    """«12», «12,5» o «12.5» → número; vacío o inválido → None (el límite no se aplica)."""
    try:
        return float(texto.strip().replace(",", "."))
    except ValueError:
        return None


def _estado_ok(fila, estado: str) -> bool:
    contada = fila.cant_contada
    if estado == "sin_contar":
        return contada is None
    if estado == "contados":
        return contada is not None
    if estado == "cuadran":
        return contada is not None and contada == (fila.cant_sistema or 0)
    if estado == "no_cuadran":
        return contada is not None and contada != (fila.cant_sistema or 0)
    return True


def _en_rango(valor, minimo, maximo) -> bool:
    if minimo is None and maximo is None:
        return True
    if valor is None:
        return False
    return (minimo is None or valor >= minimo) and (maximo is None or valor <= maximo)

COLUMNAS = ("SKU", "Producto", "Categoría", "Contada", "Sistema")


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
        self._capa_detalle = None

        ayuda = QLabel(t("SKU, producto, categoría, cantidad contada y cantidad del sistema. "
                         "Haz doble clic para ver las lecturas."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText(t("Buscar por SKU o nombre del producto"))
        self.txt_buscar.setClearButtonEnabled(True)
        self.btn_filtros = QPushButton()
        self.btn_filtros.setCheckable(True)
        self.btn_exportar = QPushButton(t("Exportar CSV"))
        barra = QHBoxLayout()
        barra.addWidget(self.txt_buscar, 1)
        barra.addWidget(self.btn_filtros)
        barra.addWidget(self.btn_exportar)

        self._todas: list = []
        self.panel_filtros = self._construir_panel_filtros()
        self.fila_chips = QHBoxLayout()
        self.fila_chips.setSpacing(6)
        self.fila_chips.setContentsMargins(0, 0, 0, 0)
        self.zona_chips = QWidget()
        self.zona_chips.setLayout(self.fila_chips)
        self.zona_chips.hide()

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
        raiz.addWidget(self.panel_filtros)
        raiz.addWidget(self.zona_chips)
        raiz.addWidget(self.tabla, 1)
        raiz.addWidget(self.lbl_resumen)

        self._retardo = QTimer(self)
        self._retardo.setSingleShot(True)
        self._retardo.setInterval(250)
        self.txt_buscar.textChanged.connect(lambda _: self._retardo.start())
        self._retardo.timeout.connect(self.refresh)
        self.btn_exportar.clicked.connect(self._elegir_archivo)
        self.btn_filtros.toggled.connect(self.panel_filtros.setVisible)
        self._actualizar_boton()
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
        self._restablecer_panel()
        self.txt_buscar.blockSignals(True)
        self.txt_buscar.clear()
        self.txt_buscar.blockSignals(False)
        self.refresh()
        self._reaplicar()

    def aplicar_filtro(self, categoria: str | None = None, estado: str | None = None) -> None:
        """Fija filtros desde fuera (p. ej. un clic en una gráfica); el resto se queda como estaba."""
        if categoria is not None:
            self._poner_categoria(categoria)
        if estado is not None:
            i = self.cmb_estado.findData(estado)
            if i >= 0:
                self.cmb_estado.setCurrentIndex(i)
        self._reaplicar()

    def filas(self) -> list[tuple[str, ...]]:
        """Las filas visibles, para las pruebas."""
        return [tuple(self.tabla.item(f, c).text() if self.tabla.item(f, c) else "" for c in range(len(COLUMNAS)))
                for f in range(self.tabla.rowCount())]

    def abrir_detalle(self, sku: str) -> None:
        fila = next((f for f in self._filas if f.sku == sku), None)
        if fila is None:
            return
        if self._capa_detalle is not None and self._capa_detalle.esta_abierta():
            self._capa_detalle.cerrar()
        panel = DetalleLecturas(sku, fila.nombre, None, categoria=fila.categoria,
                                contada=fila.cant_contada, sistema=fila.cant_sistema)
        self.detalle = panel
        ventana = self.window()
        if ventana is self:        # la vista sola (sin ventana principal): el panel queda suelto
            panel.show()
            return
        # Un panel flotante dentro de la ventana principal, centrado en el área de contenido y sobre la tabla.
        self._capa_detalle = abrir_capa(ventana, panel, area="contenido", oscuridad=0.30, radio=18)
        self._capa_detalle.cerrada.connect(self._detalle_cerrado)

    def _detalle_cerrado(self) -> None:
        self.detalle = None
        self._capa_detalle = None

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
        self._todas = list(filas)
        self._rellenar_categorias()
        self._reaplicar()

    def _pintar(self) -> None:
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
        total = (f"{len(self._filas)} {t('de')} {len(self._todas)}"
                 if len(self._filas) != len(self._todas) else f"{len(self._filas)}")
        self.lbl_resumen.setText(
            f"{total} {t('SKU')} · {contados} {t('SKU contados').lower()} · "
            f"{len(self._filas) - contados} {t('sin contar')}")
        if self._filas:
            self.banner.clear()
        else:
            self.banner.show_empty(t("Sin datos"))

    # ------------------------------------------------------- panel de filtros
    def _construir_panel_filtros(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panelFiltros")
        panel.setStyleSheet("QFrame#panelFiltros { border: 1px solid rgba(128,128,128,0.35); border-radius: 10px; }")
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItem(t("Todas"), "")
        self.cmb_estado = QComboBox()
        for clave, nombre in ESTADOS:
            self.cmb_estado.addItem(t(nombre), clave)
        self.cmb_orden = QComboBox()
        for clave, nombre in ORDENES:
            self.cmb_orden.addItem(t(nombre), clave)
        self.cmb_sentido = QComboBox()
        self.cmb_sentido.addItem("↑ " + t("Ascendente"), False)
        self.cmb_sentido.addItem("↓ " + t("Descendente"), True)
        self.txt_contada_min, self.txt_contada_max = QLineEdit(), QLineEdit()
        self.txt_sistema_min, self.txt_sistema_max = QLineEdit(), QLineEdit()
        self._retardo_filtros = QTimer(self)
        self._retardo_filtros.setSingleShot(True)
        self._retardo_filtros.setInterval(200)
        self._retardo_filtros.timeout.connect(self._reaplicar)
        for campo, texto in ((self.txt_contada_min, "mín"), (self.txt_contada_max, "máx"),
                             (self.txt_sistema_min, "mín"), (self.txt_sistema_max, "máx")):
            campo.setPlaceholderText(t(texto))
            campo.setMaximumWidth(90)
            campo.textChanged.connect(lambda _: self._retardo_filtros.start())
        for combo in (self.cmb_categoria, self.cmb_estado, self.cmb_orden, self.cmb_sentido):
            combo.currentIndexChanged.connect(lambda _: self._reaplicar())
        self.btn_limpiar = QPushButton(t("Limpiar filtros"))
        self.btn_limpiar.clicked.connect(self.limpiar_filtros)

        def fila(*piezas) -> QHBoxLayout:
            caja = QHBoxLayout()
            for pieza in piezas:
                caja.addWidget(QLabel(pieza) if isinstance(pieza, str) else pieza)
            caja.addStretch(1)
            return caja

        disposicion = QVBoxLayout(panel)
        disposicion.setContentsMargins(12, 10, 12, 10)
        disposicion.setSpacing(8)
        disposicion.addLayout(fila(t("Categoría"), self.cmb_categoria, t("Estado"), self.cmb_estado))
        disposicion.addLayout(fila(t("Contada"), self.txt_contada_min, "–", self.txt_contada_max,
                                   t("Sistema"), self.txt_sistema_min, "–", self.txt_sistema_max))
        disposicion.addLayout(fila(t("Orden"), self.cmb_orden, self.cmb_sentido, self.btn_limpiar))
        panel.hide()
        return panel

    def _poner_categoria(self, categoria: str) -> None:
        i = self.cmb_categoria.findData(categoria)
        if i < 0:
            self.cmb_categoria.addItem(categoria, categoria)
            i = self.cmb_categoria.count() - 1
        self.cmb_categoria.setCurrentIndex(i)

    def _rellenar_categorias(self) -> None:
        actual = self.cmb_categoria.currentData() or ""
        nombres = sorted({f.categoria for f in self._todas if f.categoria} | ({actual} if actual else set()))
        self.cmb_categoria.blockSignals(True)
        self.cmb_categoria.clear()
        self.cmb_categoria.addItem(t("Todas"), "")
        for nombre in nombres:
            self.cmb_categoria.addItem(nombre, nombre)
        self.cmb_categoria.setCurrentIndex(max(0, self.cmb_categoria.findData(actual)))
        self.cmb_categoria.blockSignals(False)

    def _restablecer_panel(self) -> None:
        for combo in (self.cmb_categoria, self.cmb_estado, self.cmb_orden, self.cmb_sentido):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        for campo in (self.txt_contada_min, self.txt_contada_max, self.txt_sistema_min, self.txt_sistema_max):
            campo.blockSignals(True)
            campo.clear()
            campo.blockSignals(False)

    def _filtros_activos(self) -> list[tuple[str, object]]:
        """(texto del chip, acción que lo quita) de cada filtro del panel que no está en su valor por defecto."""
        activos = []
        if self.cmb_categoria.currentData():
            activos.append((f"{t('Categoría')}: {self.cmb_categoria.currentData()}",
                            lambda: self.cmb_categoria.setCurrentIndex(0)))
        if self.cmb_estado.currentData() != "todos":
            activos.append((self.cmb_estado.currentText(), lambda: self.cmb_estado.setCurrentIndex(0)))
        for etiqueta, bajo, alto in (("Contada", self.txt_contada_min, self.txt_contada_max),
                                     ("Sistema", self.txt_sistema_min, self.txt_sistema_max)):
            minimo, maximo = _numero(bajo.text()), _numero(alto.text())
            if minimo is None and maximo is None:
                continue
            rango = (f"≥ {fmt_num(minimo)}" if maximo is None else f"≤ {fmt_num(maximo)}" if minimo is None
                     else f"{fmt_num(minimo)} – {fmt_num(maximo)}")
            activos.append((f"{t(etiqueta)}: {rango}", lambda b=bajo, a=alto: (b.clear(), a.clear())))
        if self.cmb_orden.currentIndex() != 0 or self.cmb_sentido.currentIndex() != 0:
            activos.append((f"{t('Orden')}: {self.cmb_orden.currentText()} "
                            f"{'↓' if self.cmb_sentido.currentData() else '↑'}",
                            lambda: (self.cmb_orden.setCurrentIndex(0), self.cmb_sentido.setCurrentIndex(0))))
        return activos

    def _reaplicar(self) -> None:
        categoria = self.cmb_categoria.currentData() or ""
        estado = self.cmb_estado.currentData()
        c_min, c_max = _numero(self.txt_contada_min.text()), _numero(self.txt_contada_max.text())
        s_min, s_max = _numero(self.txt_sistema_min.text()), _numero(self.txt_sistema_max.text())
        filas = [f for f in self._todas
                 if (not categoria or f.categoria == categoria) and _estado_ok(f, estado)
                 and _en_rango(f.cant_contada, c_min, c_max) and _en_rango(f.cant_sistema, s_min, s_max)]
        getter = {"sku": lambda f: f.sku.upper(), "nombre": lambda f: f.nombre.upper(),
                  "categoria": lambda f: (f.categoria or "").upper(),
                  "contada": lambda f: f.cant_contada, "sistema": lambda f: f.cant_sistema}[self.cmb_orden.currentData()]
        con = [f for f in filas if getter(f) is not None]
        sin = [f for f in filas if getter(f) is None]          # sin dato: siempre al final
        con.sort(key=getter, reverse=bool(self.cmb_sentido.currentData()))
        self._filas = con + sin
        self._pintar()
        self._actualizar_chips()
        self._actualizar_boton()

    def _actualizar_boton(self) -> None:
        n = len(self._filtros_activos())
        self.btn_filtros.setText(f"{t('Filtros')} · {n}" if n else t("Filtros"))

    def _actualizar_chips(self) -> None:
        while self.fila_chips.count():
            item = self.fila_chips.takeAt(0)
            viejo = item.widget()
            if viejo is not None:
                viejo.setParent(None)
                viejo.deleteLater()
        activos = self._filtros_activos()
        for texto, quitar in activos:
            chip = QPushButton(f"{texto}  ✕")
            chip.setFlat(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(t("Quitar este filtro"))
            chip.clicked.connect(lambda _=False, q=quitar: q())
            self.fila_chips.addWidget(chip)
        self.fila_chips.addStretch(1)
        self.zona_chips.setVisible(bool(activos))

    def _doble_clic(self, indice) -> None:
        if indice.isValid() and 0 <= indice.row() < len(self._filas):
            self.abrir_detalle(self._filas[indice.row()].sku)

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(self, t("Exportar inventario"), "inventario.csv", "CSV (*.csv)")
        if ruta:
            try:
                self.exportar_csv(ruta)
            except OSError as exc:
                isla.error("No se pudo exportar", str(exc))
                return
            isla.exito("Inventario exportado", Path(ruta).name)
