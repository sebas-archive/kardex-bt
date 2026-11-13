"""Pantallas «Categorías» y «Almacenes»: tabla, crear, editar y activar/desactivar.

Quien tiene ``GESTION`` en el módulo ``categorias`` (Inventario, por defecto) ve los botones; quien solo consulta
(Administrador, por defecto) ve la tabla. Los diálogos son funciones del módulo para poder sustituirlos en las pruebas.
"""

from __future__ import annotations

from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
                             QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auth, maestros
from .base import QueryRunner, StateBanner


def pedir_texto(padre: QWidget, titulo: str, pregunta: str, inicial: str = "") -> str | None:
    """Un texto (p. ej. el nombre de la categoría). ``None`` si se cancela."""
    texto, ok = QInputDialog.getText(padre, titulo, pregunta, text=inicial)
    return texto if ok else None


def pedir_almacen(padre: QWidget, inicial: maestros.Almacen | None = None) -> tuple[str, str, str] | None:
    """Código, nombre y ubicación. Al editar, el código no se cambia. ``None`` si se cancela."""
    dialogo = QDialog(padre)
    dialogo.setWindowTitle("Editar almacén" if inicial else "Nuevo almacén")
    codigo, nombre, ubicacion = QLineEdit(), QLineEdit(), QLineEdit()
    codigo.setPlaceholderText("ALM-03")
    if inicial is not None:
        codigo.setText(inicial.codigo)
        codigo.setReadOnly(True)
        nombre.setText(inicial.nombre)
        ubicacion.setText(inicial.ubicacion)
    forma = QFormLayout(dialogo)
    forma.addRow("Código", codigo)
    forma.addRow("Nombre", nombre)
    forma.addRow("Ubicación", ubicacion)
    botones = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    botones.accepted.connect(dialogo.accept)
    botones.rejected.connect(dialogo.reject)
    forma.addRow(botones)
    if dialogo.exec() != QDialog.DialogCode.Accepted:
        return None
    return codigo.text(), nombre.text(), ubicacion.text()


