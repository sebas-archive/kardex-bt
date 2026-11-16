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
    QDialog,
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

from .. import auth, db, isla
from ..i18n import registrar, t
from ..models import Lectura, fmt_num
from ..tema import colores
from .base import QueryRunner, StateBanner
from .capas import abrir_capa
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
})

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
            try:
                self.exportar_csv(ruta)
            except OSError as exc:
                isla.error("No se pudo exportar", str(exc))
                return
            isla.exito("Inventario exportado", Path(ruta).name)
