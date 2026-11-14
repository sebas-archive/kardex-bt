"""Pantalla «Tareas de conteo»: Inventario crea tareas (almacén, operador, productos, instrucciones), las reasigna
mientras nadie las empezó y las cierra; abajo, el avance por producto de la tarea elegida.

Quien tiene ``GESTION`` en ``tareas`` ve los botones; quien solo consulta (Administrador) ve la tabla. Los diálogos
son funciones del módulo para poder sustituirlos en las pruebas.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from btsync import tareas as bt

from .. import auth, maestros, tareas
from .base import QueryRunner, StateBanner
from .foto import ver_foto

ENCABEZADOS = ("Tarea", "Almacén", "Operador", "Productos", "Avance", "Estado")
ENCABEZADOS_AVANCE = ("Código", "Producto", "Contado", "Cantidad", "Foto")
COLOR_ESTADO = {bt.CON_DIFERENCIAS: "#FBBF24", bt.CON_ERROR: "#F87171", bt.SINCRONIZADA: "#4ADE80"}


def _numero(valor: float | None) -> str:
    if valor is None:
        return ""
    return f"{valor:,.3f}".rstrip("0").rstrip(".").replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------------ diálogos
def pedir_tarea(padre: QWidget, almacenes: list[tuple[str, str]], operadores: list[tuple[str, str]],
                productos: list[tuple[str, str, str]], inicial: tuple | None = None,
                error: str = "") -> tuple[str, str, str, list[str], str] | None:
    """Nombre, almacén, operador, SKUs elegidos e instrucciones. ``None`` si se cancela. Con ``inicial`` (lo que la
    persona ya había escrito) y ``error`` (por qué el PC lo rechazó) se reabre sin perder nada."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle("Nueva tarea de conteo")
    dialogo.resize(560, 620)
    nombre = QLineEdit()
    nombre.setPlaceholderText("p. ej. Bodega Norte, estantería A")
    combo_almacen, combo_operador, combo_categoria = QComboBox(), QComboBox(), QComboBox()
    for codigo, texto in almacenes:
        combo_almacen.addItem(f"{texto} ({codigo})", codigo)
    for usuario, texto in operadores:
        combo_operador.addItem(texto, usuario)
    combo_categoria.addItem("Todas las categorías", None)
    for categoria in sorted({c for _s, _n, c in productos}):
        combo_categoria.addItem(categoria, categoria)
    lista = QListWidget()
    for sku, texto, categoria in productos:
        item = QListWidgetItem(f"{texto}  ·  {sku}")
        item.setData(Qt.ItemDataRole.UserRole, (sku, categoria))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        lista.addItem(item)
    instrucciones = QPlainTextEdit()
    instrucciones.setPlaceholderText("Opcional: qué contar, dónde, cuidados…")
    instrucciones.setFixedHeight(70)
    elegidos = QLabel()
    aviso = QLabel(error)
    aviso.setObjectName("errorFormulario")
    aviso.setWordWrap(True)
    aviso.setVisible(bool(error))
    if inicial is not None:
        i_nombre, i_almacen, i_operador, i_skus, i_instr = inicial
        nombre.setText(i_nombre)
        combo_almacen.setCurrentIndex(max(0, combo_almacen.findData(i_almacen)))
        combo_operador.setCurrentIndex(max(0, combo_operador.findData(i_operador)))
        instrucciones.setPlainText(i_instr)
        for i in range(lista.count()):
            if lista.item(i).data(Qt.ItemDataRole.UserRole)[0] in i_skus:
                lista.item(i).setCheckState(Qt.CheckState.Checked)

    def visibles():
        return [lista.item(i) for i in range(lista.count()) if not lista.item(i).isHidden()]

    def contar():
        n = sum(lista.item(i).checkState() == Qt.CheckState.Checked for i in range(lista.count()))
        elegidos.setText(f"{n} producto(s) elegido(s)")

    def filtrar():
        categoria = combo_categoria.currentData()
        for i in range(lista.count()):
            lista.item(i).setHidden(categoria is not None and lista.item(i).data(Qt.ItemDataRole.UserRole)[1] != categoria)

    def marcar(estado):
        for item in visibles():
            item.setCheckState(estado)

    btn_todos, btn_ninguno = QPushButton("Marcar todos"), QPushButton("Ninguno")
    btn_todos.clicked.connect(lambda: marcar(Qt.CheckState.Checked))
    btn_ninguno.clicked.connect(lambda: marcar(Qt.CheckState.Unchecked))
    combo_categoria.currentIndexChanged.connect(filtrar)
    lista.itemChanged.connect(contar)
    contar()
    fila_filtro = QHBoxLayout()
    fila_filtro.addWidget(combo_categoria, 1)
    fila_filtro.addWidget(btn_todos)
    fila_filtro.addWidget(btn_ninguno)

    def datos():
        skus = [lista.item(i).data(Qt.ItemDataRole.UserRole)[0] for i in range(lista.count())
                if lista.item(i).checkState() == Qt.CheckState.Checked]
        return (nombre.text(), combo_almacen.currentData() or "", combo_operador.currentData() or "", skus,
                instrucciones.toPlainText())

    def aceptar():   # lo que se puede comprobar aquí no cierra el diálogo ni borra lo escrito
        problema = tareas.validar_tarea(*datos())
        if problema:
            aviso.setText(problema)
            aviso.show()
        else:
            dialogo.accept()

    forma = QFormLayout(dialogo)
    forma.addRow(aviso)
    forma.addRow("Nombre", nombre)
    forma.addRow("Almacén", combo_almacen)
    forma.addRow("Operador", combo_operador)
    forma.addRow("Productos", fila_filtro)
    forma.addRow(lista)
    forma.addRow("", elegidos)
    forma.addRow("Instrucciones", instrucciones)
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    botones.button(QDialogButtonBox.StandardButton.Ok).setText("Crear y asignar")
    botones.accepted.connect(aceptar)
    botones.rejected.connect(dialogo.reject)
    forma.addRow(botones)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return datos()


