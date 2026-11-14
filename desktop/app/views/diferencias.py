"""Pantalla «Diferencias»: los faltantes y sobrantes de los conteos, con la observación del operador. Inventario
las marca revisadas o pide un recuento; el Administrador las consulta.

Los ajustes de existencias llegan en una fase siguiente: aquí todavía no se corrige ninguna cantidad.
"""

from __future__ import annotations

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth, movimientos, tareas
from .ajustes import pedir_ajuste, resultado
from .base import QueryRunner, StateBanner
from .foto import ver_foto
from .maestros import pedir_texto
from .tareas import _numero

ENCABEZADOS = ("Tarea", "Producto", "Almacén", "Sistema", "Contado", "Dif.", "Tipo", "Observación", "Estado", "Dañados",
               "Foto")
COL_FOTO = ENCABEZADOS.index("Foto")
COLOR_TIPO = {"FALTANTE": "#F87171", "SOBRANTE": "#FBBF24"}

__all__ = ["DiferenciasView", "pedir_texto", "ver_foto"]


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
        self.btn_ajustar = QPushButton("Ajustar existencia…")
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("avisoFormulario")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.hide()
        barra = QHBoxLayout()
        barra.addWidget(self.btn_revisada)
        barra.addWidget(self.btn_recuento)
        barra.addWidget(self.btn_ajustar)
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
        raiz.addWidget(self.lbl_info)
        raiz.addLayout(barra)
        raiz.addWidget(self.tabla, 1)

        self.tabla.itemSelectionChanged.connect(self._ajustar)
        self.tabla.cellClicked.connect(self._clic)
        for combo in (self.combo_tarea, self.combo_tipo, self.combo_estado):
            combo.currentIndexChanged.connect(self._filtrar)
        self.btn_revisada.clicked.connect(self._revisada)
        self.btn_recuento.clicked.connect(self._recuento)
        self.btn_ajustar.clicked.connect(self._ajustar_existencia)
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
                      tareas.NOMBRE_TIPO[d.tipo], d.observacion, tareas.NOMBRE_REVISION[d.estado], _numero(d.danados),
                      "📷" if d.foto else "")
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
        # Corrige la existencia (Fase 3b): quien solicita ajustes, que nunca es el Administrador.
        sesion = self._sesion
        self.btn_ajustar.setVisible(sesion is not None and sesion.puede("ajustes", "GESTION") and not sesion.es_admin)
        self.btn_ajustar.setEnabled(d is not None and bool(d.almacen)
                                    and d.estado not in (tareas.AJUSTADA, tareas.AJUSTE_PENDIENTE))

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

    def _clic(self, fila: int, columna: int) -> None:
        if columna == COL_FOTO and 0 <= fila < len(self._vistas) and self._vistas[fila].foto:
            d = self._vistas[fila]
            ver_foto(self, d.foto, f"{d.producto} · {d.id_conteo}")

    def _ajustar_existencia(self) -> None:
        d = self._elegida()
        if d is None:
            return

        def cargar():
            almacen, actual, propuesta = movimientos.propuesta_desde_diferencia(d.id_conteo, d.sku)
            return almacen, actual, propuesta, movimientos.costo_unitario(d.sku), movimientos.umbrales()

        self._runner.run(cargar, lambda datos: self._abrir_ajuste(d, *datos), self._error_accion)

    def _abrir_ajuste(self, d: tareas.Diferencia, almacen: str, actual: float, propuesta: float, costo: float,
                      umbrales: tuple[float, float]) -> None:
        datos = pedir_ajuste(self, [(almacen, almacen)], [(d.sku, d.producto, "")],
                             inicial=(d.sku, almacen, propuesta, f"Conteo {d.id_conteo}"), actual=actual,
                             critico=lambda nueva: movimientos.es_critico(actual, nueva, costo, umbrales))
        if datos is None:
            return
        sku, alm, nueva, motivo = datos
        self._runner.run(movimientos.solicitar_ajuste, self._ajuste_listo, self._error_accion, self._sesion,
                         sku, alm, nueva, motivo, d.id_conteo)

    def _ajuste_listo(self, estado: str) -> None:
        self._accion_lista(None)
        self.lbl_info.setText(resultado(estado))
        self.lbl_info.show()

    def _accion(self, operacion, *args) -> None:
        self._runner.run(operacion, self._accion_lista, self._error_accion, self._sesion, *args)

    def _accion_lista(self, _resultado) -> None:
        self._error_accion("")
        self.refresh()

    def _error_accion(self, mensaje: str) -> None:
        if mensaje:
            self.lbl_info.hide()
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
