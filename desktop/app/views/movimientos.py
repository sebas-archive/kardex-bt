"""Pantalla «Movimientos»: el historial de entradas, salidas y ajustes, con filtros, y los botones para registrar una
entrada o una salida (Inventario). El Administrador consulta.

El diálogo es una función del módulo para poder sustituirlo en las pruebas. Valida antes de cerrarse; si el PC rechaza
el movimiento (p. ej. «Solo hay 3 en ese almacén»), se reabre con lo que la persona escribió.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QDoubleSpinBox,
                             QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from .. import auth, maestros, movimientos, tareas
from .base import QueryRunner, StateBanner

ENCABEZADOS = ("Fecha", "Tipo", "Producto", "Almacén", "Cantidad", "Motivo / observación", "Responsable", "Estado")
COLOR_TIPO = {movimientos.ENTRADA: "#4ADE80", movimientos.SALIDA: "#F87171", movimientos.AJUSTE: "#FBBF24"}


def con_signo(valor: float) -> str:
    return ("+" if valor > 0 else "−" if valor < 0 else "") + movimientos.fmt(abs(valor))


def fecha_corta(fecha) -> str:
    """«13/11/2026 10:20»; solo la fecha si se registró con fecha anterior (sin hora)."""
    return f"{fecha:%d/%m/%Y}" if (fecha.hour, fecha.minute, fecha.second) == (0, 0, 0) else f"{fecha:%d/%m/%Y %H:%M}"


def combo_productos(productos: list[tuple[str, str, str]]) -> QComboBox:
    """Producto con búsqueda al escribir (nombre o código)."""
    combo = QComboBox()
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    for sku, nombre, categoria in productos:
        combo.addItem(f"{nombre} · {sku} ({categoria})", sku)
    combo.completer().setFilterMode(Qt.MatchFlag.MatchContains)
    return combo


def producto_elegido(combo: QComboBox) -> str:
    """El SKU del producto que se ve en el combo; «» si lo escrito no coincide con ninguno de la lista (si no,
    quedaría elegido el anterior sin que la persona lo vea)."""
    indice = combo.findText(combo.currentText())
    return combo.itemData(indice) or "" if indice >= 0 else ""


def opciones() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Almacenes activos y productos de categorías activas (fuera del hilo de la interfaz)."""
    return ([(a.codigo, a.nombre) for a in maestros.listar_almacenes(solo_activos=True)], tareas.productos_disponibles())


def pedir_movimiento(padre: QWidget, tipo: str, almacenes: list[tuple[str, str]], productos: list[tuple[str, str, str]],
                     inicial: tuple | None = None, error: str = "") -> tuple | None:
    """(sku, almacén, cantidad, fecha, motivo, observaciones); en una entrada el motivo es «». ``None`` si se cancela."""
    salida = tipo == movimientos.SALIDA
    dialogo = QDialog(padre)
    dialogo.setWindowTitle("Registrar salida" if salida else "Registrar entrada")
    dialogo.resize(520, 0)
    producto = combo_productos(productos)
    almacen = QComboBox()
    for codigo, nombre in almacenes:
        almacen.addItem(nombre, codigo)
    cantidad = QDoubleSpinBox()
    cantidad.setDecimals(3)
    cantidad.setRange(0, 999_999_999.999)
    fecha = QDateEdit(QDate.currentDate())
    fecha.setCalendarPopup(True)
    fecha.setMaximumDate(QDate.currentDate())
    fecha.setDisplayFormat("dd/MM/yyyy")
    motivo = QComboBox()
    motivo.addItem("Elige el motivo", "")
    for m in movimientos.MOTIVOS_SALIDA:
        motivo.addItem(m, m)
    observaciones = QLineEdit()
    observaciones.setMaxLength(300)
    observaciones.setPlaceholderText("Opcional: proveedor, factura, destino…")
    aviso = QLabel(error)
    aviso.setObjectName("errorFormulario")
    aviso.setWordWrap(True)
    aviso.setVisible(bool(error))
    if inicial is not None:
        i_sku, i_alm, i_cant, i_fecha, i_motivo, i_obs = inicial
        producto.setCurrentIndex(max(0, producto.findData(i_sku)))
        almacen.setCurrentIndex(max(0, almacen.findData(i_alm)))
        cantidad.setValue(i_cant)
        fecha.setDate(QDate(i_fecha.year, i_fecha.month, i_fecha.day))
        motivo.setCurrentIndex(max(0, motivo.findData(i_motivo)))
        observaciones.setText(i_obs)

    def datos():
        d = fecha.date()
        return (producto_elegido(producto), almacen.currentData() or "", round(cantidad.value(), 3),
                date(d.year(), d.month(), d.day()), motivo.currentData() if salida else "", observaciones.text())

    def aceptar():
        sku, alm, cant, _f, mot, _o = datos()
        problema = ("Elige el producto de la lista." if not sku else "Elige el almacén." if not alm else
                    "La cantidad debe ser mayor que 0." if cant <= 0 else
                    "Elige el motivo de la salida." if salida and not mot else None)
        if problema:
            aviso.setText(problema)
            aviso.show()
        else:
            dialogo.accept()

    forma = QFormLayout(dialogo)
    forma.addRow(aviso)
    forma.addRow("Producto", producto)
    forma.addRow("Almacén", almacen)
    forma.addRow("Cantidad", cantidad)
    forma.addRow("Fecha", fecha)
    if salida:
        forma.addRow("Motivo", motivo)
    forma.addRow("Observaciones", observaciones)
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    botones.button(QDialogButtonBox.StandardButton.Ok).setText("Registrar")
    botones.accepted.connect(aceptar)
    botones.rejected.connect(dialogo.reject)
    forma.addRow(botones)
    return datos() if dialogo.exec() == QDialog.DialogCode.Accepted else None


