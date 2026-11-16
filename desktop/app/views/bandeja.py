"""Notificaciones flotantes: la campana abre un panel emergente (Todas | Sin leer, «Marcar todas como leídas» y la
lista) y «Ver todo» abre la vista extendida, también flotante, sobre la ventana. Ya no son una pestaña de la barra.

El diseño sigue el «notification inbox popover»: pestañas arriba, lista con ● en las sin leer, pie con «Ver todo».
Los datos son los de siempre (``notificaciones.listar`` / ``marcar_leida`` / ``marcar_todas``).
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import auth, notificaciones, tema
from ..i18n import registrar, t
from . import iconos, motion
from .base import QueryRunner
from .isla import isla
from .notificaciones import SIN_LEER, TODAS, _fecha

registrar({
    "Ver todo": "View all",
    "Cerrar": "Close",
    "No se pudieron cargar las notificaciones": "Could not load the notifications",
})

MAX_EN_PANEL = 40


class _Fila(QFrame):
    """Una notificación en el panel: icono, texto, fecha y ● si está sin leer. Al pulsarla se marca como leída."""

    pulsada = pyqtSignal(object)

    def __init__(self, n: notificaciones.Notificacion) -> None:
        super().__init__()
        self._n = n
        self.setObjectName("filaBandeja")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        icono = QLabel()
        nombre = n.seccion if n.seccion in iconos._TRAZOS else "Notificaciones"
        icono.setPixmap(iconos.icono(nombre, tam=18).pixmap(18, 18))
        icono.setFixedWidth(22)
        icono.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        texto = QLabel(n.texto)
        texto.setObjectName("textoBandeja")
        texto.setWordWrap(True)
        texto.setProperty("sinleer", not n.leida)
        fecha = QLabel(_fecha(n.fecha))
        fecha.setObjectName("fechaBandeja")
        punto = QLabel("●" if not n.leida else "")
        punto.setObjectName("puntoBandeja")
        punto.setFixedWidth(12)
        punto.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        columna = QVBoxLayout()
        columna.setSpacing(2)
        columna.addWidget(texto)
        columna.addWidget(fecha)
        fila = QHBoxLayout(self)
        fila.setContentsMargins(12, 10, 12, 10)
        fila.setSpacing(10)
        fila.addWidget(icono)
        fila.addLayout(columna, 1)
        fila.addWidget(punto)

    def mousePressEvent(self, evento) -> None:
        if evento.button() == Qt.MouseButton.LeftButton:
            self.pulsada.emit(self._n)
        super().mousePressEvent(evento)


def _estilo(c: dict[str, str]) -> str:
    return f"""
    QFrame#bandeja {{ background: {c['tarjeta']}; border: 1px solid {c['borde']}; border-radius: 12px; }}
    QFrame#bandeja QLabel {{ background: transparent; color: {c['texto']}; }}
    QFrame#bandeja QScrollArea {{ background: transparent; border: none; }}
    QFrame#bandeja QWidget#cuerpoBandeja {{ background: transparent; }}
    QFrame#bandeja QFrame#cabeceraBandeja {{ background: transparent; border: none;
        border-bottom: 1px solid {c['borde']}; }}
    QFrame#bandeja QPushButton#pestana {{ background: transparent; border: none; border-radius: 8px; padding: 6px 12px;
        color: {c['texto_suave']}; font-weight: 600; }}
    QFrame#bandeja QPushButton#pestana:hover {{ background: {c['tarjeta_alt']}; }}
    QFrame#bandeja QPushButton#pestana:checked {{ background: {c['seleccion']}; color: {c['acento']}; }}
    QFrame#bandeja QPushButton#marcarTodas {{ background: transparent; border: none; color: {c['texto_suave']};
        font-size: 11px; font-weight: 600; padding: 4px; }}
    QFrame#bandeja QPushButton#marcarTodas:hover {{ color: {c['acento']}; text-decoration: underline; }}
    QFrame#bandeja QFrame#filaBandeja {{ background: transparent; border: none; border-bottom: 1px solid {c['borde']}; }}
    QFrame#bandeja QFrame#filaBandeja:hover {{ background: {c['tarjeta_alt']}; }}
    QFrame#bandeja QLabel#textoBandeja {{ color: {c['texto_suave']}; }}
    QFrame#bandeja QLabel#textoBandeja[sinleer="true"] {{ color: {c['texto_fuerte']}; font-weight: 700; }}
    QFrame#bandeja QLabel#fechaBandeja {{ color: {c['texto_tenue']}; font-size: 11px; }}
    QFrame#bandeja QLabel#puntoBandeja {{ color: {c['acento']}; font-size: 9px; }}
    QFrame#bandeja QLabel#vacioBandeja {{ color: {c['texto_suave']}; padding: 22px 12px; }}
    QFrame#bandeja QPushButton#verTodo {{ background: transparent; border: none; border-radius: 8px; padding: 8px;
        color: {c['acento']}; font-weight: 700; }}
    QFrame#bandeja QPushButton#verTodo:hover {{ background: {c['seleccion']}; }}
    """


class PopoverNotificaciones(QFrame):
    """Panel emergente de la campana. Se cierra solo al hacer clic fuera (es una ventana emergente de Qt)."""

    ver_todo = pyqtSignal()
    ir_a = pyqtSignal(str)      # una notificación con destino: el título de la pantalla
    cambiaron = pyqtSignal()    # se marcó algo como leído (la campana se actualiza)

    ANCHO = 440

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("bandeja")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self.ANCHO)
        self._runner = QueryRunner(self)
        self._sesion: auth.Sesion | None = None
        self._todas: list[notificaciones.Notificacion] = []
        self._solo_sin_leer = False

        self.btn_todas_tab = QPushButton(t(TODAS))
        self.btn_sin_leer_tab = QPushButton(t(SIN_LEER))
        for boton in (self.btn_todas_tab, self.btn_sin_leer_tab):
            boton.setObjectName("pestana")
            boton.setCheckable(True)
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_todas_tab.setChecked(True)
        self.btn_marcar = QPushButton(t("Marcar todas como leídas"))
        self.btn_marcar.setObjectName("marcarTodas")
        self.btn_marcar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_marcar.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        cabecera = QFrame()
        cabecera.setObjectName("cabeceraBandeja")
        en_cabecera = QHBoxLayout(cabecera)
        en_cabecera.setContentsMargins(10, 8, 10, 8)
        en_cabecera.setSpacing(4)
        en_cabecera.addWidget(self.btn_todas_tab)
        en_cabecera.addWidget(self.btn_sin_leer_tab)
        en_cabecera.addStretch(1)
        en_cabecera.addWidget(self.btn_marcar)

        self._cuerpo = QWidget()
        self._cuerpo.setObjectName("cuerpoBandeja")
        self._filas = QVBoxLayout(self._cuerpo)
        self._filas.setContentsMargins(0, 0, 0, 0)
        self._filas.setSpacing(0)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._cuerpo)
        self._scroll.setFixedHeight(340)
        self.btn_ver_todo = QPushButton(t("Ver todo"))
        self.btn_ver_todo.setObjectName("verTodo")
        self.btn_ver_todo.setCursor(Qt.CursorShape.PointingHandCursor)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(0, 0, 0, 6)
        raiz.setSpacing(0)
        raiz.addWidget(cabecera)
        raiz.addWidget(self._scroll)
        pie = QHBoxLayout()
        pie.setContentsMargins(8, 4, 8, 0)
        pie.addWidget(self.btn_ver_todo)
        raiz.addLayout(pie)

        self.btn_todas_tab.clicked.connect(lambda: self._pestana(False))
        self.btn_sin_leer_tab.clicked.connect(lambda: self._pestana(True))
        self.btn_marcar.clicked.connect(self._marcar_todas)
        self.btn_ver_todo.clicked.connect(self._pedir_todo)

    # ------------------------------------------------------------------ API
    def set_sesion(self, sesion: auth.Sesion | None) -> None:
        self._sesion = sesion
        if sesion is None:
            self._todas = []
            self.hide()

    def abrir(self, ancla: QWidget) -> None:
        """Muestra el panel bajo la campana y trae lo último."""
        if self._sesion is None or not self._sesion.puede("notificaciones"):
            return
        self.setStyleSheet(_estilo(tema.colores()))
        self.btn_todas_tab.setText(t(TODAS))
        self.btn_marcar.setText(t("Marcar todas como leídas"))
        self.btn_ver_todo.setText(t("Ver todo"))
        self._pintar()
        self._cargar()
        self.adjustSize()
        esquina = ancla.mapToGlobal(QPoint(0, ancla.height() + 8))
        pantalla = (QGuiApplication.screenAt(esquina) or QGuiApplication.primaryScreen()).availableGeometry()
        x = max(pantalla.left() + 8, min(esquina.x(), pantalla.right() - self.width() - 8))
        self.move(x, esquina.y())
        self.show()

    # ------------------------------------------------------------------ datos
    def _cargar(self) -> None:
        if self._sesion is None:
            return
        self._runner.run(notificaciones.listar, self._mostrar,
                         lambda m: isla.error(t("No se pudieron cargar las notificaciones"), m),
                         self._sesion, key="bandeja")

    def _mostrar(self, lista) -> None:
        self._todas = list(lista)
        self._pintar()

    def _pestana(self, solo_sin_leer: bool) -> None:
        self._solo_sin_leer = solo_sin_leer
        self.btn_todas_tab.setChecked(not solo_sin_leer)
        self.btn_sin_leer_tab.setChecked(solo_sin_leer)
        self._pintar()

    def _pintar(self) -> None:
        sin_leer = sum(1 for n in self._todas if not n.leida)
        self.btn_sin_leer_tab.setText(f"{t(SIN_LEER)} ({sin_leer})" if sin_leer else t(SIN_LEER))
        self.btn_marcar.setVisible(sin_leer > 0)
        visibles = [n for n in self._todas if not (self._solo_sin_leer and n.leida)][:MAX_EN_PANEL]
        while self._filas.count():
            item = self._filas.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not visibles:
            vacio = QLabel(t("No hay notificaciones sin leer.") if self._solo_sin_leer else t("Aún no hay notificaciones."))
            vacio.setObjectName("vacioBandeja")
            vacio.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._filas.addWidget(vacio)
        for n in visibles:
            fila = _Fila(n)
            fila.pulsada.connect(self._abrir_una)
            self._filas.addWidget(fila)
        self._filas.addStretch(1)

    def filas(self) -> list[str]:
        """Los textos de las filas que se ven (para las pruebas)."""
        return [f.findChild(QLabel, "textoBandeja").text() for f in self._cuerpo.findChildren(_Fila)]

    # ------------------------------------------------------------------ acciones
    def _abrir_una(self, n: notificaciones.Notificacion) -> None:
        if self._sesion is not None and not n.leida:
            self._runner.run(notificaciones.marcar_leida, lambda _r: self._tras_marcar(), lambda _m: None,
                             self._sesion, n.id)
            n_leida = [x for x in self._todas if x.id == n.id]
            for x in n_leida:
                self._todas[self._todas.index(x)] = notificaciones.Notificacion(
                    x.id, x.fecha, x.tipo, x.texto, x.seccion, True)
            self._pintar()
        if n.seccion:
            self.hide()
            self.ir_a.emit(n.seccion)

    def _marcar_todas(self) -> None:
        if self._sesion is not None:
            self._runner.run(notificaciones.marcar_todas, lambda _r: self._tras_marcar(),
                             lambda m: isla.error(t("No se pudieron cargar las notificaciones"), m), self._sesion)

    def _tras_marcar(self) -> None:
        self.cambiaron.emit()
        self._cargar()

    def _pedir_todo(self) -> None:
        self.hide()
        self.ver_todo.emit()


class HojaNotificaciones(QWidget):
    """Vista extendida, flotante sobre la ventana: contiene la tabla completa de notificaciones."""

    def __init__(self, ventana: QWidget) -> None:
        super().__init__(ventana)
        self._ventana = ventana
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._tarjeta = QFrame(self)
        self._tarjeta.setObjectName("card")
        self._titulo = QLabel(t("Notificaciones"))
        self._titulo.setObjectName("tituloPagina")
        self.btn_cerrar = QPushButton()
        self.btn_cerrar.setIcon(iconos.icono("x", tam=16))
        self.btn_cerrar.setToolTip(t("Cerrar"))
        self.btn_cerrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cerrar.setFixedSize(30, 30)
        self.btn_cerrar.clicked.connect(self.cerrar)
        cabecera = QHBoxLayout()
        cabecera.addWidget(self._titulo)
        cabecera.addStretch(1)
        cabecera.addWidget(self.btn_cerrar)
        self._lay = QVBoxLayout(self._tarjeta)
        self._lay.setContentsMargins(20, 16, 20, 16)
        self._lay.setSpacing(8)
        self._lay.addLayout(cabecera)
        self.vista: QWidget | None = None
        ventana.installEventFilter(self)
        self.hide()

    def poner(self, vista: QWidget) -> None:
        """Pone la vista extendida; si ya había una (las vistas se reconstruyen al cambiar tema o idioma), la reemplaza."""
        anterior = self.vista
        if anterior is not None and anterior is not vista:
            self._lay.removeWidget(anterior)
            anterior.deleteLater()
        self.vista = vista
        self._lay.addWidget(vista, 1)

    def abrir(self) -> None:
        c = tema.colores()
        self.btn_cerrar.setStyleSheet(f"QPushButton {{ color: {c['texto']}; font-size: 14px; padding: 0; }}")
        self._reubicar()
        self.show()
        self.raise_()
        self.setFocus()
        motion.desvanecer(self._tarjeta, 0.0, 1.0, motion.NORMAL)
        refrescar = getattr(self.vista, "refresh", None)
        if callable(refrescar):
            refrescar()
        isla.elevar()

    def cerrar(self) -> None:
        self.hide()

    def _reubicar(self) -> None:
        self.setGeometry(self._ventana.rect())
        w = max(520, min(1040, self.width() - 80))
        h = max(360, min(720, self.height() - 80))
        self._tarjeta.setGeometry(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h).toRect())

    def eventFilter(self, objeto, evento) -> bool:
        if objeto is self._ventana and evento.type() == QEvent.Type.Resize and self.isVisible():
            self._reubicar()
        return super().eventFilter(objeto, evento)

    def paintEvent(self, _evento) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.end()

    def mousePressEvent(self, evento) -> None:
        if not self._tarjeta.geometry().contains(evento.position().toPoint()):
            self.cerrar()
        evento.accept()

    def keyPressEvent(self, evento) -> None:
        if evento.key() == Qt.Key.Key_Escape:
            self.cerrar()
            return
        super().keyPressEvent(evento)