def pedir_operador(padre: QWidget, operadores: list[tuple[str, str]], actual: str) -> str | None:
    """A quién pasa la tarea. ``None`` si se cancela."""
    nombres = [n for _u, n in operadores]
    indice = next((i for i, (u, _n) in enumerate(operadores) if u == actual), 0)
    texto, ok = QInputDialog.getItem(padre, "Reasignar tarea", "Nuevo operador:", nombres, indice, False)
    if not ok or not nombres:
        return None
    return operadores[nombres.index(texto)][0]


def confirmar(padre: QWidget, pregunta: str) -> bool:
    return QMessageBox.question(padre, "Confirmar", pregunta) == QMessageBox.StandardButton.Yes


# ------------------------------------------------------------------ carga (fuera del hilo de la interfaz)
def _cargar() -> tuple[list, dict[str, str], dict[str, str]]:
    """Las tareas y los nombres de almacenes y operadores para mostrarlas."""
    almacenes = {a.codigo: a.nombre for a in maestros.listar_almacenes()}
    with tareas.db._conexion() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT usuario, nombre FROM {auth.TABLA} WHERE rol = :r", r=auth.OPERADOR)
        operadores = dict(cur.fetchall())
    return tareas.listar_tareas(), almacenes, operadores


def _opciones_nueva() -> tuple[list, list, list]:
    return ([(a.codigo, a.nombre) for a in maestros.listar_almacenes(solo_activos=True)],
            tareas.operadores_disponibles(), tareas.productos_disponibles())


