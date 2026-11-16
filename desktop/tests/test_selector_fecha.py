"""Selector de fecha: la cuadrícula del calendario, el popover, la validación Desde/Hasta y los temas.

Regresión del error original: las reglas globales ``QTableView::item { padding: 0 10px }`` elidían los números de dos
dígitos del ``QCalendarWidget`` nativo (filas vacías, días «faltantes»). Aquí se comprueba, píxel a píxel, que cada
día de cada mes se dibuja en su sitio, con el stylesheet completo de la aplicación puesto."""

import calendar
from datetime import date

import pytest
from PyQt6.QtCore import QDate, QEvent, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QWidget

from app import i18n, tema
from app.views import selector_fecha as sf
from app.views import widgets
from app.views.base import estilo
from app.views.selector_fecha import SelectorFecha, _Calendario, cuadricula

MESES_PEDIDOS = [(2026, 10), (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2028, 2), (2026, 8)]
MESES_DIFICILES = MESES_PEDIDOS + [(2025, 6), (2025, 9), (2024, 2), (2023, 10), (2026, 2), (2027, 5)]   # inicia domingo, lunes…


def esperar(qtbot, cond, ms=3000):
    qtbot.waitUntil(cond, timeout=ms)


# ------------------------------------------------------------------ lógica del calendario (sin interfaz)
@pytest.mark.parametrize("anio, mes", MESES_DIFICILES)
def test_la_cuadricula_coincide_con_el_calendario_real(anio, mes):
    f = cuadricula(anio, mes)
    assert len(f) == 42                                                         # siempre 6 semanas × 7 días
    assert f[0].dayOfWeek() == 1                                                # empieza en lunes
    assert all(f[i + 1] == f[i].addDays(1) for i in range(41))                  # cronológica, sin saltos ni repetidos
    assert len({d.toJulianDay() for d in f}) == 42
    mes_dias = [d for d in f if d.month() == mes and d.year() == anio]
    n = calendar.monthrange(anio, mes)[1]
    assert [d.day() for d in mes_dias] == list(range(1, n + 1))                 # ni faltan ni sobran días
    assert f.index(QDate(anio, mes, 1)) == date(anio, mes, 1).weekday()          # el día 1 cae en su día de la semana real
    # lo que no es del mes solo está antes del 1 y después del último
    primero, ultimo = f.index(QDate(anio, mes, 1)), f.index(QDate(anio, mes, n))
    assert all(d.month() != mes for d in f[:primero]) and all(d.month() != mes for d in f[ultimo + 1:])
    assert primero + n == ultimo + 1


def test_todos_los_meses_de_2020_a_2032():
    for anio in range(2020, 2033):
        for mes in range(1, 13):
            f = cuadricula(anio, mes)
            assert f[date(anio, mes, 1).weekday()] == QDate(anio, mes, 1)
            assert sum(1 for d in f if d.month() == mes) == calendar.monthrange(anio, mes)[1]


def test_meses_de_4_5_y_6_semanas():
    # Febrero 2027 empieza en lunes y tiene 28 días: 4 semanas exactas; octubre 2026 necesita 5; agosto 2026, 6.
    def semanas(a, m):
        f = cuadricula(a, m)
        return sum(1 for fila in range(6) if any(d.month() == m for d in f[fila * 7:fila * 7 + 7]))
    assert semanas(2027, 2) == 4 and semanas(2026, 10) == 5 and semanas(2026, 8) == 6


def test_febrero_bisiesto_y_cambio_de_anio():
    assert sum(1 for d in cuadricula(2028, 2) if d.month() == 2) == 29
    assert sum(1 for d in cuadricula(2027, 2) if d.month() == 2) == 28
    assert QDate(2027, 1, 1) in cuadricula(2026, 12) and QDate(2026, 12, 31) in cuadricula(2027, 1)


# ------------------------------------------------------------------ dibujo real
def hay_tinta(img: QImage, rect: QRect, fondo: QColor) -> bool:
    r = rect.intersected(img.rect())
    for y in range(r.top(), r.bottom() + 1):
        for x in range(r.left(), r.right() + 1):
            c = img.pixelColor(x, y)
            if abs(c.red() - fondo.red()) + abs(c.green() - fondo.green()) + abs(c.blue() - fondo.blue()) > 90:
                return True
    return False


