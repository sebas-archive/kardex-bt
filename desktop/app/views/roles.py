"""Pantalla «Roles y permisos»: la matriz módulo × rol, con un nivel por celda que se guarda en Oracle al cambiarlo."""

from __future__ import annotations

from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from .. import auth, permisos
from .base import QueryRunner, StateBanner


class RolesView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._combos: dict[tuple[str, str], QComboBox] = {}

        ayuda = QLabel("Qué puede hacer cada rol en cada módulo. «Consulta» lo ve; «Gestión» además cambia datos. "
                       "El cambio rige desde el próximo inicio de sesión de cada persona. El administrador siempre "
                       "gestiona usuarios, solicitudes y permisos.")
        ayuda.setObjectName("ayuda")
        ayuda.setWordWrap(True)
        self.banner = StateBanner()
        self.banner.retry.connect(self.refresh)
        self.tabla = QTableWidget(0, 1 + len(auth.ROLES))
        self.tabla.setHorizontalHeaderLabels(["Módulo"] + [auth.NOMBRE_ROL[r] for r in auth.ROLES])
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
        if sesion is None:   # al salir no queda la matriz en pantalla
            self._combos.clear()
            self.tabla.setRowCount(0)
        self.refresh()

    def set_conteo(self, id_conteo: str | None) -> None:
        """Los permisos no dependen del conteo."""

    def refresh(self) -> None:
        if self._sesion is None or not self._sesion.puede("permisos"):
            return
        self._runner.run(permisos.matriz, self._mostrar, self.banner.show_error, key="permisos")

    def combo(self, rol: str, modulo: str) -> QComboBox | None:
        return self._combos.get((rol, modulo))

    # ------------------------------------------------------------- internos
    def _mostrar(self, matriz: dict[tuple[str, str], str]) -> None:
        self.banner.clear()
        editable = self._sesion is not None and self._sesion.puede("permisos", permisos.GESTION)
        self._combos.clear()
        self.tabla.setRowCount(len(permisos.MODULOS))
        for fila, (clave, nombre) in enumerate(permisos.MODULOS):
            en_uso = clave in permisos.EN_USO
            self.tabla.setItem(fila, 0, QTableWidgetItem(nombre if en_uso else f"{nombre} (próximamente)"))
            for columna, rol in enumerate(auth.ROLES, start=1):
                combo = QComboBox()
                for nivel in permisos.NIVELES:
                    combo.addItem(permisos.NOMBRE_NIVEL[nivel], nivel)
                combo.setCurrentIndex(combo.findData(matriz[(rol, clave)]))
                combo.setEnabled(editable and en_uso and (rol, clave) not in permisos.INTOCABLES)
                if (rol, clave) in permisos.INTOCABLES:
                    combo.setToolTip("El administrador siempre gestiona este módulo.")
                elif not en_uso:
                    combo.setToolTip("Este módulo llega en una fase siguiente: su permiso todavía no rige.")
                combo.currentIndexChanged.connect(lambda _i, r=rol, m=clave, c=combo: self._guardar(r, m, c.currentData()))
                self.tabla.setCellWidget(fila, columna, combo)
                self._combos[(rol, clave)] = combo

    def _guardar(self, rol: str, modulo: str, nivel: str) -> None:
        # Si falla (p. ej. sin permiso), se muestra el error y se vuelve a leer la matriz para no mentir en pantalla.
        self._runner.run(permisos.guardar, lambda _: None, self._fallo, self._sesion, rol, modulo, nivel)

    def _fallo(self, mensaje: str) -> None:
        self.banner.show_error(mensaje)
        self.refresh()
