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
from PyQt6.QtWidgets import (QBoxLayout, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from .. import auth, configuracion, i18n
from ..i18n import registrar, t
from ..tema import NOMBRE_MODO
from . import components
from .base import QueryRunner
from .iconos import icono
from .isla import isla
from .foto import (EditorFoto, borrar_perfil, elegir_imagen, formato_valido, guardar_perfil, pixmap_avatar,
                   pixmap_inicial)

registrar({
    "Seguridad de la cuenta": "Account security", "Preferencias": "Preferences",
    "Tu cuenta, tu seguridad y tus preferencias.": "Your account, security and preferences.",
    "Elige cómo se ve la aplicación.": "Choose how the app looks.", "Idioma": "Language",
    "Cerrar sesión": "Sign out", "Mostrar contraseña": "Show password", "Ocultar contraseña": "Hide password",
})

ANCHO_MAXIMO = 1080
ANCHO_DOS_COLUMNAS = 820
ANCHO_TARJETA_HORIZONTAL = 700


class Segmentado(QFrame):
    """Control segmentado estilo macOS: una fila de opciones excluyentes con la elegida resaltada."""

    cambiado = pyqtSignal(int)

    def __init__(self, opciones: list[tuple[str, str | None]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("segmentado")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)
        self._botones: list[QPushButton] = []
        for i, (texto, nombre_icono) in enumerate(opciones):
            b = QPushButton(" " + texto if nombre_icono else texto)
            b.setObjectName("segmento")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if nombre_icono:
                b.setIcon(icono(nombre_icono, tam=16))
            self._grupo.addButton(b, i)
            self._botones.append(b)
            lay.addWidget(b, 1)
        self._grupo.idClicked.connect(self.cambiado)

    def poner(self, indice: int) -> None:
        if 0 <= indice < len(self._botones):
            self._botones[indice].setChecked(True)


def _con_icono(nombre: str, etiqueta: QLabel) -> QWidget:
    """Una línea de datos: icono discreto y su texto."""
    caja = QWidget()
    caja.setObjectName("filaIcono")
    lay = QHBoxLayout(caja)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    marca = QLabel()
    marca.setObjectName("subtitulo")
    marca.setPixmap(icono(nombre, tam=15).pixmap(15, 15))
    marca.setFixedWidth(16)
    lay.addWidget(marca)
    lay.addWidget(etiqueta, 1)
    return caja


def _separador() -> QFrame:
    linea = QFrame()
    linea.setObjectName("separadorSuave")
    linea.setFixedHeight(1)
    return linea


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

        # ---------------------------------------------------------- tarjeta del usuario
        self.lbl_avatar = QLabel()
        self.lbl_avatar.setObjectName("avatarGrande")
        self.lbl_avatar.setFixedSize(80, 80)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_nombre = QLabel("")
        self.lbl_nombre.setObjectName("perfilNombre")
        self.lbl_usuario = QLabel("")
        self.lbl_usuario.setObjectName("subtitulo")
        self.lbl_correo = QLabel("")
        self.lbl_correo.setObjectName("subtitulo")
        self.lbl_rol = QLabel("")
        self.lbl_rol.setObjectName("insignia")
        self.lbl_foto_aviso = QLabel("")
        self.lbl_foto_aviso.setWordWrap(True)
        self.lbl_foto_aviso.hide()
        self._fila_correo = _con_icono("correo", self.lbl_correo)
        fila_rol = QHBoxLayout()
        fila_rol.setContentsMargins(0, 2, 0, 0)
        fila_rol.addWidget(self.lbl_rol)
        fila_rol.addStretch(1)
        datos = QVBoxLayout()
        datos.setSpacing(4)
        datos.addStretch(1)
        datos.addWidget(self.lbl_nombre)
        datos.addWidget(_con_icono("usuario", self.lbl_usuario))
        datos.addWidget(self._fila_correo)
        datos.addLayout(fila_rol)
        datos.addWidget(self.lbl_foto_aviso)
        datos.addStretch(1)

        self.btn_foto = QPushButton(" " + t("Cambiar foto"))
        self.btn_foto.setIcon(icono("usuario", tam=16))
        self.btn_quitar_foto = QPushButton(" " + t("Eliminar foto"))
        self.btn_quitar_foto.setObjectName("peligro")
        self.btn_salir = QPushButton(" " + t("Cerrar sesión"))
        self.btn_salir.setIcon(icono("salir", tam=16))
        for boton in (self.btn_foto, self.btn_quitar_foto, self.btn_salir):
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
        self._acciones = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._acciones.setSpacing(8)
        self._acciones.addWidget(self.btn_foto)
        self._acciones.addWidget(self.btn_quitar_foto)
        self._acciones.addWidget(self.btn_salir)

        tarjeta_usuario = QFrame()
        tarjeta_usuario.setObjectName("card")
        self._lay_usuario = QBoxLayout(QBoxLayout.Direction.LeftToRight, tarjeta_usuario)
        self._lay_usuario.setContentsMargins(24, 20, 24, 20)
        self._lay_usuario.setSpacing(20)
        self._lay_usuario.addWidget(self.lbl_avatar, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lay_usuario.addLayout(datos, 1)
        self._lay_usuario.addLayout(self._acciones)

        # ---------------------------------------------------------- seguridad
        self.lbl_clave_ayuda = QLabel("")
        self.lbl_clave_ayuda.setObjectName("ayuda")
        self.lbl_clave_ayuda.setWordWrap(True)
        self.txt_actual = self._clave(t("Contraseña actual"))
        self.txt_nueva = self._clave(t("Contraseña nueva (mínimo 8, con letras y números)"))
        self.txt_confirmacion = self._clave(t("Repite la contraseña nueva"))
        self.btn_cambiar = QPushButton(t("Cambiar contraseña"))
        self.btn_cambiar.setObjectName("primario")
        self.btn_cambiar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_resultado = QLabel("")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.hide()
        fila_boton = QHBoxLayout()
        fila_boton.addStretch(1)
        fila_boton.addWidget(self.btn_cambiar)
        tarjeta_clave = self._tarjeta(t("Seguridad de la cuenta"), self.lbl_clave_ayuda, self.txt_actual,
                                      self.txt_nueva, self.txt_confirmacion, fila_boton, self.lbl_resultado)

        # ---------------------------------------------------------- preferencias
        self.combo_tema = QComboBox()
        for modo in ("claro", "sistema", "oscuro"):
            self.combo_tema.addItem(t(NOMBRE_MODO[modo]), modo)
        self.combo_idioma = QComboBox()
        for codigo, nombre in (("es", "Español"), ("en", "English")):
            self.combo_idioma.addItem(t(nombre), codigo)
        # La lógica de siempre vive en los combos (ocultos); los controles segmentados los gobiernan y los reflejan.
        self.combo_tema.hide()
        self.combo_idioma.hide()
        iconos_tema = {"claro": "sol", "sistema": "contraste", "oscuro": "luna"}
        self.seg_tema = Segmentado([(self.combo_tema.itemText(i), iconos_tema[self.combo_tema.itemData(i)])
                                    for i in range(self.combo_tema.count())])
        self.seg_idioma = Segmentado([(self.combo_idioma.itemText(i), None) for i in range(self.combo_idioma.count())])
        self.seg_tema.cambiado.connect(self.combo_tema.setCurrentIndex)
        self.seg_idioma.cambiado.connect(self.combo_idioma.setCurrentIndex)
        self.combo_tema.currentIndexChanged.connect(self.seg_tema.poner)
        self.combo_idioma.currentIndexChanged.connect(self.seg_idioma.poner)
        self.lbl_pref = QLabel("")
        self.lbl_pref.setWordWrap(True)
        self.lbl_pref.hide()
        apariencia = QLabel(t("Apariencia"))
        apariencia.setObjectName("seccion")
        ayuda_tema = QLabel(t("Elige cómo se ve la aplicación."))
        ayuda_tema.setObjectName("ayuda")
        idioma = QLabel(t("Idioma"))
        idioma.setObjectName("seccion")
        tarjeta_pref = self._tarjeta(t("Preferencias"), apariencia, ayuda_tema, self.seg_tema, _separador(), idioma,
                                     self.seg_idioma, self.combo_tema, self.combo_idioma, self.lbl_pref)

        # ---------------------------------------------------------- página: ancho máximo y centrada
        descripcion = QLabel(t("Tu cuenta, tu seguridad y tus preferencias."))
        descripcion.setObjectName("subtitulo")
        self._columnas = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._columnas.setSpacing(16)
        for tarjeta in (tarjeta_clave, tarjeta_pref):
            self._columnas.addWidget(tarjeta, 1, Qt.AlignmentFlag.AlignTop)
        pagina = QWidget()
        pagina.setMaximumWidth(ANCHO_MAXIMO)
        lay_pagina = QVBoxLayout(pagina)
        lay_pagina.setContentsMargins(0, 0, 0, 12)
        lay_pagina.setSpacing(16)
        lay_pagina.addWidget(descripcion)
        lay_pagina.addWidget(tarjeta_usuario)
        lay_pagina.addLayout(self._columnas)
        lay_pagina.addStretch(1)
        centro = QWidget()
        lay_centro = QHBoxLayout(centro)
        lay_centro.setContentsMargins(4, 4, 4, 4)
        lay_centro.addStretch(1)
        lay_centro.addWidget(pagina, 100)
        lay_centro.addStretch(1)
        desplazable = QScrollArea()
        desplazable.setWidgetResizable(True)
        desplazable.setFrameShape(QFrame.Shape.NoFrame)
        desplazable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        desplazable.setWidget(centro)
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 0)
        raiz.addWidget(desplazable)

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
        campo.addAction(icono("candado", tam=16), QLineEdit.ActionPosition.LeadingPosition)
        ojo = campo.addAction(icono("ojo", tam=16), QLineEdit.ActionPosition.TrailingPosition)
        ojo.setToolTip(t("Mostrar contraseña"))

        def alternar() -> None:
            visible = campo.echoMode() == QLineEdit.EchoMode.Normal
            campo.setEchoMode(QLineEdit.EchoMode.Password if visible else QLineEdit.EchoMode.Normal)
            ojo.setIcon(icono("ojo" if visible else "ojo_off", tam=16))
            ojo.setToolTip(t("Mostrar contraseña") if visible else t("Ocultar contraseña"))
        ojo.triggered.connect(alternar)
        return campo

    @staticmethod
    def _tarjeta(titulo: str, *contenido) -> QFrame:
        tarjeta = QFrame()
        tarjeta.setObjectName("card")
        lay = QVBoxLayout(tarjeta)
        lay.setContentsMargins(22, 20, 22, 20)
        lay.setSpacing(12)
        rotulo = QLabel(titulo)
        rotulo.setObjectName("tituloTarjeta")
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
        self.btn_foto.setText(" " + (t("Cambiar foto") if sesion.foto else t("Poner foto")))
        self.btn_quitar_foto.setEnabled(bool(sesion.foto))
        self.lbl_nombre.setText(sesion.nombre)
        self.lbl_usuario.setText(f"@{sesion.usuario}")
        self.lbl_correo.setText(sesion.correo or "")
        self._fila_correo.setVisible(bool(sesion.correo))
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
        self.seg_tema.poner(self.combo_tema.currentIndex())
        self.seg_idioma.poner(self.combo_idioma.currentIndex())
        self._cargar_max_mb()
        self.refresh()

    def resizeEvent(self, evento) -> None:
        """Dos columnas en ventanas amplias; en las pequeñas todo se apila y los botones bajan a su propia fila."""
        super().resizeEvent(evento)
        ancho = self.width()
        self._columnas.setDirection(QBoxLayout.Direction.LeftToRight if ancho >= ANCHO_DOS_COLUMNAS
                                    else QBoxLayout.Direction.TopToBottom)
        horizontal = ancho >= ANCHO_TARJETA_HORIZONTAL
        self._lay_usuario.setDirection(QBoxLayout.Direction.LeftToRight if horizontal else QBoxLayout.Direction.TopToBottom)
        self._acciones.setDirection(QBoxLayout.Direction.LeftToRight)

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
        mapa = pixmap_avatar(self._foto, 76)
        if mapa is None:
            mapa = pixmap_inicial(self._sesion.nombre, 76)
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
        self.btn_foto.setText(" " + t("Cambiar foto"))
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
        self.btn_foto.setText(" " + t("Poner foto"))
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
