"""Pantalla «Roles y permisos»: la matriz de los doce módulos por rol.

Cada celda se guarda al cambiarla. La fila del Administrador está bloqueada entera (siempre Gestión). Si el
guardado falla, se muestra el error y se vuelve a leer la matriz para no mostrar algo que no quedó guardado.
"""

from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtWidgets import (QAbstractItemView, QComboBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from .. import auth, permisos
from ..i18n import t
from . import motion, motion_global, widgets
from .base import QueryRunner, StateBanner
from .isla import isla

ROJO = "#F87171"


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
        for columna in range(1, 1 + len(auth.ROLES)):   # cada rol con ancho fijo: el selector no se recorta
            self.tabla.horizontalHeader().setSectionResizeMode(columna, QHeaderView.ResizeMode.Fixed)
            self.tabla.setColumnWidth(columna, 190)

        self._ayuda = ayuda
        self._actividad = motion_global.Actividad(self, self._runner)

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
    def entrada_motion(self) -> None:
        """Entrada de la pantalla (la llama ``motion_global.entrada_pagina``): ayuda y estado en cascada y la matriz
        entra como una sola superficie."""
        motion_global.entrada_cascada([self._ayuda, self.banner, self.tabla])

    def _reutilizable(self) -> bool:
        """¿La matriz ya construida tiene exactamente los selectores de siempre (mismos roles y módulos)?"""
        claves = {(rol, clave) for clave, _n in permisos.MODULOS for rol in auth.ROLES}
        return (set(self._combos) == claves and self.tabla.rowCount() == len(permisos.MODULOS)
                and not any(sip.isdeleted(c) for c in self._combos.values()))

    def _mostrar(self, matriz: dict[tuple[str, str], str]) -> None:
        editable = self._sesion is not None and self._sesion.puede("permisos", permisos.GESTION)
        if self._reutilizable():
            # Misma matriz, datos nuevos: los selectores conservan su identidad y solo el que cambió se anima
            # (en rojo si se está revirtiendo un guardado que falló).
            color = ROJO if self._error else motion.VERDE
            for (rol, clave), combo in self._combos.items():
                nuevo = combo.findData(matriz[(rol, clave)])
                bloqueada = rol == auth.ADMIN or (rol, clave) in permisos.INTOCABLES
                combo.setEnabled(editable and not bloqueada)
                if nuevo != combo.currentIndex():
                    combo.blockSignals(True)          # reflejar lo guardado no es un cambio del usuario: no se re-guarda
                    combo.setCurrentIndex(nuevo)
                    combo.blockSignals(False)
                    motion.destello(combo, color, radio=8)
            self._cerrar_error()
            return
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
                    lambda _i, r=rol, m=clave, c=combo: self._guardar(r, m, c.currentData(), c))
                motion_global.instalar_realce(combo)
                self.tabla.setCellWidget(fila, columna, combo)
                self._combos[(rol, clave)] = combo
        self._cerrar_error()

    def _cerrar_error(self) -> None:
        if self._error:
            self.banner.show_error(self._error)
            self._error = ""
        else:
            self.banner.clear()

    def _guardar(self, rol: str, modulo: str, nivel: str, combo: QComboBox | None = None) -> None:
        # Si falla (p. ej. sin permiso), se muestra el error y se vuelve a leer la matriz para no mentir en pantalla.
        self.banner.clear()
        if combo is not None and not sip.isdeleted(combo):
            motion.destello(combo, motion.VERDE, 520, radio=8)    # respuesta inmediata: el cambio se registró en pantalla
        self._runner.run(permisos.guardar, lambda _: isla.exito(t("Permiso actualizado")), self._fallo,
                         self._sesion, rol, modulo, nivel, key="guardarPermiso")

    def _fallo(self, mensaje: str) -> None:
        self._error = t("No se pudo guardar el cambio. Se volvió a leer la matriz.") + f" {mensaje}"
        self.refresh()
