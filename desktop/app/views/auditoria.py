"""Pantalla «Auditoría»: quién hizo qué y cuándo (solo consulta). El Administrador ve todo; Inventario, la operación."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QDateEdit, QHBoxLayout, QLabel, QLineEdit, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auditoria, auth
from .base import QueryRunner, StateBanner

ENCABEZADOS = ("Fecha", "Usuario", "Módulo", "Acción", "Detalle")


class AuditoriaView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[auditoria.Entrada] = []

        self.lbl_ayuda = QLabel("")
        self.lbl_ayuda.setObjectName("ayuda")
        self.lbl_ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.combo_usuario, self.combo_modulo = QComboBox(), QComboBox()
        self.combo_usuario.addItem("Todos los usuarios", None)
        self.combo_modulo.addItem("Todos los módulos", None)
        self.fecha_desde, self.fecha_hasta = QDateEdit(), QDateEdit()
        for editor, dias in ((self.fecha_desde, 30), (self.fecha_hasta, 0)):
            editor.setCalendarPopup(True)
            editor.setDisplayFormat("dd/MM/yyyy")
            editor.setDate(QDate.currentDate().addDays(-dias))
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText("Buscar en la acción o el detalle")
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        for w in (self.combo_usuario, self.combo_modulo, QLabel("Desde"), self.fecha_desde, QLabel("Hasta"),
                  self.fecha_hasta):
            filtros.addWidget(w)

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
        raiz.addWidget(self.lbl_ayuda)
        raiz.addWidget(self.banner)
        raiz.addLayout(filtros)
        raiz.addWidget(self.tabla, 1)

        for combo in (self.combo_usuario, self.combo_modulo):
            combo.currentIndexChanged.connect(self._filtrar)
        for editor in (self.fecha_desde, self.fecha_hasta):
            editor.dateChanged.connect(self._filtrar)
        self.txt_buscar.textChanged.connect(self._filtrar)

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        self.lbl_ayuda.setText(
            "Quién hizo qué y cuándo: cuentas, permisos, inicios de sesión y la operación diaria."
            if sesion is not None and sesion.es_admin else
            "Quién hizo qué y cuándo en la operación: tareas, diferencias, movimientos, ajustes, categorías y almacenes.")
        if sesion is None:
            self._mostrar([])
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """No depende del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("historial"):
            return
        self._runner.run(auditoria.listar, self._mostrar, self.banner.show_error, self._sesion, key="auditoria")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() for c in range(len(ENCABEZADOS))) for f in range(self.tabla.rowCount())]

    # ------------------------------------------------------------- internos
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

    def _mostrar(self, datos: list[auditoria.Entrada]) -> None:
        self._todas = list(datos)
        self._rellenar(self.combo_usuario, sorted({(e.usuario, e.nombre) for e in self._todas}, key=lambda x: x[1]))
        self._rellenar(self.combo_modulo, sorted({(e.modulo, auditoria.NOMBRE_MODULO.get(e.modulo, e.modulo))
                                                  for e in self._todas}, key=lambda x: x[1]))
        self._filtrar()

    def _filtrar(self) -> None:
        usuario, modulo = self.combo_usuario.currentData(), self.combo_modulo.currentData()
        texto = self.txt_buscar.text().strip().lower()
        d, h = self.fecha_desde.date(), self.fecha_hasta.date()
        desde, hasta = date(d.year(), d.month(), d.day()), date(h.year(), h.month(), h.day())
        sin_tope = hasta >= date.today()
        vistas = [e for e in self._todas
                  if (usuario is None or e.usuario == usuario) and (modulo is None or e.modulo == modulo)
                  and e.fecha.date() >= desde and (sin_tope or e.fecha.date() <= hasta)
                  and (not texto or texto in e.accion.lower() or texto in e.detalle.lower())]
        self.tabla.setRowCount(len(vistas))
        for fila, e in enumerate(vistas):
            celdas = (f"{e.fecha:%d/%m/%Y %H:%M:%S}", e.nombre, auditoria.NOMBRE_MODULO.get(e.modulo, e.modulo),
                      e.accion, e.detalle)
            for columna, valor in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(valor))
        self.tabla.resizeColumnsToContents()
        if not self._todas:
            self.banner.show_empty("Todavía no hay acciones registradas.")
        elif not vistas:
            self.banner.show_empty("Ninguna acción coincide con los filtros.")
        else:
            self.banner.clear()
