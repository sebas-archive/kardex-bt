"""Pantalla «Diferencias»: los faltantes y sobrantes de los conteos, con la observación del operador. Inventario
las marca revisadas o pide un recuento; el Administrador las consulta.

Los ajustes de existencias llegan en una fase siguiente: aquí todavía no se corrige ninguna cantidad.
"""

from __future__ import annotations

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth, tareas
from .base import QueryRunner, StateBanner
from .maestros import pedir_texto
from .tareas import _numero

ENCABEZADOS = ("Tarea", "Producto", "Almacén", "Sistema", "Contado", "Dif.", "Tipo", "Observación", "Estado")
COLOR_TIPO = {"FALTANTE": "#F87171", "SOBRANTE": "#FBBF24"}

__all__ = ["DiferenciasView", "pedir_texto"]


def _diferencia(valor: float) -> str:
    return ("+" if valor > 0 else "") + _numero(valor)


class DiferenciasView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[tareas.Diferencia] = []
        self._vistas: list[tareas.Diferencia] = []

        ayuda = QLabel("Productos cuya cantidad contada no coincide con la del sistema. «Pedir recuento» devuelve el "
                       "producto a la tarea del operador; una lectura nueva vuelve a dejar la diferencia pendiente.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        self.combo_tarea, self.combo_tipo, self.combo_estado = QComboBox(), QComboBox(), QComboBox()
        self.combo_tarea.addItem("Todas las tareas", None)
        self.combo_tipo.addItem("Faltantes y sobrantes", None)
        for tipo, texto in tareas.NOMBRE_TIPO.items():
            self.combo_tipo.addItem(texto, tipo)
        for estado, texto in (("PENDIENTE", "Pendientes"), ("REVISADA", "Revisadas"), ("RECUENTO", "Recuento pedido"),
                              (None, "Todos los estados")):
            self.combo_estado.addItem(texto, estado)
        self.btn_revisada = QPushButton("Marcar revisada…")
        self.btn_recuento = QPushButton("Pedir recuento")
        barra = QHBoxLayout()
        barra.addWidget(self.btn_revisada)
        barra.addWidget(self.btn_recuento)
        barra.addStretch(1)
        for combo in (self.combo_tarea, self.combo_tipo, self.combo_estado):
            barra.addWidget(combo)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(list(ENCABEZADOS))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        self.tabla.horizontalHeader().setStretchLastSection(True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.lbl_error)
        raiz.addLayout(barra)
        raiz.addWidget(self.tabla, 1)

        self.tabla.itemSelectionChanged.connect(self._ajustar)
        for combo in (self.combo_tarea, self.combo_tipo, self.combo_estado):
            combo.currentIndexChanged.connect(self._filtrar)
        self.btn_revisada.clicked.connect(self._revisada)
        self.btn_recuento.clicked.connect(self._recuento)
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
            self._error_accion("")
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """Muestra las diferencias de todos los conteos; se filtran con «Tarea»."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("diferencias"):
            return
        self._runner.run(tareas.listar_diferencias, self._mostrar, self.banner.show_error, key="diferencias")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    def seleccionar(self, id_conteo: str, sku: str) -> None:
        for fila, d in enumerate(self._vistas):
            if (d.id_conteo, d.sku) == (id_conteo, sku):
                self.tabla.selectRow(fila)

    # ------------------------------------------------------------- internos
    def _gestiona(self) -> bool:
        return self._sesion is not None and self._sesion.puede("diferencias", "GESTION")

    def _elegida(self) -> tareas.Diferencia | None:
        fila = self.tabla.currentRow()
        return self._vistas[fila] if 0 <= fila < len(self._vistas) and self.tabla.selectedItems() else None

    def _mostrar(self, datos: list[tareas.Diferencia]) -> None:
        self._todas = list(datos)
        actual = self.combo_tarea.currentData()
        self.combo_tarea.blockSignals(True)
        while self.combo_tarea.count() > 1:
            self.combo_tarea.removeItem(1)
        for id_conteo in dict.fromkeys(d.id_conteo for d in self._todas):
            self.combo_tarea.addItem(id_conteo, id_conteo)
        self.combo_tarea.setCurrentIndex(max(0, self.combo_tarea.findData(actual)) if actual else 0)
        self.combo_tarea.blockSignals(False)
        self._filtrar()

    def _filtrar(self) -> None:
        elegida = self._elegida()
        tarea, tipo, estado = self.combo_tarea.currentData(), self.combo_tipo.currentData(), self.combo_estado.currentData()
        self._vistas = [d for d in self._todas if (tarea is None or d.id_conteo == tarea)
                        and (tipo is None or d.tipo == tipo) and (estado is None or d.estado == estado)]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self._vistas))
        for fila, d in enumerate(self._vistas):
            celdas = (d.id_conteo, d.producto, d.almacen, _numero(d.sistema), _numero(d.contado), _diferencia(d.diferencia),
                      tareas.NOMBRE_TIPO[d.tipo], d.observacion, tareas.NOMBRE_REVISION[d.estado])
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if columna == 6:
                    item.setForeground(QBrush(QColor(COLOR_TIPO[d.tipo])))
                if d.estado == tareas.REVISADA:
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.clearSelection()
        self.tabla.blockSignals(False)
        if elegida is not None:
            self.seleccionar(elegida.id_conteo, elegida.sku)
        if not self._todas:
            self.banner.show_empty("No hay diferencias: lo contado coincide con el sistema.")
        elif not self._vistas:
            self.banner.show_empty("Ninguna diferencia coincide con los filtros.")
        else:
            self.banner.clear()
        self._ajustar()

    def _ajustar(self) -> None:
        gestiona, d = self._gestiona(), self._elegida()
        for boton in (self.btn_revisada, self.btn_recuento):
            boton.setVisible(gestiona)
            boton.setEnabled(d is not None)

    def _revisada(self) -> None:
        d = self._elegida()
        if d is None:
            return
        nota = pedir_texto(self, "Marcar revisada", f"{d.producto} ({d.id_conteo}). Nota (opcional):")
        if nota is not None:
            self._accion(tareas.marcar_revisada, d.id_conteo, d.sku, nota)

    def _recuento(self) -> None:
        d = self._elegida()
        if d is not None:
            self._accion(tareas.pedir_recuento, d.id_conteo, d.sku)

    def _accion(self, operacion, *args) -> None:
        self._runner.run(operacion, self._accion_lista, self._error_accion, self._sesion, *args)

    def _accion_lista(self, _resultado) -> None:
        self._error_accion("")
        self.refresh()

    def _error_accion(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