class _TablaMaestra(QWidget):
    """Lo común: ayuda, aviso, botones de gestión y una tabla de solo lectura que recuerda la fila elegida por clave."""

    ENCABEZADOS: tuple[str, ...] = ()
    AYUDA = ""
    CLAVE_REFRESCO = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._datos: list = []

        ayuda = QLabel(self.AYUDA)
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        # Errores de una ACCIÓN (p. ej. «ya existe»): aparte del aviso de consulta, que el refresco de 5 s limpia.
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorFormulario")
        self.lbl_error.setWordWrap(True)
        self.lbl_error.hide()
        self.btn_nuevo = QPushButton("Nuevo…")
        self.btn_editar = QPushButton("Editar…")
        self.btn_estado = QPushButton("Desactivar")
        acciones = QHBoxLayout()
        for boton in (self.btn_nuevo, self.btn_editar, self.btn_estado):
            acciones.addWidget(boton)
        acciones.addStretch(1)
        self.tabla = QTableWidget(0, len(self.ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels(list(self.ENCABEZADOS))
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(36)
        self.tabla.horizontalHeader().setStretchLastSection(True)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.lbl_error)
        raiz.addLayout(acciones)
        raiz.addWidget(self.tabla, 1)

        self.tabla.itemSelectionChanged.connect(self._ajustar)
        self.btn_nuevo.clicked.connect(self._nuevo)
        self.btn_editar.clicked.connect(self._editar)
        self.btn_estado.clicked.connect(self._cambiar_estado)
        self._ajustar()

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:   # al salir no queda nada en pantalla
            self._mostrar([])
            self._error_accion("")
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No dependen del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("categorias"):
            return
        self._runner.run(self._cargar, self._mostrar, self.banner.show_error, key=self.CLAVE_REFRESCO)

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(self.ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    def seleccionar(self, clave: str) -> None:
        for fila, dato in enumerate(self._datos):
            if self._clave(dato) == clave:
                self.tabla.selectRow(fila)

    # ------------------------------------------------- lo que define cada pantalla
    @staticmethod
    def _cargar() -> list: raise NotImplementedError
    @staticmethod
    def _clave(dato) -> str: raise NotImplementedError
    @staticmethod
    def _celdas(dato) -> tuple[str, ...]: raise NotImplementedError
    @staticmethod
    def _activo(dato) -> bool: raise NotImplementedError
    def _nuevo(self) -> None: raise NotImplementedError
    def _editar(self) -> None: raise NotImplementedError
    def _cambiar_estado(self) -> None: raise NotImplementedError

    # ------------------------------------------------------------- internos
    def _gestiona(self) -> bool:
        return self._sesion is not None and self._sesion.puede("categorias", "GESTION")

    def _elegido(self):
        fila = self.tabla.currentRow()
        return self._datos[fila] if 0 <= fila < len(self._datos) and self.tabla.selectedItems() else None

    def _mostrar(self, datos: list) -> None:
        self.banner.clear()
        elegido = self._elegido()
        self._datos = list(datos)
        self.tabla.setRowCount(len(self._datos))
        for fila, dato in enumerate(self._datos):
            for columna, texto in enumerate(self._celdas(dato)):
                item = QTableWidgetItem(texto)
                if not self._activo(dato):
                    item.setForeground(QBrush(QColor("#6E6E6E")))
                self.tabla.setItem(fila, columna, item)
        self.tabla.resizeColumnsToContents()
        self.tabla.clearSelection()
        if elegido is not None:
            self.seleccionar(self._clave(elegido))
        self._ajustar()

    def _ajustar(self) -> None:
        gestiona, dato = self._gestiona(), self._elegido()
        for boton in (self.btn_nuevo, self.btn_editar, self.btn_estado):
            boton.setVisible(gestiona)
        self.btn_editar.setEnabled(dato is not None)
        self.btn_estado.setEnabled(dato is not None)
        if dato is not None:
            self.btn_estado.setText("Desactivar" if self._activo(dato) else "Activar")

    def _accion(self, operacion, *args) -> None:
        self._runner.run(operacion, self._accion_lista, self._error_accion, self._sesion, *args)

    def _accion_lista(self, _resultado) -> None:
        self._error_accion("")
        self.refresh()

    def _error_accion(self, mensaje: str) -> None:
        self.lbl_error.setText(mensaje)
        self.lbl_error.setVisible(bool(mensaje))


class CategoriasView(_TablaMaestra):
    ENCABEZADOS = ("Nombre", "Productos", "Estado")
    AYUDA = ("Las categorías de los productos. Renombrar una cambia también sus productos; desactivarla no borra "
             "nada, solo deja de ofrecerse para registros nuevos.")
    CLAVE_REFRESCO = "categorias"

    _cargar = staticmethod(maestros.listar_categorias)

    @staticmethod
    def _clave(dato: maestros.Categoria) -> str:
        return dato.nombre

    @staticmethod
    def _celdas(dato: maestros.Categoria) -> tuple[str, ...]:
        return dato.nombre, str(dato.productos), "Activa" if dato.activa else "Inactiva"

    @staticmethod
    def _activo(dato: maestros.Categoria) -> bool:
        return dato.activa

    def _nuevo(self) -> None:
        nombre = pedir_texto(self, "Nueva categoría", "Nombre de la categoría:")
        if nombre is not None:
            self._accion(maestros.crear_categoria, nombre)

    def _editar(self) -> None:
        dato = self._elegido()
        if dato is None:
            return
        nombre = pedir_texto(self, "Renombrar categoría", "Nombre nuevo (sus productos también cambian):", dato.nombre)
        if nombre is not None:
            self._accion(maestros.renombrar_categoria, dato.nombre, nombre)

    def _cambiar_estado(self) -> None:
        dato = self._elegido()
        if dato is not None:
            self._accion(maestros.activar_categoria, dato.nombre, not dato.activa)


class AlmacenesView(_TablaMaestra):
    ENCABEZADOS = ("Código", "Nombre", "Ubicación", "Estado")
    AYUDA = "Las bodegas donde están los productos. Desactivar un almacén no borra sus existencias."
    CLAVE_REFRESCO = "almacenes"

    _cargar = staticmethod(maestros.listar_almacenes)

    @staticmethod
    def _clave(dato: maestros.Almacen) -> str:
        return dato.codigo

    @staticmethod
    def _celdas(dato: maestros.Almacen) -> tuple[str, ...]:
        return dato.codigo, dato.nombre, dato.ubicacion, "Activo" if dato.activo else "Inactivo"

    @staticmethod
    def _activo(dato: maestros.Almacen) -> bool:
        return dato.activo

    def _nuevo(self) -> None:
        datos = pedir_almacen(self)
        if datos is not None:
            self._accion(maestros.crear_almacen, *datos)

    def _editar(self) -> None:
        dato = self._elegido()
        if dato is None:
            return
        datos = pedir_almacen(self, dato)
        if datos is not None:
            self._accion(maestros.editar_almacen, dato.codigo, datos[1], datos[2])

    def _cambiar_estado(self) -> None:
        dato = self._elegido()
        if dato is not None:
            self._accion(maestros.activar_almacen, dato.codigo, not dato.activo)
