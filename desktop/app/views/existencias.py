"""Pantalla «Existencias»: cuánto hay de cada producto en cada almacén, con búsqueda y filtros (solo consulta)."""

from __future__ import annotations

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from .. import auth, maestros
from .base import QueryRunner, StateBanner

ENCABEZADOS = ("Código", "Producto", "Categoría", "Almacén", "Cantidad", "Estado")
COLOR_ESTADO = {maestros.AGOTADO: "#F87171", maestros.STOCK_BAJO: "#FBBF24"}


def _cantidad(valor: float) -> str:
    return f"{valor:,.3f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")


def _almacen(e: maestros.Existencia) -> str:
    return e.almacen if e.almacen_activo else f"{e.almacen} (inactivo)"


def _categoria(e: maestros.Existencia) -> str:
    return e.categoria if e.categoria_activa else f"{e.categoria} (inactiva)"


class ExistenciasView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[maestros.Existencia] = []
        self._vistas: list[maestros.Existencia] = []

        ayuda = QLabel("Cantidad actual de cada producto en cada almacén. «Stock bajo»: por debajo del mínimo del producto.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar por código o producto")
        self.combo_almacen, self.combo_categoria, self.combo_estado = QComboBox(), QComboBox(), QComboBox()
        self.combo_almacen.addItem("Todos los almacenes", None)
        self.combo_categoria.addItem("Todas las categorías", None)
        self.combo_estado.addItem("Todos los estados", None)
        for estado, texto in maestros.NOMBRE_ESTADO.items():
            self.combo_estado.addItem(texto, estado)
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        for combo in (self.combo_almacen, self.combo_categoria, self.combo_estado):
            filtros.addWidget(combo)
        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(list(ENCABEZADOS))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        self.tabla.horizontalHeader().setStretchLastSection(True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addLayout(filtros)
        raiz.addWidget(self.tabla, 1)

        self.txt_buscar.textChanged.connect(self._filtrar)
        for combo in (self.combo_almacen, self.combo_categoria, self.combo_estado):
            combo.currentIndexChanged.connect(self._filtrar)

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """Las existencias no dependen del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("existencias"):
            return
        self._runner.run(maestros.listar_existencias, self._mostrar, self.banner.show_error, key="existencias")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    # ------------------------------------------------------------- internos
    @staticmethod
    def _rellenar(combo: QComboBox, valores: list[tuple[str, str]]) -> None:
        """Opciones de un filtro según los datos, conservando la elegida."""
        actual = combo.currentData()
        combo.blockSignals(True)
        while combo.count() > 1:
            combo.removeItem(1)
        for dato, texto in valores:
            combo.addItem(texto, dato)
        indice = combo.findData(actual) if actual is not None else 0
        combo.setCurrentIndex(max(0, indice))
        combo.blockSignals(False)

    def _mostrar(self, existencias: list[maestros.Existencia]) -> None:
        self._todas = list(existencias)
        self._rellenar(self.combo_almacen, sorted({(e.codigo_almacen, _almacen(e)) for e in existencias}))
        self._rellenar(self.combo_categoria, sorted({(e.categoria, _categoria(e)) for e in existencias}))
        self._filtrar()

    def _filtrar(self) -> None:
        texto = self.txt_buscar.text().strip().lower()
        almacen, categoria, estado = self.combo_almacen.currentData(), self.combo_categoria.currentData(), self.combo_estado.currentData()
        self._vistas = [e for e in self._todas
                        if (almacen is None or e.codigo_almacen == almacen) and (categoria is None or e.categoria == categoria)
                        and (estado is None or e.estado == estado)
                        and (not texto or texto in e.sku.lower() or texto in e.producto.lower())]
        self.tabla.setRowCount(len(self._vistas))
        for fila, e in enumerate(self._vistas):
            celdas = (e.sku, e.producto, _categoria(e), _almacen(e), _cantidad(e.cantidad), maestros.NOMBRE_ESTADO[e.estado])
            for columna, valor in enumerate(celdas):
                item = QTableWidgetItem(valor)
                if columna == 5 and e.estado in COLOR_ESTADO:
                    item.setForeground(QBrush(QColor(COLOR_ESTADO[e.estado])))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        if not self._vistas:
            self.banner.show_empty("Ningún producto coincide con los filtros" if self._todas else "Sin existencias registradas")
        else:
            self.banner.clear()
