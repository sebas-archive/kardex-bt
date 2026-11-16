"""Pantalla «Perfil»: identidad, foto con editor, tema, idioma, contraseña y cierre de sesión.

Cada usuario cambia solo su propia foto. El Administrador cambia su contraseña directo; Inventario deja la
solicitud para que el Administrador la apruebe en Solicitudes. Tema e idioma se guardan por usuario y se aplican
de inmediato (``main.py`` escucha las señales).
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                             QWidget)

from .. import auth, configuracion, i18n
from ..i18n import t
from ..tema import NOMBRE_MODO
from . import components
from .base import QueryRunner
from .isla import isla
from .foto import (EditorFoto, borrar_perfil, elegir_imagen, formato_valido, guardar_perfil, pixmap_avatar,
                   pixmap_inicial)


class PerfilView(QWidget):
    cerrar_sesion = pyqtSignal()
    tema_cambiado = pyqtSignal(str)
    idioma_cambiado = pyqtSignal(str)
    foto_cambiada = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._max_mb = 2
        self._foto: str | None = None

        self.lbl_avatar = QLabel()
        self.lbl_avatar.setObjectName("avatarGrande")
        self.lbl_avatar.setFixedSize(96, 96)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_nombre = QLabel("")
        self.lbl_nombre.setObjectName("tituloPagina")
        self.lbl_usuario = QLabel("")
        self.lbl_usuario.setObjectName("subtitulo")
        self.lbl_correo = QLabel("")
        self.lbl_correo.setObjectName("subtitulo")
        self.lbl_rol = QLabel("")
        self.lbl_rol.setObjectName("insignia")
        self.lbl_foto_aviso = QLabel("")
        self.lbl_foto_aviso.setWordWrap(True)
        self.lbl_foto_aviso.hide()
        datos = QVBoxLayout()
        datos.setSpacing(2)
        datos.addWidget(self.lbl_nombre)
        fila = QHBoxLayout()
        fila.addWidget(self.lbl_usuario)
        fila.addWidget(self.lbl_rol)
        fila.addStretch(1)
        datos.addLayout(fila)
        datos.addWidget(self.lbl_correo)
        datos.addWidget(self.lbl_foto_aviso)
        self.btn_foto = QPushButton(t("Cambiar foto"))
        self.btn_quitar_foto = QPushButton(t("Eliminar foto"))
        self.btn_quitar_foto.setObjectName("peligro")
        fotos_botones = QHBoxLayout()
        fotos_botones.setSpacing(8)
        fotos_botones.addWidget(self.btn_foto)
        fotos_botones.addWidget(self.btn_quitar_foto)
        self.btn_salir = QPushButton(t("Cerrar sesión"))
        self.btn_salir.setObjectName("peligro")
        fotos_botones.addWidget(self.btn_salir)
        datos.insertStretch(0, 1)
        datos.addStretch(1)
        cabecera = QHBoxLayout()
        cabecera.setSpacing(16)
        cabecera.addWidget(self.lbl_avatar)
        cabecera.addLayout(datos, 1)
        cabecera.addLayout(fotos_botones)
        cabecera.setAlignment(fotos_botones, Qt.AlignmentFlag.AlignVCenter)

        # ---------------------------------------------------------- contraseña
        self.lbl_clave_ayuda = QLabel("")
        self.lbl_clave_ayuda.setObjectName("ayuda")
        self.lbl_clave_ayuda.setWordWrap(True)
        self.txt_actual = self._clave(t("Contraseña actual"))
        self.txt_nueva = self._clave(t("Contraseña nueva (mínimo 8, con letras y números)"))
        self.txt_confirmacion = self._clave(t("Repite la contraseña nueva"))
        self.btn_cambiar = QPushButton(t("Cambiar contraseña"))
        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.hide()
        fila_boton = QHBoxLayout()
        fila_boton.addWidget(self.btn_cambiar)
        fila_boton.addStretch(1)
        tarjeta_clave = self._tarjeta(t("Contraseña"), self.lbl_clave_ayuda, self.txt_actual, self.txt_nueva,
                                      self.txt_confirmacion, fila_boton, self.lbl_resultado)
        tarjeta_clave.setMaximumWidth(480)

        # ---------------------------------------------------------- preferencias
        self.combo_tema = QComboBox()
        for modo in ("claro", "sistema", "oscuro"):
            self.combo_tema.addItem(t(NOMBRE_MODO[modo]), modo)
        self.combo_idioma = QComboBox()
        for codigo, nombre in (("es", "Español"), ("en", "English")):
            self.combo_idioma.addItem(t(nombre), codigo)
        tarjeta_pref = self._tarjeta(t("Apariencia"), QLabel(t("Tema")), self.combo_tema,
                                     QLabel(t("Idioma")), self.combo_idioma)
        tarjeta_pref.setMaximumWidth(480)
        self.lbl_pref = QLabel("")
        self.lbl_pref.setWordWrap(True)
        self.lbl_pref.hide()

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(4, 4, 4, 4)
        raiz.setSpacing(16)
        raiz.addLayout(cabecera)
        columnas = QHBoxLayout()
        columnas.setSpacing(16)
        columna = QVBoxLayout()
        columna.setSpacing(16)
        columna.addWidget(tarjeta_clave)
        columna.addWidget(tarjeta_pref)
        columna.addWidget(self.lbl_pref)
        columna.addStretch(1)
        columnas.addLayout(columna, 1)
        columnas.addStretch(1)
        raiz.addLayout(columnas)
        raiz.addStretch(1)

        self.btn_salir.clicked.connect(self.cerrar_sesion)
        self.btn_cambiar.clicked.connect(self._cambiar)
        self.txt_confirmacion.returnPressed.connect(self._cambiar)
        self.btn_foto.clicked.connect(self._elegir_foto)
        self.btn_quitar_foto.clicked.connect(self._quitar_foto)
        self.combo_tema.currentIndexChanged.connect(self._guardar_tema)
        self.combo_idioma.currentIndexChanged.connect(self._guardar_idioma)

    @staticmethod
    def _clave(pista: str) -> QLineEdit:
        campo = QLineEdit()
        campo.setPlaceholderText(pista)
        campo.setEchoMode(QLineEdit.EchoMode.Password)
        return campo

    @staticmethod
    def _tarjeta(titulo: str, *contenido) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("seccion")
        lay.addWidget(rotulo)
        for pieza in contenido:
            if isinstance(pieza, QHBoxLayout):
                lay.addLayout(pieza)
            else:
                lay.addWidget(pieza)
        return tarjeta

    # ------------------------------------------------- contrato de las vistas
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        for campo in (self.txt_actual, self.txt_nueva, self.txt_confirmacion):
            campo.clear()
        self.lbl_resultado.hide()
        self.lbl_pref.hide()
        if sesion is None:
            self._foto = None
            self.lbl_avatar.setPixmap(QPixmap())
            self.lbl_avatar.setText("")
            return
        self._foto = sesion.foto
        self.btn_foto.setText(t("Cambiar foto") if sesion.foto else t("Poner foto"))
        self.btn_quitar_foto.setEnabled(bool(sesion.foto))
        self.lbl_nombre.setText(sesion.nombre)
        self.lbl_usuario.setText(f"@{sesion.usuario}")
        self.lbl_correo.setText(sesion.correo or "")
        self.lbl_rol.setText(t(auth.NOMBRE_ROL[sesion.rol]))
        self.lbl_rol.setProperty("estado", sesion.rol)
        self.lbl_rol.style().unpolish(self.lbl_rol)
        self.lbl_rol.style().polish(self.lbl_rol)
        self._pintar_avatar()
        admin = sesion.es_admin
        self.btn_cambiar.setText(t("Cambiar contraseña") if admin else t("Solicitar cambio de contraseña"))
        self.lbl_clave_ayuda.setText(
            t("Tu contraseña cambia de inmediato.") if admin
            else t("El Administrador debe aprobar el cambio en Solicitudes."))
        self.combo_tema.blockSignals(True)
        self.combo_tema.setCurrentIndex(max(0, self.combo_tema.findData(sesion.tema)))
        self.combo_tema.blockSignals(False)
        self.combo_idioma.blockSignals(True)
        self.combo_idioma.setCurrentIndex(max(0, self.combo_idioma.findData(sesion.idioma)))
        self.combo_idioma.blockSignals(False)
        self._cargar_max_mb()
        self.refresh()

    def refresh(self) -> None:
        """Nada que consultar: los datos de la sesión ya están aquí."""

    def _cargar_max_mb(self) -> None:
        self._runner.run(configuracion.valores, self._max_mb_listo, lambda _m: None, key="perfilMaxFoto")

    def _max_mb_listo(self, valores: dict[str, str]) -> None:
        try:
            self._max_mb = int(valores.get("fotos.max_mb", "2"))
        except (TypeError, ValueError):
            self._max_mb = 2

    def _pintar_avatar(self) -> None:
        if self._sesion is None:
            return
        mapa = pixmap_avatar(self._foto, 48)
        if mapa is None:
            mapa = pixmap_inicial(self._sesion.nombre, 48)
        self.lbl_avatar.setPixmap(mapa)

    # ------------------------------------------------------------- contraseña
    def _cambiar(self) -> None:
        if self._sesion is None:
            return
        self.btn_cambiar.setEnabled(False)
        self._runner.run(auth.cambiar_clave, self._clave_lista, self._clave_fallo,
                         self._sesion.usuario, self.txt_actual.text(), self.txt_nueva.text(),
                         self.txt_confirmacion.text(), key="cambiarClave")

    def _clave_lista(self, mensaje: str) -> None:
        self.btn_cambiar.setEnabled(True)
        self._resultado(str(mensaje), True)
        for campo in (self.txt_actual, self.txt_nueva, self.txt_confirmacion):
            campo.clear()

    def _clave_fallo(self, mensaje: str) -> None:
        self.btn_cambiar.setEnabled(True)
        self._resultado(mensaje, False)

    def _resultado(self, mensaje: str, ok: bool) -> None:
        self.lbl_resultado.setText(t(mensaje))  # consultable; el aviso lo muestra la Isla
        if ok:
            isla.exito(t("Contraseña actualizada"), t(mensaje))
        else:
            isla.error(t("No se pudo cambiar la contraseña"), t(mensaje))

    # ------------------------------------------------------------- foto
    def _elegir_foto(self) -> None:
        if self._sesion is None:
            return
        ruta = elegir_imagen(self)
        if not ruta:
            return
        try:
            bytes_archivo = os.path.getsize(ruta)
        except OSError:
            self._aviso_foto(t("La imagen no se pudo leer."), True)
            return
        if bytes_archivo > self._max_mb * 1024 * 1024:
            self._aviso_foto(t("El archivo supera el tamaño máximo de {mb} MB.", mb=self._max_mb), True)
            return
        if not formato_valido(ruta):
            self._aviso_foto(t("Formato no admitido. Usa PNG, JPG, WEBP o BMP."), True)
            return
        imagen = QImage(ruta)
        if imagen.isNull():
            self._aviso_foto(t("La imagen no se pudo leer."), True)
            return
        editor = EditorFoto(imagen, self)
        if not editor.exec():
            return
        recorte = editor.resultado()
        if recorte.isNull():
            self._aviso_foto(t("La imagen no se pudo leer."), True)
            return
        self._guardar_foto(recorte)

    def _guardar_foto(self, imagen: QImage) -> None:
        if self._sesion is None:
            return
        try:
            ruta = guardar_perfil(self._sesion.usuario, imagen)
        except auth.ErrorDeAcceso as exc:
            self._aviso_foto(str(exc), True)
            return
        self._runner.run(auth.guardar_foto, lambda _: self._foto_lista(ruta), self._foto_fallo,
                         self._sesion.usuario, ruta, key="fotoPerfil")

    def _foto_lista(self, ruta: str) -> None:
        self._foto = ruta
        self._pintar_avatar()
        self.btn_foto.setText(t("Cambiar foto"))
        self.btn_quitar_foto.setEnabled(True)
        self.foto_cambiada.emit(ruta)
        self._aviso_foto(t("Foto de perfil actualizada."), False)

    def _foto_fallo(self, mensaje: str) -> None:
        self._aviso_foto(mensaje, True)

    def _quitar_foto(self) -> None:
        if self._sesion is None or not self._foto:
            return
        if not components.Confirmacion.pedir(self, t("Eliminar foto"), t("¿Eliminar tu foto de perfil?"),
                                             t("Eliminar"), requiere_entendido=False, peligro=True):
            return
        anterior = self._foto
        self._runner.run(auth.guardar_foto, lambda _: self._foto_borrada(anterior), self._foto_fallo,
                         self._sesion.usuario, None, key="fotoPerfil")

    def _foto_borrada(self, anterior: str) -> None:
        borrar_perfil(anterior)
        self._foto = None
        self._pintar_avatar()
        self.btn_foto.setText(t("Poner foto"))
        self.btn_quitar_foto.setEnabled(False)
        self.foto_cambiada.emit(None)
        self._aviso_foto(t("Se volverá a mostrar tu inicial."), False)

    def _aviso_foto(self, mensaje: str, error: bool) -> None:
        self.lbl_foto_aviso.setText(t(mensaje))  # consultable; el aviso lo muestra la Isla
        if error:
            isla.error(t("No se pudo actualizar la foto"), t(mensaje))
        else:
            isla.exito(t("Foto de perfil"), t(mensaje))

    # ------------------------------------------------------------- tema e idioma
    def _guardar_tema(self, _indice: int) -> None:
        if self._sesion is None:
            return
        modo = self.combo_tema.currentData()
        self._runner.run(auth.guardar_preferencias, lambda _v: self._tema_listo(modo),
                         lambda m: self._pref_fallo(m, self.combo_tema, self._sesion.tema),
                         self._sesion.usuario, modo, None, key="tema")

    def _tema_listo(self, modo: str) -> None:
        self.lbl_pref.hide()
        isla.info(t("Apariencia actualizada"))
        self.tema_cambiado.emit(modo)

    def _guardar_idioma(self, _indice: int) -> None:
        if self._sesion is None:
            return
        idioma = self.combo_idioma.currentData()
        self._runner.run(auth.guardar_preferencias, lambda _v: self._idioma_listo(idioma),
                         lambda m: self._pref_fallo(m, self.combo_idioma, self._sesion.idioma),
                         self._sesion.usuario, None, idioma, key="idioma")

    def _idioma_listo(self, idioma: str) -> None:
        self.lbl_pref.hide()
        isla.info(t("Idioma actualizado"))
        self.idioma_cambiado.emit(idioma)

    def _pref_fallo(self, mensaje: str, combo: QComboBox, anterior: str) -> None:
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, combo.findData(anterior)))
        combo.blockSignals(False)
        self.lbl_pref.setText(t("No se pudo guardar la preferencia.") + f" {mensaje}")
        isla.error(t("No se pudo guardar la preferencia"), mensaje)