def panel_en(qtbot, anio, mes, modo="claro", dia=None):
    tema.aplicar(QApplication.instance(), modo)
    p = _Calendario(QDate(anio, mes, dia or 1), QDate(1752, 9, 14), QDate(7999, 12, 31))
    qtbot.addWidget(p)
    p.show()
    return p


@pytest.mark.parametrize("modo", ["claro", "oscuro"])
@pytest.mark.parametrize("anio, mes", MESES_PEDIDOS)
def test_cada_dia_se_dibuja_en_su_celda(qtbot, anio, mes, modo):
    """Ningún número falta, está recortado ni cae en otra columna; las siete columnas y seis filas son iguales."""
    app = QApplication.instance()
    app.setStyleSheet(estilo())              # el stylesheet global completo, el que causaba el error
    try:
        p = panel_en(qtbot, anio, mes, modo)
        r = p.rejilla
        img = p.grab().toImage()
        dpr = img.devicePixelRatio()
        fondo = QColor(tema.colores()["tarjeta"])
        celdas = r.celdas()
        assert len(celdas) == 42
        ancho, alto = celdas[0][1].width(), celdas[0][1].height()
        f = QFont(r.font())
        f.setPixelSize(14)
        f.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetricsF(f)
        for i, (d, rc, en_mes) in enumerate(celdas):
            assert rc.width() == pytest.approx(ancho) and rc.height() == pytest.approx(alto)        # celdas iguales
            assert i % 7 == d.dayOfWeek() - 1                                                        # columna = día de la semana
            assert rc.x() == pytest.approx((i % 7) * ancho)
            assert fm.horizontalAdvance(str(d.day())) + 6 <= ancho and fm.height() <= alto           # el número cabe
            assert 0 <= rc.left() and rc.right() <= r.width() + 0.01 and rc.bottom() <= r.height() + 0.01
            if en_mes:                                                                               # se ve de verdad
                origen = r.mapTo(p, QPoint(0, 0))
                caja = QRect(round((origen.x() + rc.x() + 6) * dpr), round((origen.y() + rc.y() + 6) * dpr),
                             round((rc.width() - 12) * dpr), round((rc.height() - 12) * dpr))
                assert hay_tinta(img, caja, fondo), f"falta el {d.toString()} en {anio}-{mes} ({modo})"
        # la semana empieza en lunes y la primera columna del día 1 es la real
        assert celdas[date(anio, mes, 1).weekday()][0] == QDate(anio, mes, 1)
    finally:
        app.setStyleSheet("")
        tema.aplicar(app, "sistema")


def test_el_stylesheet_global_ya_no_afecta_al_calendario(qtbot):
    """Con las reglas de tablas puestas, la celda de dos dígitos sigue midiendo lo mismo y se sigue viendo."""
    app = QApplication.instance()
    sin = panel_en(qtbot, 2026, 10)
    medida_sin = sin.rejilla.sizeHint()
    app.setStyleSheet(estilo())
    try:
        con = panel_en(qtbot, 2026, 10)
        assert con.rejilla.sizeHint() == medida_sin
        img = con.grab().toImage()
        # «16» (seleccionado) y «24» tienen tinta
        celdas = {d.day(): rc for d, rc, en in con.rejilla.celdas() if en}
        origen = con.rejilla.mapTo(con, QPoint(0, 0))
        for dia in (10, 11, 24, 30):
            rc = celdas[dia]
            caja = QRect(round(origen.x() + rc.x() + 6), round(origen.y() + rc.y() + 6), round(rc.width() - 12), round(rc.height() - 12))
            assert hay_tinta(img, caja, QColor(tema.colores()["tarjeta"]))
    finally:
        app.setStyleSheet("")