class MovimientosView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todos: list[movimientos.Movimiento] = []
        self._vistos: list[movimientos.Movimiento] = []

        ayuda = QLabel("Entradas, salidas y ajustes de inventario. Cada entrada o salida cambia la existencia al momento; "
                       "una salida nunca deja la existencia por debajo de 0.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        self.btn_entrada = QPushButton("+ Entrada…")
        self.btn_salida = QPushButton("− Salida…")
        self.combo_tipo, self.combo_almacen, self.combo_responsable = QComboBox(), QComboBox(), QComboBox()
        self.combo_tipo.addItem("Todos los tipos", None)
        for tipo, texto in movimientos.NOMBRE_TIPO.items():
            self.combo_tipo.addItem(texto, tipo)
        self.combo_almacen.addItem("Todos los almacenes", None)
        self.combo_responsable.addItem("Todos los responsables", None)
        self.fecha_desde, self.fecha_hasta = QDateEdit(), QDateEdit()
        for editor, dias in ((self.fecha_desde, 30), (self.fecha_hasta, 0)):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")
            editor.setDate(QDate.currentDate().addDays(-dias))
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar producto o código")
        barra = QHBoxLayout()
        barra.addWidget(self.btn_entrada)
        barra.addWidget(self.btn_salida)
        barra.addStretch(1)
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        for w in (self.combo_tipo, self.combo_almacen, self.combo_responsable, QLabel("Desde"), self.fecha_desde,
                  QLabel("Hasta"), self.fecha_hasta):
            filtros.addWidget(w)

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
        raiz.addLayout(filtros)
        raiz.addWidget(self.tabla, 1)

        self.btn_entrada.clicked.connect(lambda: self._nuevo(movimientos.ENTRADA))
        self.btn_salida.clicked.connect(lambda: self._nuevo(movimientos.SALIDA))
        for combo in (self.combo_tipo, self.combo_almacen, self.combo_responsable):
            combo.currentIndexChanged.connect(self._filtrar)
        for editor in (self.fecha_desde, self.fecha_hasta):
            editor.dateChanged.connect(self._filtrar)
        self.txt_buscar.textChanged.connect(self._filtrar)
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar([])
            self._error_accion("")
        self._ajustar()
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No depende del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("movimientos"):
            return
        self._runner.run(movimientos.listar, self._mostrar, self.banner.show_error, key="movimientos")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    # ------------------------------------------------------------- internos
    def _gestiona(self) -> bool:
        return self._sesion is not None and self._sesion.puede("entradas_salidas", "GESTION")

    def _ajustar(self) -> None:
        for boton in (self.btn_entrada, self.btn_salida):
            boton.setVisible(self._gestiona())

    @staticmethod
    def _rellenar(combo: QComboBox, valores) -> None:
        actual = combo.currentData()
        combo.blockSignals(True)
        while combo.count() > 1:
            combo.removeItem(1)
        for dato, texto in valores:
            combo.addItem(texto, dato)
        combo.setCurrentIndex(max(0, combo.findData(actual)) if actual is not None else 0)
        combo.blockSignals(False)

    def _mostrar(self, datos: list[movimientos.Movimiento]) -> None:
        self._todos = list(datos)
        self._rellenar(self.combo_almacen, sorted({(m.almacen, m.nombre_almacen) for m in self._todos}))
        self._rellenar(self.combo_responsable, sorted({(m.responsable, m.nombre_responsable) for m in self._todos},
                                                      key=lambda x: x[1]))
        self._filtrar()

    def _filtrar(self) -> None:
        tipo, almacen = self.combo_tipo.currentData(), self.combo_almacen.currentData()
        responsable, texto = self.combo_responsable.currentData(), self.txt_buscar.text().strip().lower()
        d, h = self.fecha_desde.date(), self.fecha_hasta.date()
        desde = date(d.year(), d.month(), d.day())
        hasta = date(h.year(), h.month(), h.day())
        sin_tope = hasta >= date.today()   # «hasta hoy» incluye lo que se registre después de abrir la pantalla
        self._vistos = [m for m in self._todos
                        if (tipo is None or m.tipo == tipo) and (almacen is None or m.almacen == almacen)
                        and (responsable is None or m.responsable == responsable)
                        and m.fecha.date() >= desde and (sin_tope or m.fecha.date() <= hasta)
                        and (not texto or texto in m.producto.lower() or texto in m.sku.lower())]
        self.tabla.setRowCount(len(self._vistos))
        for fila, m in enumerate(self._vistos):
            detalle = " · ".join(x for x in (m.motivo, m.observaciones,
                                             f"Rechazo: {m.motivo_rechazo}" if m.motivo_rechazo else "") if x)
            celdas = (fecha_corta(m.fecha), movimientos.NOMBRE_TIPO[m.tipo], m.producto, m.nombre_almacen,
                      con_signo(m.cantidad), detalle, m.nombre_responsable, movimientos.NOMBRE_ESTADO[m.estado])
            for columna, texto_celda in enumerate(celdas):
                item = QTableWidgetItem(texto_celda)
                if columna == 1:
                    item.setForeground(QBrush(QColor(COLOR_TIPO[m.tipo])))
                if m.estado == movimientos.RECHAZADO:
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        if not self._todos:
            self.banner.show_empty("Todavía no hay movimientos." + (" Registra el primero con «+ Entrada…»."
                                                                     if self._gestiona() else ""))
        elif not self._vistos:
            self.banner.show_empty("Ningún movimiento coincide con los filtros.")
        else:
            self.banner.clear()

    def _nuevo(self, tipo: str, inicial: tuple | None = None, error: str = "") -> None:
        self._runner.run(opciones, lambda o: self._abrir(tipo, o, inicial, error), self._error_accion)

    def _abrir(self, tipo: str, opciones_, inicial, error) -> None:
        almacenes, productos = opciones_
        if not almacenes or not productos:
            self._error_accion("No hay almacenes activos." if not almacenes else "No hay productos de categorías activas.")
            return
        datos = pedir_movimiento(self, tipo, almacenes, productos, inicial=inicial, error=error)
        if datos is None:
            return
        sku, almacen, cantidad, fecha, motivo, observaciones = datos
        if tipo == movimientos.ENTRADA:
            funcion, args = movimientos.registrar_entrada, (sku, almacen, cantidad, fecha, observaciones)
        else:
            funcion, args = movimientos.registrar_salida, (sku, almacen, cantidad, fecha, motivo, observaciones)
        self._runner.run(funcion, self._listo, lambda mensaje: self._rechazado(tipo, datos, mensaje), self._sesion, *args)

    def _rechazado(self, tipo: str, datos: tuple, mensaje: str) -> None:
        self._error_accion(mensaje)
        self._nuevo(tipo, inicial=datos, error=mensaje)

    def _listo(self, _resultado) -> None:
        self._error_accion("")
        self.refresh()

    def _error_accion(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))

