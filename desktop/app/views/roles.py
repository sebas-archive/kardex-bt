"""Pantalla «Roles y permisos»: la matriz de los doce módulos por rol.

Cada celda se guarda al cambiarla. La fila del Administrador está bloqueada entera (siempre Gestión). Si el
guardado falla, se muestra el error y se vuelve a leer la matriz para no mostrar algo que no quedó guardado.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from .. import auth, permisos
from ..i18n import t
from .base import QueryRunner, StateBanner
from .isla import isla


class RolesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._combos: dict[tuple[str, str], QComboBox] = {}
        self._error = ""

        ayuda = QLabel(t("Qué puede hacer cada rol en cada módulo. «Consulta» lo ve; «Gestión» además cambia datos. "
                         "El cambio rige desde el próximo inicio de sesión de cada persona. El Administrador siempre "
                         "gestiona los doce módulos y su fila está bloqueada."))
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.tabla = QTableWidget(0, 1 + len(auth.ROLES))
        self.tabla.setHorizontalHeaderLabels(
            [t("Módulo")] + [t(auth.NOMBRE_ROL[r]) for r in auth.ROLES])
        self.tabla.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabla.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabla.verticalHeader().hide()
        self.tabla.verticalHeader().setDefaultSectionSize(40)
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(12)
        raiz.addWidget(ayuda)
        raiz.addWidget(self.banner)
        raiz.addWidget(self.tabla, 1)

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._combos.clear()
            self.tabla.setRowCount(0)
        self.refresh()

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("permisos"):
            return
        self._runner.run(permisos.matriz, self._mostrar, self.banner.show_error, key="permisos")

    def combo(self, rol: str, modulo: str) -> QComboBox | None:
        return self._combos.get((rol, modulo))

    # ------------------------------------------------------------- internos
    def _mostrar(self, matriz: dict[tuple[str, str], str]) -> None:
        editable = self._sesion is not None and self._sesion.puede("permisos", permisos.GESTION)
        self._combos.clear()
        self.tabla.setRowCount(len(permisos.MODULOS))
        for fila, (clave, nombre) in enumerate(permisos.MODULOS):
            self.tabla.setItem(fila, 0, QTableWidgetItem(t(nombre)))
            for columna, rol in enumerate(auth.ROLES, start=1):
                combo = QComboBox()
                for nivel in permisos.NIVELES:
                    combo.addItem(t(permisos.NOMBRE_NIVEL[nivel]), nivel)
                combo.setCurrentIndex(combo.findData(matriz[(rol, clave)]))
                bloqueada = rol == auth.ADMIN or (rol, clave) in permisos.INTOCABLES
                combo.setEnabled(editable and not bloqueada)
                if bloqueada:
                    combo.setToolTip(t("La fila del Administrador está bloqueada: siempre tiene Gestión."))
                combo.currentIndexChanged.connect(
                    lambda _i, r=rol, m=clave, c=combo: self._guardar(r, m, c.currentData()))
                self.tabla.setCellWidget(fila, columna, combo)
                self._combos[(rol, clave)] = combo
        if self._error:
            self.banner.show_error(self._error)
            self._error = ""
        else:
            self.banner.clear()

    def _guardar(self, rol: str, modulo: str, nivel: str) -> None:
        # Si falla (p. ej. sin permiso), se muestra el error y se vuelve a leer la matriz para no mentir en pantalla.
        self.banner.clear()
        self._runner.run(permisos.guardar, lambda _: isla.exito(t("Permiso actualizado")), self._fallo,
                         self._sesion, rol, modulo, nivel, key="guardarPermiso")

    def _fallo(self, mensaje: str) -> None:
        self._error = t("No se pudo guardar el cambio. Se volvió a leer la matriz.") + f" {mensaje}"
        self.refresh()
