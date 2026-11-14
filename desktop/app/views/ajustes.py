"""Pantalla «Ajustes»: Inventario solicita ajustes de existencia con motivo; los críticos (cambian 10 % o más, o valen
$200.000 o más) quedan pendientes hasta que el Administrador los aprueba o los rechaza con motivo.

``pedir_ajuste`` también lo usa «Diferencias» (con la cantidad propuesta a partir del conteo). Los diálogos son
funciones del módulo para poder sustituirlos en las pruebas.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from .. import auth, movimientos
from .base import QueryRunner, StateBanner
from .maestros import pedir_texto
from .movimientos import combo_productos, con_signo, opciones, producto_elegido

ENCABEZADOS = ("Fecha", "Producto", "Almacén", "Antes", "Después", "Dif.", "Motivo", "Estado", "Solicitó")
COLOR_ESTADO = {movimientos.PENDIENTE: "#FBBF24", movimientos.APLICADO: "#4ADE80"}

__all__ = ["AjustesView", "confirmar", "pedir_ajuste", "pedir_texto", "resultado"]


def confirmar(padre: QWidget, pregunta: str) -> bool:
    return QMessageBox.question(padre, "Confirmar", pregunta) == QMessageBox.StandardButton.Yes


def resultado(estado: str) -> str:
    return ("El ajuste quedó pendiente de aprobación del Administrador: la existencia no cambia hasta entonces."
            if estado == movimientos.PENDIENTE else "Ajuste aplicado: la existencia ya cambió.")


def pedir_ajuste(padre: QWidget, almacenes: list[tuple[str, str]], productos: list[tuple[str, str, str]],
                 inicial: tuple | None = None, error: str = "", actual: float | None = None,
                 critico: Callable[[float], bool] | None = None,
                 consultar: Callable[[str, str], tuple[float, float]] | None = None) -> tuple[str, str, float, str] | None:
    """(sku, almacén, cantidad nueva, motivo). Con ``inicial`` (desde una diferencia) el producto y el almacén quedan
    fijos y se muestra la existencia ``actual``; ``critico(nueva)`` avisa si necesitará aprobación. En un ajuste a mano,
    ``consultar(sku, almacén) -> (existencia, costo)`` se llama fuera del hilo de la interfaz al cambiar la elección."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle("Ajustar existencia")
    dialogo.resize(520, 0)
    producto = combo_productos(productos)
    almacen = QComboBox()
    for codigo, nombre in almacenes:
        almacen.addItem(nombre, codigo)
    nueva = QDoubleSpinBox()
    nueva.setDecimals(3)
    nueva.setRange(0, 999_999_999.999)
    motivo = QLineEdit()
    motivo.setMaxLength(60)
    motivo.setPlaceholderText("p. ej. Conteo T-014, merma, daño")
    aviso = QLabel(error)
    aviso.setObjectName("errorFormulario")
    aviso.setWordWrap(True)
    aviso.setVisible(bool(error))
    nota = QLabel("")
    nota.setObjectName("ayuda")
    nota.setWordWrap(True)
    if inicial is not None:
        i_sku, i_alm, i_nueva, i_motivo = inicial
        producto.setCurrentIndex(max(0, producto.findData(i_sku)))
        almacen.setCurrentIndex(max(0, almacen.findData(i_alm)))
        producto.setEnabled(False)
        almacen.setEnabled(False)
        nueva.setValue(i_nueva)
        motivo.setText(i_motivo)

    estado = {"actual": actual, "critico": critico}

    def avisar_critico():
        actual_, critico_ = estado["actual"], estado["critico"]
        partes = [] if actual_ is None else [f"Hoy hay {movimientos.fmt(actual_)}."]
        if critico_ is not None and critico_(round(nueva.value(), 3)):
            partes.append("Este ajuste necesitará aprobación del Administrador.")
        nota.setText(" ".join(partes))
        nota.setVisible(bool(partes))

    nueva.valueChanged.connect(avisar_critico)
    avisar_critico()

    if consultar is not None:
        runner = QueryRunner(dialogo)

        def recibir(valores):
            hoy, costo = valores
            estado["actual"] = hoy
            estado["critico"] = lambda n: movimientos.es_critico(hoy, n, costo)
            avisar_critico()

        def recargar():
            sku, alm = producto_elegido(producto), almacen.currentData()
            estado["actual"] = estado["critico"] = None
            avisar_critico()
            if sku and alm:
                runner.run(consultar, recibir, lambda _m: None, sku, alm, key="existencia")

        producto.currentIndexChanged.connect(recargar)
        almacen.currentIndexChanged.connect(recargar)
        recargar()

    def datos():
        return producto_elegido(producto), almacen.currentData() or "", round(nueva.value(), 3), motivo.text()

    def aceptar():
        sku, alm, cantidad, mot = datos()
        problema = ("Elige el producto de la lista." if not sku else "Elige el almacén." if not alm else
                    "Escribe el motivo del ajuste." if not mot.strip() else
                    "La cantidad nueva es igual a la actual." if estado["actual"] is not None
                    and cantidad == estado["actual"] else None)
        if problema:
            aviso.setText(problema)
            aviso.show()
        else:
            dialogo.accept()

    forma = QFormLayout(dialogo)
    forma.addRow(aviso)
    forma.addRow("Producto", producto)
    forma.addRow("Almacén", almacen)
    forma.addRow("Cantidad nueva", nueva)
    forma.addRow("", nota)
    forma.addRow("Motivo", motivo)
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    botones.button(QDialogButtonBox.StandardButton.Ok).setText("Solicitar ajuste")
    botones.accepted.connect(aceptar)
    botones.rejected.connect(dialogo.reject)
    forma.addRow(botones)
    return datos() if dialogo.exec() == QDialog.DialogCode.Accepted else None


class AjustesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todos: list[movimientos.Movimiento] = []
        self._vistos: list[movimientos.Movimiento] = []

        ayuda = QLabel("Correcciones de existencia con motivo. Los ajustes críticos (cambian 10 % o más, o valen $200.000 "
                       "o más) esperan la aprobación del Administrador y no cambian nada hasta entonces.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("avisoFormulario")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.hide()

        self.btn_nuevo = QPushButton("+ Nuevo ajuste…")
        self.btn_aprobar = QPushButton("Aprobar")
        self.btn_rechazar = QPushButton("Rechazar…")
        self.combo_estado = QComboBox()
        self.combo_estado.addItem("Todos los estados", None)
        for estado, texto in movimientos.NOMBRE_ESTADO.items():
            self.combo_estado.addItem(texto, estado)
        barra = QHBoxLayout()
        for boton in (self.btn_nuevo, self.btn_aprobar, self.btn_rechazar):
            barra.addWidget(boton)
        barra.addStretch(1)
        barra.addWidget(self.combo_estado)

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
        for w in (ayuda, self.banner, self.lbl_error, self.lbl_info):
            raiz.addWidget(w)
        raiz.addLayout(barra)
        raiz.addWidget(self.tabla, 1)

        self.tabla.itemSelectionChanged.connect(self._ajustar)
        self.combo_estado.currentIndexChanged.connect(self._filtrar)
        self.btn_nuevo.clicked.connect(lambda: self._nuevo())
        self.btn_aprobar.clicked.connect(self._aprobar)
        self.btn_rechazar.clicked.connect(self._rechazar)
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
            self._error_accion("")
            self._info("")
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No depende del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("ajustes"):
            return
        self._runner.run(movimientos.listar, self._mostrar, self.banner.show_error, key="ajustes")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    def seleccionar(self, id_mov: int) -> None:
        for fila, m in enumerate(self._vistos):
            if m.id == id_mov:
                self.tabla.selectRow(fila)

    # ------------------------------------------------------------- internos
    def _solicita(self) -> bool:
        return self._sesion is not None and self._sesion.puede("ajustes", "GESTION") and not self._sesion.es_admin

    def _aprueba(self) -> bool:
        return self._sesion is not None and self._sesion.puede("ajustes", "GESTION") and self._sesion.es_admin

    def _elegido(self) -> movimientos.Movimiento | None:
        fila = self.tabla.currentRow()
        return self._vistos[fila] if 0 <= fila < len(self._vistos) and self.tabla.selectedItems() else None

    def _mostrar(self, datos: list[movimientos.Movimiento]) -> None:
        self._todos = [m for m in datos if m.tipo == movimientos.AJUSTE]
        self._filtrar()

    def _filtrar(self) -> None:
        elegido = self._elegido()
        estado = self.combo_estado.currentData()
        self._vistos = [m for m in self._todos if estado is None or m.estado == estado]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self._vistos))
        for fila, m in enumerate(self._vistos):
            motivo = m.motivo + (f" · Rechazo: {m.motivo_rechazo}" if m.motivo_rechazo else "")
            celdas = (f"{m.fecha:%d/%m/%Y %H:%M}", m.producto, m.nombre_almacen, movimientos.fmt(m.antes or 0),
                      movimientos.fmt(m.despues or 0), con_signo(m.cantidad), motivo,
                      movimientos.NOMBRE_ESTADO[m.estado], m.nombre_responsable)
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if columna == 7 and m.estado in COLOR_ESTADO:
                    item.setForeground(QBrush(QColor(COLOR_ESTADO[m.estado])))
                if m.estado == movimientos.RECHAZADO:
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.clearSelection()
        self.tabla.blockSignals(False)
        if elegido is not None:
            self.seleccionar(elegido.id)
        if not self._todos:
            self.banner.show_empty("Todavía no hay ajustes.")
        elif not self._vistos:
            self.banner.show_empty("Ningún ajuste coincide con el filtro.")
        else:
            self.banner.clear()
        self._ajustar()

    def _ajustar(self) -> None:
        m = self._elegido()
        self.btn_nuevo.setVisible(self._solicita())
        for boton in (self.btn_aprobar, self.btn_rechazar):
            boton.setVisible(self._aprueba())
            boton.setEnabled(m is not None and m.estado == movimientos.PENDIENTE)

    def _nuevo(self, inicial: tuple | None = None, error: str = "") -> None:
        self._runner.run(opciones, lambda o: self._abrir(o, inicial, error), self._error_accion)

    def _abrir(self, opciones_, inicial, error) -> None:
        almacenes, productos = opciones_
        if not almacenes or not productos:
            self._error_accion("No hay almacenes activos." if not almacenes else "No hay productos de categorías activas.")
            return
        datos = pedir_ajuste(self, almacenes, productos, inicial=inicial, error=error,
                             consultar=movimientos.existencia_y_costo)
        if datos is None:
            return
        self._runner.run(movimientos.solicitar_ajuste, self._listo,
                         lambda mensaje: self._rechazado(datos, mensaje), self._sesion, *datos)

    def _rechazado(self, datos: tuple, mensaje: str) -> None:
        self._error_accion(mensaje)
        self._nuevo(inicial=datos, error=mensaje)

    def _aprobar(self) -> None:
        m = self._elegido()
        if m is not None:   # primero la existencia de hoy: el Administrador ve en qué quedará antes de aprobar
            self._runner.run(movimientos.existencia, lambda hoy: self._confirmar_aprobacion(m, hoy), self._error_accion,
                             m.sku, m.almacen)

    def _confirmar_aprobacion(self, m: movimientos.Movimiento, hoy: float) -> None:
        pregunta = (f"{m.producto} en {m.nombre_almacen}: hoy hay {movimientos.fmt(hoy)}. Al aprobar quedará en "
                    f"{movimientos.fmt(hoy + m.cantidad)} ({con_signo(m.cantidad)}). ¿Aprobar el ajuste?")
        if confirmar(self, pregunta[0].upper() + pregunta[1:]):
            self._runner.run(movimientos.aprobar, lambda _r: self._listo(movimientos.APLICADO), self._error_accion,
                             self._sesion, m.id)

    def _rechazar(self) -> None:
        m = self._elegido()
        if m is None:
            return
        motivo = pedir_texto(self, "Rechazar ajuste", f"{m.producto}: ¿por qué se rechaza?")
        if motivo is not None:
            self._runner.run(movimientos.rechazar, lambda _r: self._listo(None), self._error_accion, self._sesion,
                             m.id, motivo)

    def _listo(self, estado) -> None:
        self._error_accion("")
        self._info(resultado(estado) if estado in (movimientos.PENDIENTE, movimientos.APLICADO) else "")
        self.refresh()

    def _info(self, texto: str) -> None:
        self.lbl_info.setText(texto)
        self.lbl_info.setVisible(bool(texto))

    def _error_accion(self, mensaje: str) -> None:
        if mensaje:
            self._info("")
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
