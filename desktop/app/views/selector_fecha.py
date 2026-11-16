"""Selector de fecha de la aplicación: un solo componente para todos los campos «Desde» y «Hasta».

Por qué existe. El desplegable nativo de ``QDateEdit`` es un ``QCalendarWidget``, cuya cuadrícula es un ``QTableView``.
Las reglas globales del tema (``QTableView::item { padding: 0 10px; border-bottom: … }``) le llegaban y cada celda,
de 35 px de ancho, se quedaba con 15 px útiles: los números de dos dígitos se elidían por completo (se veían filas
vacías) y el borde inferior descuadraba las filas. Pintar la cuadrícula a mano la deja fuera del alcance de cualquier QSS.

El calendario es un popover dentro de la ventana principal (``capas.CapaFlotante``), no una ventana del sistema:
no se corta, queda siempre dentro de la ventana y se coloca debajo del campo o, si no cabe, encima.
La semana empieza en lunes. La cuadrícula siempre tiene 6 filas × 7 columnas, así que la altura nunca salta.
"""

from __future__ import annotations

from PyQt6.QtCore import (QDate, QEasingCurve, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QPixmap
from PyQt6.QtWidgets import QDateEdit, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import tema
from ..i18n import idioma, registrar, t
from . import widgets
from .capas import CapaFlotante, abrir_capa, superficie
from .iconos import icono
from .isla import isla

registrar({
    "Hoy": "Today",
    "Mes anterior": "Previous month",
    "Mes siguiente": "Next month",
    "Rango de fechas inválido": "Invalid date range",
    "«Desde» no puede ser posterior a «Hasta» ({otro}). Se mantiene {actual}.":
        "“From” cannot be later than “To” ({otro}). {actual} was kept.",
    "«Hasta» no puede ser anterior a «Desde» ({otro}). Se mantiene {actual}.":
        "“To” cannot be earlier than “From” ({otro}). {actual} was kept.",
})

MESES = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"),
}
DIAS = {"es": ("Lu", "Ma", "Mi", "Ju", "Vi", "Sá", "Do"), "en": ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")}

ANCHO_CELDA, ALTO_CELDA, ALTO_CABECERA = 40, 36, 28
FILAS, COLUMNAS = 6, 7
FORMATO = "dd/MM/yyyy"


def cuadricula(anio: int, mes: int) -> list[QDate]:
    """Las 42 fechas (6 semanas × 7 días, de lunes a domingo) que se muestran para ``anio``/``mes``.

    Empieza en el lunes de la semana del día 1; los días de otros meses completan la primera y la última fila."""
    primero = QDate(anio, mes, 1)
    inicio = primero.addDays(-(primero.dayOfWeek() - 1))            # Qt: lunes = 1 … domingo = 7
    return [inicio.addDays(i) for i in range(FILAS * COLUMNAS)]


def _mes_primero(fecha: QDate) -> QDate:
    return QDate(fecha.year(), fecha.month(), 1)


def _alfa(color: str, a: float) -> QColor:
    q = QColor(color)
    q.setAlphaF(max(0.0, min(1.0, a)))
    return q


# ------------------------------------------------------------------ cuadrícula de días
class _Rejilla(QWidget):
    """Cabecera de días de la semana y 6×7 celdas iguales. Todo se pinta aquí: ningún QSS puede recortarlo."""

    elegida = pyqtSignal(QDate)
    mes_cambiado = pyqtSignal(QDate)

    def __init__(self, seleccion: QDate, minimo: QDate, maximo: QDate, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._sel = seleccion
        self._foco = seleccion
        self._teclado = False
        self._mes = _mes_primero(seleccion)
        self._min, self._max = minimo, maximo
        self._hoy = QDate.currentDate()
        self._fechas = cuadricula(self._mes.year(), self._mes.month())
        self._hover = -1
        self._alfa_hover: dict[int, float] = {}
        self._anim_hover: QVariantAnimation | None = None
        self._sel_t = 1.0
        self._anim_sel: QVariantAnimation | None = None
        self._viejo: QPixmap | None = None
        self._dir = 1
        self._t = 1.0
        self._anim_mes: QVariantAnimation | None = None
        self.setMinimumSize(COLUMNAS * ANCHO_CELDA, ALTO_CABECERA + FILAS * ALTO_CELDA)

    def sizeHint(self) -> QSize:
        return QSize(COLUMNAS * ANCHO_CELDA, ALTO_CABECERA + FILAS * ALTO_CELDA)

    # ------------------------------------------------------------- consulta (también para pruebas)
    def mes(self) -> QDate:
        return self._mes

    def seleccion(self) -> QDate:
        return self._sel

    def fechas(self) -> list[QDate]:
        return list(self._fechas)

    def rect_celda(self, i: int) -> QRectF:
        w = self.width() / COLUMNAS
        h = (self.height() - ALTO_CABECERA) / FILAS
        return QRectF((i % COLUMNAS) * w, ALTO_CABECERA + (i // COLUMNAS) * h, w, h)

    def celdas(self) -> list[tuple[QDate, QRectF, bool]]:
        """(fecha, rectángulo, ¿es del mes mostrado?) de las 42 celdas, en orden de lectura."""
        return [(d, self.rect_celda(i), d.month() == self._mes.month() and d.year() == self._mes.year())
                for i, d in enumerate(self._fechas)]

    def habilitada(self, d: QDate) -> bool:
        return self._min <= d <= self._max

    def _indice(self, pos: QPointF) -> int:
        if pos.y() < ALTO_CABECERA or pos.y() >= self.height() or pos.x() < 0 or pos.x() >= self.width():
            return -1
        col = int(pos.x() / (self.width() / COLUMNAS))
        fila = int((pos.y() - ALTO_CABECERA) / ((self.height() - ALTO_CABECERA) / FILAS))
        return min(fila, FILAS - 1) * COLUMNAS + min(col, COLUMNAS - 1)

    # ------------------------------------------------------------- cambios de mes
    def ir_a_mes(self, primero: QDate, animar: bool = True) -> None:
        primero = _mes_primero(primero)
        if primero == self._mes:
            return
        direccion = 1 if primero > self._mes else -1
        self._terminar_mes()
        if animar and widgets.ANIMAR and self.isVisible():
            self._viejo = self._captura_dias()
            self._dir = direccion
            self._t = 0.0
        self._mes = primero
        self._fechas = cuadricula(primero.year(), primero.month())
        self._hover = -1
        self._alfa_hover.clear()
        if self._viejo is not None:
            self._anim_mes = widgets.animar(self, 0.0, 1.0, 260, self._paso_mes, self._terminar_mes,
                                            QEasingCurve.Type.OutCubic)
        self.mes_cambiado.emit(primero)
        self.update()

    def _paso_mes(self, v: float) -> None:
        self._t = v
        self.update()

    def _terminar_mes(self) -> None:
        widgets._detener(self._anim_mes)
        self._anim_mes = None
        self._viejo = None
        self._t = 1.0
        self.update()

    def _captura_dias(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        pm = QPixmap(round(self.width() * dpr), round((self.height() - ALTO_CABECERA) * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        p.translate(0, -ALTO_CABECERA)
        self._pintar_dias(p, 0.0, 1.0)
        p.end()
        return pm

    # ------------------------------------------------------------- selección y foco
    def poner_seleccion(self, d: QDate, animar: bool = True) -> None:
        self._sel = d
        self._foco = d
        self._sel_t = 0.0
        widgets._detener(self._anim_sel)
        self._anim_sel = widgets.animar(self, 0.0, 1.0, 180, self._paso_sel, self._fin_sel,
                                        QEasingCurve.Type.OutCubic) if animar else None
        if not animar:
            self._sel_t = 1.0
        self.update()

    def _paso_sel(self, v: float) -> None:
        self._sel_t = v
        self.update()

    def _fin_sel(self) -> None:
        self._sel_t = 1.0
        self.update()

    def mover_foco(self, dias: int = 0, meses: int = 0) -> None:
        """Teclado: mueve el día enfocado (y cambia de mes si hace falta)."""
        d = self._foco.addDays(dias).addMonths(meses) if meses else self._foco.addDays(dias)
        d = max(self._min, min(self._max, d))
        self._teclado = True
        self._foco = d
        if _mes_primero(d) != self._mes:
            self.ir_a_mes(d)
        self.update()

    def elegir_foco(self) -> None:
        if self.habilitada(self._foco):
            self._elegir(self._foco)

    def _elegir(self, d: QDate) -> None:
        self.poner_seleccion(d)
        self.elegida.emit(d)

    # ------------------------------------------------------------- ratón
    def mouseMoveEvent(self, e) -> None:
        i = self._indice(e.position())
        if i != -1 and not self.habilitada(self._fechas[i]):
            i = -1
        if i != self._hover:
            self._hover = i
            self._teclado = False
            self._animar_hover()
        self.setCursor(Qt.CursorShape.PointingHandCursor if i != -1 else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, e) -> None:
        if self._hover != -1:
            self._hover = -1
            self._animar_hover()
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        i = self._indice(e.position())
        if i != -1 and self.habilitada(self._fechas[i]):
            self._elegir(self._fechas[i])

    def _animar_hover(self) -> None:
        desde = {i: self._alfa_hover.get(i, 0.0) for i in set(self._alfa_hover) | {self._hover}}
        widgets._detener(self._anim_hover)

        def paso(v: float) -> None:
            for i, a0 in desde.items():
                self._alfa_hover[i] = a0 + ((1.0 if i == self._hover else 0.0) - a0) * v
            self.update()

        def fin() -> None:
            for i in [i for i, a in self._alfa_hover.items() if a <= 0.001 and i != self._hover]:
                del self._alfa_hover[i]

        self._anim_hover = widgets.animar(self, 0.0, 1.0, 140, paso, fin, QEasingCurve.Type.OutCubic)

    # ------------------------------------------------------------- pintura
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        c = tema.colores()
        w = self.width() / COLUMNAS
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(c["texto_suave"]))
        for col, nombre in enumerate(DIAS.get(idioma(), DIAS["es"])):
            p.drawText(QRectF(col * w, 0, w, ALTO_CABECERA), int(Qt.AlignmentFlag.AlignCenter), nombre)
        p.setClipRect(QRectF(0, ALTO_CABECERA, self.width(), self.height() - ALTO_CABECERA))
        if self._viejo is not None and self._t < 1.0:
            t = self._t
            desp = self.width() * 0.30
            p.setOpacity(max(0.0, 1 - 1.9 * t))                  # el mes anterior se va rápido…
            p.drawPixmap(QPointF(-self._dir * t * desp, ALTO_CABECERA), self._viejo)
            self._pintar_dias(p, self._dir * (1 - t) * desp, min(1.0, max(0.0, (t - 0.25) / 0.75)))   # …y el nuevo entra
        else:
            self._pintar_dias(p, 0.0, 1.0)

    def _pintar_dias(self, p: QPainter, dx: float, opacidad: float) -> None:
        c = tema.colores()
        p.save()
        p.setOpacity(opacidad)
        fuente = QFont(self.font())
        fuente.setPixelSize(14)
        for i, d in enumerate(self._fechas):
            r = self.rect_celda(i).translated(dx, 0)
            en_mes = d.month() == self._mes.month()
            activa = self.habilitada(d)
            diametro = min(r.width(), r.height()) - 4
            disco = QRectF(r.center().x() - diametro / 2, r.center().y() - diametro / 2, diametro, diametro)
            seleccionada = d == self._sel
            if not seleccionada:
                a = self._alfa_hover.get(i, 0.0)
                if self._teclado and d == self._foco and activa:
                    a = max(a, 1.0)
                if a > 0.004 and activa:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(_alfa(c["texto"], 0.09 * a))
                    p.drawEllipse(disco)
            color = QColor(c["texto"])
            fuente.setWeight(QFont.Weight.Normal)
            if seleccionada:
                k = 0.62 + 0.38 * self._sel_t
                centro = disco.center()
                m = QRectF(0, 0, diametro * k, diametro * k)
                m.moveCenter(centro)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(_alfa(c["acento"], 1.0 if en_mes else 0.85))
                p.drawEllipse(m)
                color = QColor(c["acento_texto"])
                fuente.setWeight(QFont.Weight.DemiBold)
            elif d == self._hoy and activa:
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(_alfa(c["acento"], 0.9 if en_mes else 0.5))
                p.drawEllipse(disco.adjusted(1, 1, -1, -1))
                color = QColor(c["acento"])
                fuente.setWeight(QFont.Weight.DemiBold)
            if not seleccionada:
                if not activa:
                    color = _alfa(c["texto_suave"], 0.38)
                elif not en_mes:
                    color = _alfa(c["texto_suave"], 0.62)
            p.setFont(fuente)
            p.setPen(color)
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), str(d.day()))
        p.restore()


# ------------------------------------------------------------------ panel del calendario
class _Calendario(QWidget):
    """Encabezado (mes, año y flechas), cuadrícula y «Hoy». Es el panel de la capa flotante."""

    elegida = pyqtSignal(QDate)
    cerrar_pedido = pyqtSignal()

    def __init__(self, seleccion: QDate, minimo: QDate, maximo: QDate) -> None:
        super().__init__()
        c = tema.colores()
        self._c = c
        self._min, self._max = minimo, maximo
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"""
            QLabel#calMes {{ background: transparent; color: {c['texto_fuerte']}; font-size: 15px; }}
            QPushButton#calNav {{ background: transparent; border: none; border-radius: 15px; min-width: 30px;
                max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; }}
            QPushButton#calNav:hover {{ background: {c['tarjeta_alt']}; }}
            QPushButton#calNav:pressed {{ background: {c['borde']}; }}
            QPushButton#calNav:disabled {{ background: transparent; }}
            QPushButton#calHoy {{ background: transparent; border: none; color: {c['acento']}; font-size: 13px;
                font-weight: 600; padding: 5px 10px; border-radius: 9px; }}
            QPushButton#calHoy:hover {{ background: {c['tarjeta_alt']}; }}""")
        self.rejilla = _Rejilla(seleccion, minimo, maximo)
        self.btn_ant = QPushButton()
        self.btn_sig = QPushButton()
        for b, nombre, ayuda in ((self.btn_ant, "izquierda", t("Mes anterior")), (self.btn_sig, "derecha", t("Mes siguiente"))):
            b.setObjectName("calNav")
            b.setIcon(icono(nombre, color=c["texto"], color_activo=c["texto_fuerte"], tam=16))
            b.setIconSize(QSize(16, 16))
            b.setToolTip(ayuda)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.lbl_mes = QLabel("")
        self.lbl_mes.setObjectName("calMes")
        self.lbl_mes.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_hoy = QPushButton(t("Hoy"))
        self.btn_hoy.setObjectName("calHoy")
        self.btn_hoy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hoy.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cab = QHBoxLayout()
        cab.setSpacing(4)
        cab.addWidget(self.btn_ant)
        cab.addWidget(self.lbl_mes, 1)
        cab.addWidget(self.btn_sig)
        pie = QHBoxLayout()
        pie.addWidget(self.btn_hoy)
        pie.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)
        lay.addLayout(cab)
        lay.addWidget(self.rejilla)
        lay.addLayout(pie)

        self.btn_ant.clicked.connect(lambda: self.mover_mes(-1))
        self.btn_sig.clicked.connect(lambda: self.mover_mes(1))
        self.btn_hoy.clicked.connect(self._hoy)
        self.rejilla.mes_cambiado.connect(self._poner_titulo)
        self.rejilla.elegida.connect(self._elegida)
        self._poner_titulo(self.rejilla.mes())

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        superficie(p, QRectF(self.rect()), self._c["tarjeta"], self._c["borde_fuerte"], 14)

    # ------------------------------------------------------------- acciones
    def mes_visible(self) -> QDate:
        return self.rejilla.mes()

    def mover_mes(self, n: int) -> None:
        destino = self.rejilla.mes().addMonths(n)
        if _mes_primero(self._min) > destino.addMonths(1).addDays(-1) or destino > self._max:
            return
        self.rejilla.ir_a_mes(destino)

    def _hoy(self) -> None:
        hoy = QDate.currentDate()
        if self._min <= hoy <= self._max:
            self.rejilla.ir_a_mes(hoy)
            self.rejilla.poner_seleccion(hoy)
            self._elegida(hoy)

    def _elegida(self, d: QDate) -> None:
        """Se aplica al instante y el popover se cierra tras un instante (se alcanza a ver la selección)."""
        self.elegida.emit(d)
        QTimer.singleShot(150 if widgets.ANIMAR else 0, self.cerrar_pedido.emit)

    def _poner_titulo(self, mes: QDate) -> None:
        nombre = MESES.get(idioma(), MESES["es"])[mes.month() - 1]
        self.lbl_mes.setText(f"<b>{nombre.capitalize()}</b> <span style='color:{self._c['texto_suave']}'>{mes.year()}</span>")
        self.btn_ant.setEnabled(_mes_primero(self._min) < mes)
        self.btn_sig.setEnabled(mes.addMonths(1) <= self._max)

    # ------------------------------------------------------------- teclado
    def keyPressEvent(self, e: QKeyEvent) -> None:
        k = e.key()
        pasos = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (-7, 0), Qt.Key.Key_Down: (7, 0),
                 Qt.Key.Key_PageUp: (0, -1), Qt.Key.Key_PageDown: (0, 1)}
        if k in pasos:
            self.rejilla.mover_foco(*pasos[k])
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.rejilla.elegir_foco()
        elif k == Qt.Key.Key_Home:
            self._hoy()
        else:
            super().keyPressEvent(e)


# ------------------------------------------------------------------ el campo
class SelectorFecha(QDateEdit):
    """``QDateEdit`` con el calendario de la aplicación. Mismo API que ``QDateEdit`` (``date()``, ``setDate()``,
    ``dateChanged``…), formato ``dd/MM/yyyy`` y, si se vincula a otro selector, validación de rango «Desde ≤ Hasta»."""

    def __init__(self, fecha: QDate | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCalendarPopup(True)           # conserva la flecha del campo; el desplegable lo abrimos nosotros
        self.setDisplayFormat(FORMATO)
        if fecha is not None:
            self.setDate(fecha)
        self._rol: str | None = None
        self._otro: SelectorFecha | None = None
        self._previo = self.date()
        self._capa: CapaFlotante | None = None
        self.dateChanged.connect(self._cambio)
        self.editingFinished.connect(self._fin_edicion)

    # ------------------------------------------------------------- rango
    @staticmethod
    def vincular(desde: SelectorFecha, hasta: SelectorFecha) -> None:
        """Los dos campos se validan entre sí: «Desde» no puede pasar de «Hasta»."""
        desde._rol, desde._otro = "desde", hasta
        hasta._rol, hasta._otro = "hasta", desde

    def _rango_ok(self, fecha: QDate) -> bool:
        if self._otro is None:
            return True
        return fecha <= self._otro.date() if self._rol == "desde" else fecha >= self._otro.date()

    def _rechazar(self, intento: QDate) -> None:
        """Rango inválido: no se acepta el valor, se mantiene el anterior y se avisa por la Isla."""
        clave = ("«Desde» no puede ser posterior a «Hasta» ({otro}). Se mantiene {actual}." if self._rol == "desde"
                 else "«Hasta» no puede ser anterior a «Desde» ({otro}). Se mantiene {actual}.")
        isla.advertencia(t("Rango de fechas inválido"),
                         t(clave, otro=self._otro.date().toString(FORMATO), actual=self._previo.toString(FORMATO)))

    def _cambio(self, d: QDate) -> None:
        if not self.hasFocus() and not self.calendario_abierto():
            self._previo = d

    def _fin_edicion(self) -> None:
        """Al terminar de escribir a mano: si el rango quedó mal se vuelve al valor anterior (con aviso)."""
        d = self.date()
        if self._rango_ok(d):
            self._previo = d
            return
        self._rechazar(d)
        self.setDate(self._previo)

    def focusInEvent(self, e) -> None:
        self._previo = self.date()
        super().focusInEvent(e)

    # ------------------------------------------------------------- calendario
    def calendario_abierto(self) -> bool:
        return self._capa is not None and self._capa.esta_abierta()

    def calendario(self) -> _Calendario | None:
        return self._capa.panel if self.calendario_abierto() else None

    def abrir_calendario(self) -> None:
        if self.calendario_abierto():
            self._capa.cerrar()
            return
        self._previo = self.date()
        panel = _Calendario(self.date(), self.minimumDate(), self.maximumDate())
        panel.elegida.connect(self._elegido)
        ventana = self.window()
        self._capa = abrir_capa(ventana, panel, area="ventana", oscuridad=0.0, radio=14,
                                tamano=lambda _a, p=panel: p.sizeHint(), posicion=self._posicion, sombra=(16, 0.7))
        return

    def cerrar_calendario(self) -> None:
        if self.calendario_abierto():
            self._capa.cerrar()

    def _elegido(self, d: QDate) -> None:
        if not self._rango_ok(d):
            self._rechazar(d)
            return
        self._previo = d
        self.setDate(d)
        self.setFocus()

    def _posicion(self, tam: QSize, limites: QRect) -> QRect:
        """Debajo del campo, alineado a su izquierda; si no cabe, encima; siempre dentro de la ventana."""
        ventana = self.window()
        campo = QRect(self.mapTo(ventana, QPoint(0, 0)), self.size())
        x, y = campo.left(), campo.bottom() + 6
        if y + tam.height() > limites.bottom() - 8:
            arriba = campo.top() - tam.height() - 6
            y = arriba if arriba >= limites.top() + 8 else max(limites.top() + 8, limites.bottom() - 8 - tam.height())
        if x + tam.width() > limites.right() - 8:
            x = campo.right() - tam.width() + 1
        x = max(limites.left() + 8, min(x, limites.right() - 8 - tam.width() + 1))
        return QRect(QPoint(x, y), tam)

    # ------------------------------------------------------------- eventos
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and e.position().x() >= self.width() - 34:
            self.abrir_calendario()
            e.accept()
            return
        super().mousePressEvent(e)

    def keyPressEvent(self, e) -> None:
        if (e.key() == Qt.Key.Key_Down and e.modifiers() & Qt.KeyboardModifier.AltModifier) or e.key() == Qt.Key.Key_F4:
            self.abrir_calendario()
            e.accept()
            return
        super().keyPressEvent(e)
