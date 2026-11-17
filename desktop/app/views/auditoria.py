"""Pantalla «Auditoría»: quién hizo qué y cuándo (solo consulta). La matriz decide quién entra."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import auditoria, auth
from ..i18n import registrar, t
from . import motion_global
from .base import QueryRunner, StateBanner
from .selector_fecha import SelectorFecha

registrar({
    "Quién hizo qué y cuándo: cuentas, permisos, inicios de sesión y la operación diaria.":
        "Who did what and when: accounts, permissions, sign-ins and daily operations.",
    "Todos los usuarios": "All users",
    "Todos los módulos": "All modules",
    "Buscar en la acción o el detalle": "Search the action or detail",
    "Desde": "From",
    "Hasta": "To",
    "Fecha": "Date",
    "Usuario": "User",
    "Módulo": "Module",
    "Acción": "Action",
    "Detalle": "Detail",
    "Todavía no hay acciones registradas.": "No actions have been recorded yet.",
    "Ninguna acción coincide con los filtros.": "No action matches the filters.",
})

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
        self.combo_usuario.addItem(t("Todos los usuarios"), None)
        self.combo_modulo.addItem(t("Todos los módulos"), None)
        self.fecha_desde = SelectorFecha(QDate.currentDate().addDays(-30))
        self.fecha_hasta = SelectorFecha(QDate.currentDate())
        SelectorFecha.vincular(self.fecha_desde, self.fecha_hasta)     # «Desde» no puede pasar de «Hasta»
        self.txt_buscar = QLineEdit()
        self.txt_buscar.setPlaceholderText(t("Buscar en la acción o el detalle"))
        filtros = QHBoxLayout()
        filtros.addWidget(self.txt_buscar, 1)
        for w in (self.combo_usuario, self.combo_modulo, QLabel(t("Desde")), self.fecha_desde, QLabel(t("Hasta")),
                  self.fecha_hasta):
            filtros.addWidget(w)

        self.tabla = QTableWidget(0, len(ENCABEZADOS))
        self.tabla.setHorizontalHeaderLabels([t(c) for c in ENCABEZADOS])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(34)
        # Las columnas cortas se ajustan a su contenido y «Detalle» absorbe todo el ancho que sobra, así la tabla
        # siempre llena su área (con resizeColumnsToContents() la última columna perdía el estiramiento).
        cabecera = self.tabla.horizontalHeader()
        cabecera.setStretchLastSection(True)
        for columna in range(len(ENCABEZADOS) - 1):
            cabecera.setSectionResizeMode(columna, QHeaderView.ResizeMode.ResizeToContents)
        cabecera.setSectionResizeMode(len(ENCABEZADOS) - 1, QHeaderView.ResizeMode.Stretch)
        self._vivas = motion_global.FilasVivas(self.tabla)
        self._actividad = motion_global.Actividad(self, self._runner)
        motion_global.instalar_realces(self.txt_buscar, self.combo_usuario, self.combo_modulo)

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
        self.lbl_ayuda.setText(t("Quién hizo qué y cuándo: cuentas, permisos, inicios de sesión y la operación diaria."))
        if sesion is None:
            self._mostrar([])
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("auditoria"):
            return
        self._runner.run(auditoria.listar, self._mostrar, self.banner.show_error, self._sesion, key="auditoria")

    def filas(self) -> list[tuple[str, ...]]:
        return [tuple(self.tabla.item(f, c).text() if self.tabla.item(f, c) else "" for c in range(len(ENCABEZADOS)))
                for f in range(self.tabla.rowCount())]

    def entrada_motion(self) -> None:
        """Entrada de la pantalla (la llama ``motion_global.entrada_pagina``): ayuda, estado y filtros en cascada; la
        tabla revela sus filas sin moverlas."""
        motion_global.entrada_cascada([self.lbl_ayuda, self.banner, self.txt_buscar, self.combo_usuario,
                                       self.combo_modulo, self.fecha_desde, self.fecha_hasta], [self._vivas])

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
        self._rellenar(self.combo_modulo, sorted({(e.modulo, t(auditoria.NOMBRE_MODULO.get(e.modulo, e.modulo)))
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
        antes = self._vivas.capturar()
        self.tabla.setRowCount(len(vistas))
        claves = []
        for fila, e in enumerate(vistas):
            celdas = (f"{e.fecha:%d/%m/%Y %H:%M:%S}", e.nombre, t(auditoria.NOMBRE_MODULO.get(e.modulo, e.modulo)),
                      t(e.accion), e.detalle)
            for columna, valor in enumerate(celdas):
                self.tabla.setItem(fila, columna, QTableWidgetItem(valor))
            claves.append("\x1f".join(celdas))
        # Un registro histórico no cambia: su clave es su contenido, así que solo entran o salen filas (ninguna se reescribe).
        self._vivas.revelar(antes, claves, [""] * len(claves))
        if not self._todas:
            self.banner.show_empty(t("Todavía no hay acciones registradas."))
        elif not vistas:
            self.banner.show_empty(t("Ninguna acción coincide con los filtros."))
        else:
            self.banner.clear()