# ------------------------------------------------------------------ navegación
def test_navegacion_entre_meses_y_anios(qtbot):
    p = panel_en(qtbot, 2026, 12)
    assert p.mes_visible() == QDate(2026, 12, 1) and "Diciembre" in p.lbl_mes.text() and "2026" in p.lbl_mes.text()
    p.btn_sig.click()
    assert p.mes_visible() == QDate(2027, 1, 1) and "Enero" in p.lbl_mes.text() and "2027" in p.lbl_mes.text()
    p.btn_ant.click()
    p.btn_ant.click()
    assert p.mes_visible() == QDate(2026, 11, 1) and "Noviembre" in p.lbl_mes.text()
    assert QDate(2026, 11, 1) in p.rejilla.fechas()


def test_nombres_en_ingles(qtbot):
    i18n.set_idioma("en")
    try:
        p = panel_en(qtbot, 2026, 10)
        assert "October" in p.lbl_mes.text()
        assert sf.DIAS["en"][0] == "Mo" and sf.DIAS["es"][0] == "Lu"
    finally:
        i18n.set_idioma("es")


def test_limites_minimo_y_maximo(qtbot):
    p = _Calendario(QDate(2026, 10, 16), QDate(2026, 9, 10), QDate(2026, 11, 20))
    qtbot.addWidget(p)
    p.show()
    assert p.rejilla.habilitada(QDate(2026, 10, 1)) and not p.rejilla.habilitada(QDate(2026, 9, 9))
    assert not p.rejilla.habilitada(QDate(2026, 11, 21))
    p.btn_ant.click()
    assert not p.btn_ant.isEnabled() and p.mes_visible() == QDate(2026, 9, 1)
    p.btn_ant.click()
    assert p.mes_visible() == QDate(2026, 9, 1)                                  # no pasa del mínimo
    p.mover_mes(3)
    assert p.mes_visible() == QDate(2026, 9, 1) or p.mes_visible() <= QDate(2026, 11, 1)


# ------------------------------------------------------------------ el campo y el popover
class Ventana(QMainWindow):
    def __init__(self, ancho=1100, alto=700, pos=(40, 30)):
        super().__init__()
        raiz = QWidget()
        self.setCentralWidget(raiz)
        self.marco = QFrame(raiz)
        self.marco.setObjectName("lienzo")
        self.marco.setGeometry(0, 0, ancho, alto)
        self.desde = SelectorFecha(QDate(2026, 10, 16), self.marco)
        self.hasta = SelectorFecha(QDate(2026, 11, 15), self.marco)
        SelectorFecha.vincular(self.desde, self.hasta)
        self.desde.move(*pos)
        self.hasta.move(pos[0] + 180, pos[1])
        self.resize(ancho, alto)


@pytest.fixture
def ventana(qtbot):
    v = Ventana()
    qtbot.addWidget(v)
    v.show()
    return v


def clic_celda(panel, dia):
    r = panel.rejilla
    rc = next(rc for d, rc, en in r.celdas() if en and d.day() == dia)
    QTest.mouseClick(r, Qt.MouseButton.LeftButton, pos=rc.center().toPoint())


def test_abre_desplegable_completo_dentro_de_la_ventana(qtbot, ventana):
    ventana.desde.abrir_calendario()
    cal = ventana.desde.calendario()
    capa = ventana.desde._capa
    assert capa.parentWidget() is ventana and not capa.isWindow()               # no es una ventana del sistema
    r = capa.rect_panel()
    assert ventana.rect().contains(r)
    campo = QRect(ventana.desde.mapTo(ventana, QPoint(0, 0)), ventana.desde.size())
    assert r.top() > campo.bottom() and r.left() == campo.left()                # debajo del campo, alineado a su izquierda
    assert r.width() >= 7 * sf.ANCHO_CELDA and r.height() >= sf.ALTO_CABECERA + 6 * sf.ALTO_CELDA   # no se recorta
    assert cal.sizeHint().width() <= r.width() and cal.sizeHint().height() <= r.height()
    assert cal.rejilla.size().width() >= 7 * sf.ANCHO_CELDA


@pytest.mark.parametrize("pos", [(900, 40), (40, 600), (900, 600), (0, 0), (1010, 660)])
def test_cerca_de_los_bordes_siempre_dentro(qtbot, pos):
    v = Ventana(1100, 700, pos)
    qtbot.addWidget(v)
    v.show()
    v.desde.abrir_calendario()
    r = v.desde._capa.rect_panel()
    assert v.rect().contains(r), (pos, r)
    if pos[1] == 600:                                                           # sin sitio abajo: se abre encima del campo
        campo_top = v.desde.mapTo(v, QPoint(0, 0)).y()
        assert r.bottom() < campo_top