class TareasView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[bt.ResumenTarea] = []
        self._vistas: list[bt.ResumenTarea] = []
        self._almacenes: dict[str, str] = {}
        self._operadores: dict[str, str] = {}
        self._avance: list[tuple[str, str, bool, float | None]] = []

        ayuda = QLabel("Tareas de conteo asignadas a los operadores. El estado se actualiza solo con lo que llega de "
                       "los teléfonos. Solo se reasigna una tarea que aún no empezó; cerrarla cuenta como 0 lo no contado.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()

        self.combo_estado, self.combo_operador = QComboBox(), QComboBox()
        self.combo_estado.addItem("Todos los estados", None)
        for estado in bt.ESTADOS:
            self.combo_estado.addItem(bt.NOMBRE_ESTADO[estado], estado)
        self.combo_operador.addItem("Todos los operadores", None)
        self.btn_nuevo = QPushButton("Nueva tarea…")
        self.btn_reasignar = QPushButton("Reasignar…")
        self.btn_cerrar = QPushButton("Cerrar tarea")
        barra = QHBoxLayout()
        for boton in (self.btn_nuevo, self.btn_reasignar, self.btn_cerrar):
            barra.addWidget(boton)
        barra.addStretch(1)
        barra.addWidget(self.combo_estado)
        barra.addWidget(self.combo_operador)

        self.tabla = self._tabla(ENCABEZADOS)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lbl_avance = QLabel("Elige una tarea para ver su avance por producto.")
        self.lbl_avance.setObjectName("ayuda")
        self.tabla_avance = self._tabla(ENCABEZADOS_AVANCE)
        self.lbl_errores = QLabel("")
        self.lbl_errores.setObjectName("errorFormulario")
        self.lbl_errores.setWordWrap(True)
        self.lbl_errores.hide()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.lbl_error)
        raiz.addLayout(barra)
        raiz.addWidget(self.tabla, 3)
        raiz.addWidget(self.lbl_avance)
        raiz.addWidget(self.lbl_errores)
        raiz.addWidget(self.tabla_avance, 2)

        self.tabla.itemSelectionChanged.connect(self._al_elegir)
        self.tabla_avance.cellClicked.connect(self._clic_avance)
        for combo in (self.combo_estado, self.combo_operador):
            combo.currentIndexChanged.connect(self._filtrar)
        self.btn_nuevo.clicked.connect(lambda: self._nuevo())   # clicked pasa «checked»: no es lo escrito
        self.btn_reasignar.clicked.connect(self._reasignar)
        self.btn_cerrar.clicked.connect(self._cerrar)
        self._ajustar()

    @staticmethod
    def _tabla(encabezados) -> QTableWidget:
        tabla = QTableWidget(0, len(encabezados))
        tabla.setHorizontalHeaderLabels(list(encabezados))
        tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tabla.verticalHeader().hide()
        tabla.verticalHeader().setDefaultSectionSize(34)
        tabla.horizontalHeader().setStretchLastSection(True)
        return tabla

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._mostrar(([], {}, {}))
            self._error_accion("")
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No depende del conteo elegido arriba."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("tareas"):
            return
        self._runner.run(_cargar, self._mostrar, self.banner.show_error, key="tareas")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    def avance_filas(self) -> list[tuple[str, ...]]:
        t = self.tabla_avance
        return [tuple(t.item(f, c).text() for c in range(len(ENCABEZADOS_AVANCE))) for f in range(t.rowCount())]

    def seleccionar(self, id_tarea: str) -> None:
        for fila, r in enumerate(self._vistas):
            if r.id == id_tarea:
                self.tabla.selectRow(fila)

    # ------------------------------------------------------------- internos
    def _gestiona(self) -> bool:
        return self._sesion is not None and self._sesion.puede("tareas", "GESTION")

    def _elegida(self) -> bt.ResumenTarea | None:
        fila = self.tabla.currentRow()
        return self._vistas[fila] if 0 <= fila < len(self._vistas) and self.tabla.selectedItems() else None

    def _mostrar(self, datos) -> None:
        self._todas, self._almacenes, self._operadores = datos
        actual = self.combo_operador.currentData()
        self.combo_operador.blockSignals(True)
        while self.combo_operador.count() > 1:
            self.combo_operador.removeItem(1)
        for usuario in sorted({r.operador for r in self._todas}, key=lambda u: self._operadores.get(u, u)):
            self.combo_operador.addItem(self._operadores.get(usuario, usuario), usuario)
        self.combo_operador.setCurrentIndex(max(0, self.combo_operador.findData(actual)) if actual else 0)
        self.combo_operador.blockSignals(False)
        self._filtrar()

    def _filtrar(self) -> None:
        elegida = self._elegida()
        estado, operador = self.combo_estado.currentData(), self.combo_operador.currentData()
        self._vistas = [r for r in self._todas
                        if (estado is None or r.estado == estado) and (operador is None or r.operador == operador)]
        self.tabla.blockSignals(True)
        self.tabla.setRowCount(len(self._vistas))
        for fila, r in enumerate(self._vistas):
            celdas = (r.id, self._almacenes.get(r.almacen, r.almacen), self._operadores.get(r.operador, r.operador),
                      str(r.total), f"{r.contados}/{r.total}", bt.NOMBRE_ESTADO[r.estado])
            for columna, texto in enumerate(celdas):
                item = QTableWidgetItem(texto)
                if columna == 5 and r.estado in COLOR_ESTADO:
                    item.setForeground(QBrush(QColor(COLOR_ESTADO[r.estado])))
                if r.estado == bt.CERRADA:
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.clearSelection()
        self.tabla.blockSignals(False)
        if elegida is not None:
            self.seleccionar(elegida.id)
        if not self._todas:
            self.banner.show_empty("Todavía no hay tareas de conteo." + (" Crea la primera con «Nueva tarea…»."
                                                                        if self._gestiona() else ""))
        elif not self._vistas:
            self.banner.show_empty("Ninguna tarea coincide con los filtros.")
        else:
            self.banner.clear()
        self._al_elegir()

    def _al_elegir(self) -> None:
        self._ajustar()
        r = self._elegida()
        if r is None:
            self.lbl_avance.setText("Elige una tarea para ver su avance por producto.")
            self._mostrar_avance([])
            return
        self.lbl_avance.setText(f"Avance de {r.id} · {r.nombre}" + (f" — {r.instrucciones}" if r.instrucciones else ""))
        self._runner.run(lambda i: (tareas.avance(i), tareas.errores(i)), self._mostrar_avance, self.banner.show_error,
                         r.id, key="avance")

    def _mostrar_avance(self, datos) -> None:
        filas, errores = datos if isinstance(datos, tuple) else (datos, [])
        self._avance = list(filas)
        if errores:
            detalle = ", ".join(f"{motivo} ({sku})" for sku, motivo in errores[:5]) + ("…" if len(errores) > 5 else "")
            self.lbl_errores.setText(f"{len(errores)} lectura(s) rechazada(s) por el PC: {detalle}. Corrige el código "
                                     "en el teléfono o pide al administrador que las reprocese.")
        self.lbl_errores.setVisible(bool(errores))
        self.tabla_avance.setRowCount(len(self._avance))
        for fila, (sku, nombre, contado, cantidad, foto) in enumerate(self._avance):
            for columna, texto in enumerate((sku, nombre, "Sí" if contado else "No", _numero(cantidad), "📷" if foto else "")):
                self.tabla_avance.setItem(fila, columna, QTableWidgetItem(texto))
        self.tabla_avance.resizeColumnsToContents()

    def _clic_avance(self, fila: int, columna: int) -> None:
        if columna == len(ENCABEZADOS_AVANCE) - 1 and 0 <= fila < len(self._avance) and self._avance[fila][4]:
            sku, nombre, *_resto, foto = self._avance[fila]
            ver_foto(self, foto, f"{nombre} · {sku}")

    def _ajustar(self) -> None:
        gestiona, r = self._gestiona(), self._elegida()
        for boton in (self.btn_nuevo, self.btn_reasignar, self.btn_cerrar):
            boton.setVisible(gestiona)
        self.btn_reasignar.setEnabled(r is not None and r.estado == bt.ASIGNADA)
        self.btn_cerrar.setEnabled(r is not None and r.estado != bt.CERRADA)

    def _nuevo(self, inicial: tuple | None = None, error: str = "") -> None:
        self._runner.run(_opciones_nueva, lambda opciones: self._abrir_nueva(opciones, inicial, error), self._error_accion)

    def _abrir_nueva(self, opciones, inicial: tuple | None = None, error: str = "") -> None:
        almacenes, operadores, productos = opciones
        if not almacenes or not operadores:
            self._error_accion("No hay almacenes activos." if not almacenes else
                               "No hay operadores activos: aprueba primero la cuenta del operador en Solicitudes.")
            return
        datos = pedir_tarea(self, almacenes, operadores, productos, inicial=inicial, error=error)
        if datos is None:
            return
        # Si el PC la rechaza (p. ej. otro usuario desactivó el operador), el diálogo se reabre con lo escrito.
        self._runner.run(tareas.crear_tarea, self._accion_lista,
                         lambda mensaje: self._rechazada(datos, mensaje), self._sesion, *datos)

    def _rechazada(self, datos: tuple, mensaje: str) -> None:
        self._error_accion(mensaje)
        self._nuevo(inicial=datos, error=mensaje)

    def _reasignar(self) -> None:
        r = self._elegida()
        if r is not None:
            self._runner.run(tareas.operadores_disponibles, lambda ops: self._abrir_reasignar(r, ops), self._error_accion)

    def _abrir_reasignar(self, r: bt.ResumenTarea, operadores) -> None:
        operador = pedir_operador(self, operadores, r.operador)
        if operador is not None and operador != r.operador:
            self._accion(tareas.reasignar, r.id, operador)

    def _cerrar(self) -> None:
        r = self._elegida()
        if r is not None and confirmar(self, f"¿Cerrar la tarea {r.id}? Lo que no se contó quedará como 0 y ya no "
                                             f"se aceptarán lecturas. No se puede deshacer."):
            self._accion(tareas.cerrar, r.id)

    def _accion(self, operacion, *args) -> None:
        self._runner.run(operacion, self._accion_lista, self._error_accion, self._sesion, *args)

    def _accion_lista(self, _resultado) -> None:
        self._error_accion("")
        self.refresh()

    def _error_accion(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))