@pytest.mark.parametrize("tam", [(520, 420), (800, 600), (1280, 800), (1920, 1080)])
def test_distintos_tamanos_de_ventana(qtbot, tam):
    v = Ventana(*tam, pos=(tam[0] - 200, tam[1] - 60))
    qtbot.addWidget(v)
    v.show()
    v.hasta.abrir_calendario()
    assert v.rect().contains(v.hasta._capa.rect_panel())


def test_la_flecha_del_campo_abre_y_un_dia_lo_cierra(qtbot, ventana):
    d = ventana.desde
    QTest.mouseClick(d, Qt.MouseButton.LeftButton, pos=QPoint(d.width() - 12, d.height() // 2))
    esperar(qtbot, d.calendario_abierto)
    cal = d.calendario()
    assert cal.mes_visible() == QDate(2026, 10, 1)
    clic_celda(cal, 8)
    assert d.date() == QDate(2026, 10, 8) and d.lineEdit().text() == "08/10/2026"      # formato de la aplicación
    esperar(qtbot, lambda: not d.calendario_abierto())


def test_clic_en_el_texto_no_abre_el_calendario(qtbot, ventana):
    d = ventana.desde
    QTest.mouseClick(d, Qt.MouseButton.LeftButton, pos=QPoint(20, d.height() // 2))
    assert not d.calendario_abierto()


def test_escape_y_clic_fuera_cierran_sin_cambiar_la_fecha(qtbot, ventana):
    d = ventana.desde
    d.abrir_calendario()
    capa = d._capa
    QTest.keyClick(d.calendario(), Qt.Key.Key_Escape)
    esperar(qtbot, lambda: not d.calendario_abierto())
    assert d.date() == QDate(2026, 10, 16)
    d.abrir_calendario()
    QTest.mouseClick(d._capa, Qt.MouseButton.LeftButton, pos=QPoint(2, ventana.height() - 3))
    esperar(qtbot, lambda: not d.calendario_abierto())
    assert d.date() == QDate(2026, 10, 16)


def test_teclado_alt_abajo_flechas_y_enter(qtbot, ventana):
    d = ventana.desde
    QTest.keyClick(d, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    esperar(qtbot, d.calendario_abierto)
    cal = d.calendario()
    QTest.keyClick(cal, Qt.Key.Key_Right)
    QTest.keyClick(cal, Qt.Key.Key_Down)                                         # +1 día, +7 días
    QTest.keyClick(cal, Qt.Key.Key_Return)
    assert d.date() == QDate(2026, 10, 24)
    esperar(qtbot, lambda: not d.calendario_abierto())
    d.abrir_calendario()
    cal = d.calendario()
    QTest.keyClick(cal, Qt.Key.Key_PageDown)
    assert cal.mes_visible() == QDate(2026, 11, 1)


def test_hoy_selecciona_la_fecha_actual(qtbot, ventana):
    d = ventana.desde
    d.abrir_calendario()
    d.calendario().btn_hoy.click()
    hoy = QDate.currentDate()
    # «Desde» no puede pasar de «Hasta» (15/11/2026): si hoy lo supera, se rechaza y se mantiene la fecha
    assert d.date() == (hoy if hoy <= ventana.hasta.date() else QDate(2026, 10, 16))


# ------------------------------------------------------------------ validación Desde / Hasta
class Isla:
    def __init__(self):
        self.avisos = []

    def advertencia(self, titulo, descripcion="", **k):
        self.avisos.append((titulo, descripcion))


@pytest.fixture
def isla_falsa(monkeypatch):
    f = Isla()
    monkeypatch.setattr(sf, "isla", f)
    return f


def test_desde_posterior_a_hasta_se_rechaza_con_aviso(qtbot, ventana, isla_falsa):
    d = ventana.desde
    d.abrir_calendario()
    cal = d.calendario()
    cal.rejilla.ir_a_mes(QDate(2026, 12, 1), animar=False)
    clic_celda(cal, 5)                                                           # 05/12/2026 > Hasta (15/11/2026)
    assert d.date() == QDate(2026, 10, 16)                                       # no se altera en silencio
    assert len(isla_falsa.avisos) == 1
    titulo, desc = isla_falsa.avisos[0]
    assert titulo == "Rango de fechas inválido" and "15/11/2026" in desc and "16/10/2026" in desc and "Desde" in desc


def test_hasta_anterior_a_desde_se_rechaza_con_aviso(qtbot, ventana, isla_falsa):
    h = ventana.hasta
    h.abrir_calendario()
    cal = h.calendario()
    cal.rejilla.ir_a_mes(QDate(2026, 9, 1), animar=False)
    clic_celda(cal, 20)
    assert h.date() == QDate(2026, 11, 15)
    assert len(isla_falsa.avisos) == 1 and "Hasta" in isla_falsa.avisos[0][1]


def test_rango_valido_se_acepta_sin_aviso(qtbot, ventana, isla_falsa):
    h = ventana.hasta
    h.abrir_calendario()
    clic_celda(h.calendario(), 30)
    assert h.date() == QDate(2026, 11, 30) and isla_falsa.avisos == []
    d = ventana.desde
    d.abrir_calendario()
    clic_celda(d.calendario(), 30)
    assert d.date() == QDate(2026, 10, 30) and isla_falsa.avisos == []


def test_fecha_escrita_a_mano_invalida_vuelve_al_valor_anterior(qtbot, ventana, isla_falsa, monkeypatch):
    d = ventana.desde
    monkeypatch.setattr(SelectorFecha, "hasFocus", lambda self: True)            # como si se estuviera escribiendo
    d._previo = QDate(2026, 10, 16)
    d.setDate(QDate(2027, 1, 1))
    d.editingFinished.emit()
    assert d.date() == QDate(2026, 10, 16) and len(isla_falsa.avisos) == 1


def test_el_cambio_programatico_no_avisa(qtbot, ventana, isla_falsa):
    ventana.desde.setDate(QDate(2030, 1, 1))                                     # lo hace el código (p. ej. al cargar)
    assert isla_falsa.avisos == []


def test_los_filtros_reciben_el_cambio(qtbot, ventana):
    vistos = []
    ventana.hasta.dateChanged.connect(vistos.append)
    ventana.hasta.abrir_calendario()
    clic_celda(ventana.hasta.calendario(), 20)
    assert vistos == [QDate(2026, 11, 20)]


# ------------------------------------------------------------------ temas y animaciones
@pytest.mark.parametrize("modo", ["claro", "oscuro"])
def test_estados_visuales_en_ambos_temas(qtbot, modo):
    app = QApplication.instance()
    p = panel_en(qtbot, 2026, 10, modo, dia=16)
    c = tema.colores()
    img = p.grab().toImage()
    dpr = img.devicePixelRatio()
    celdas = {d.toJulianDay(): rc for d, rc, en in p.rejilla.celdas()}
    origen = p.rejilla.mapTo(p, QPoint(0, 0))

    def pixel(d, dx=0.5, dy=0.14):
        rc = celdas[d.toJulianDay()]
        return img.pixelColor(round((origen.x() + rc.x() + rc.width() * dx) * dpr), round((origen.y() + rc.y() + rc.height() * dy) * dpr))
    # seleccionado: disco del color de identidad (cerca del borde superior del disco)
    sel = pixel(QDate(2026, 10, 16), 0.5, 0.2)
    ident = QColor(c["acento"])
    assert abs(sel.red() - ident.red()) + abs(sel.green() - ident.green()) + abs(sel.blue() - ident.blue()) < 40
    # el fondo del panel es el de la superficie del tema
    fondo = QColor(c["tarjeta"])
    esquina = img.pixelColor(round(dpr * 20), round(dpr * 6))
    assert abs(esquina.red() - fondo.red()) + abs(esquina.green() - fondo.green()) + abs(esquina.blue() - fondo.blue()) < 12
    tema.aplicar(app, "sistema")


def test_cambio_de_tema_se_refleja_al_abrir(qtbot):
    app = QApplication.instance()
    tema.aplicar(app, "claro")
    claro = panel_en(qtbot, 2026, 10, "claro").grab().toImage().pixelColor(30, 8)
    oscuro = panel_en(qtbot, 2026, 10, "oscuro").grab().toImage().pixelColor(30, 8)
    assert claro.lightness() > oscuro.lightness() + 80
    tema.aplicar(app, "sistema")


def test_con_animaciones_abre_cambia_de_mes_y_cierra(qtbot, ventana, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    d = ventana.desde
    d.abrir_calendario()
    capa = d._capa
    esperar(qtbot, lambda: capa._estado == "abierta")
    cal = d.calendario()
    cal.btn_sig.click()
    assert cal.rejilla._viejo is not None                                        # transición horizontal en curso
    assert not cal.grab().toImage().isNull()
    qtbot.wait(120)
    assert not cal.grab().toImage().isNull()
    esperar(qtbot, lambda: cal.rejilla._viejo is None)
    assert cal.mes_visible() == QDate(2026, 11, 1)
    clic_celda(cal, 3)                                                           # elegir durante/tras la animación funciona
    assert d.date() == QDate(2026, 11, 3)
    esperar(qtbot, lambda: not d.calendario_abierto(), 3000)


def test_cambio_rapido_de_mes_no_deja_estado_a_medias(qtbot, ventana, monkeypatch):
    monkeypatch.setattr(widgets, "ANIMAR", True)
    d = ventana.desde
    d.abrir_calendario()
    esperar(qtbot, lambda: d._capa._estado == "abierta")
    cal = d.calendario()
    for _ in range(5):
        cal.btn_sig.click()
    esperar(qtbot, lambda: cal.rejilla._viejo is None)
    assert cal.mes_visible() == QDate(2027, 3, 1)
    assert all(r.month() in (2, 3, 4) for r in cal.rejilla.fechas())
    assert [x for x in cal.rejilla.fechas() if x.month() == 3] == [QDate(2027, 3, i) for i in range(1, 32)]


# ------------------------------------------------------------------ la causa original, demostrada
def _tinta_en_celda_nativa(qtbot, extra_qss=""):
    from PyQt6.QtWidgets import QCalendarWidget, QTableView
    app = QApplication.instance()
    app.setStyleSheet(estilo() + extra_qss)
    try:
        marco = QFrame()
        marco.setObjectName("lienzo")
        lay = QHBoxLayout(marco)
        cal = QCalendarWidget()
        cal.setSelectedDate(QDate(2026, 10, 16))
        cal.setFixedSize(245, 156)                            # el tamaño del desplegable nativo: celdas de 35 px
        lay.addWidget(cal)
        qtbot.addWidget(marco)
        marco.resize(420, 320)
        marco.show()
        qtbot.wait(100)
        vista = cal.findChild(QTableView)
        fondo = QColor(vista.palette().color(vista.backgroundRole()))
        img = vista.viewport().grab().toImage()
        resultado = {}
        for fila in range(1, 7):                              # fila 0 = encabezado de días de la semana
            for col in range(1, 8):
                ix = vista.model().index(fila, col)           # columna 0 = números de semana (ocultos)
                if ix.data() in (11, 24):
                    r = vista.visualRect(ix).adjusted(8, 4, -8, -4)
                    resultado[ix.data()] = hay_tinta(img, r, fondo)
        return resultado
    finally:
        app.setStyleSheet("")


def test_causa_original_el_qss_global_elide_los_numeros_de_dos_digitos_del_calendario_nativo(qtbot):
    """Documenta el bug: con las reglas de tablas del tema el QCalendarWidget pierde los números de dos dígitos;
    anulando solo ese padding reaparecen. Por eso el selector pinta su propia cuadrícula."""
    tema.aplicar(QApplication.instance(), "claro")
    roto = _tinta_en_celda_nativa(qtbot)
    arreglado = _tinta_en_celda_nativa(qtbot, "QCalendarWidget QAbstractItemView::item { padding: 0; border: none; }")
    assert roto and not any(roto.values())                    # 11 y 24 no se dibujan (elididos)
    assert arreglado and all(arreglado.values())              # sin el padding global, sí
