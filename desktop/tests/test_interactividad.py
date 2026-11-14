"""Pruebas de la capa de interactividad: hover, drawer, paleta, chips, confirmación y diagrama.

Corren con ``APP_SIN_ANIMACIONES=1`` (lo fija ``conftest.py``): el estado final se ve de inmediato y las pruebas no
dependen de que una animación termine. No tocan Oracle.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QTableWidgetItem, QToolButton, QWidget

from app.views import components, paleta, widgets
from app.views.bluetooth_vivo import BarrasTrafico, Diagrama


@pytest.fixture
def host(qtbot):
    ventana = QWidget()
    ventana.resize(900, 600)
    qtbot.addWidget(ventana)
    ventana.show()
    return ventana


# ------------------------------------------------------------------ KPI
def test_kpi_se_voltea_al_hover_y_vuelve(qtbot):
    tarjeta = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(tarjeta)
    tarjeta.set_valor(80.0, lambda v: f"{v:.0f} %")
    tarjeta.set_detalle("4 de 5 SKU contados")
    tarjeta.show()
    QApplication.sendEvent(tarjeta, QEvent(QEvent.Type.Enter))
    assert tarjeta._detalle.isVisible()
    assert tarjeta.texto() == "80 %"                 # el dato final no depende del dibujo
    QApplication.sendEvent(tarjeta, QEvent(QEvent.Type.Leave))
    assert not tarjeta._detalle.isVisible()
    assert tarjeta._valor.isVisible()


def test_kpi_emite_clic(qtbot):
    tarjeta = widgets.TarjetaKpi("Avance")
    qtbot.addWidget(tarjeta)
    vistos = []
    tarjeta.clicked.connect(lambda: vistos.append(True))
    evento = QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(10, 10), QPointF(10, 10),
                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    tarjeta.mouseReleaseEvent(evento)
    assert vistos == [True]


# ------------------------------------------------------------------ paleta
def test_paleta_filtra_y_ejecuta(qtbot, host):
    registro = paleta.RegistroAtajos()
    hechos = []
    registro.registrar(paleta.Atajo("ir:dashboard", "Ir a Dashboard", "Navegar", "Ctrl+1",
                                    lambda: hechos.append("dashboard")))
    registro.registrar(paleta.Atajo("accion:exportar", "Exportar conciliación", "Inventario", "",
                                    lambda: hechos.append("exportar")))
    dialogo = paleta.PaletaComandos(host, registro, None)
    qtbot.addWidget(dialogo)
    dialogo.abrir("dashboard")
    assert dialogo.lista.count() == 1
    dialogo._elegir_actual()
    qtbot.wait(30)
    assert hechos == ["dashboard"]
    assert not dialogo.isVisible()


def test_paleta_sin_resultados_lo_dice(qtbot, host):
    dialogo = paleta.PaletaComandos(host, paleta.RegistroAtajos(), None)
    qtbot.addWidget(dialogo)
    dialogo.abrir("zzzz")
    assert dialogo.lista.count() == 0
    assert "Sin resultados" in dialogo.lbl_total.text()


# ------------------------------------------------------------------ drawer
def test_drawer_abre_y_cierra_con_esc(qtbot, host):
    drawer = components.Drawer(host, ancho=360)
    qtbot.addWidget(drawer)
    contenido = QLabel("Detalle del KPI")
    drawer.abrir("Detalle", contenido)
    assert drawer.isVisible()
    assert drawer.panel.width() == 360
    drawer.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert not drawer.isVisible()


# ------------------------------------------------------------------ chips
def test_chip_activo_avisa_y_desaparece(qtbot):
    quitados = []
    fila = components.FiltrosActivos()
    qtbot.addWidget(fila)
    fila.quitado.connect(quitados.append)
    fila.actua([("categoria", "Categoría: Aseo", lambda: quitados.append("limpiar"))])
    qtbot.wait(60)
    cerrar = fila.findChildren(QToolButton)[0]
    cerrar.click()
    qtbot.wait(60)
    assert "categoria" in quitados
    assert "limpiar" in quitados


# ------------------------------------------------------------------ confirmación
def test_confirmacion_exige_entender_antes_de_seguir(qtbot, host):
    dialogo = components.Confirmacion(host, "Eliminar", "Esto no se puede deshacer.", "Eliminar",
                                      requiere_entendido=True)
    qtbot.addWidget(dialogo)
    dialogo.show()
    dialogo._confirmar()
    assert dialogo.resultado is False
    assert dialogo.aviso.isVisible()
    dialogo.check.setChecked(True)
    dialogo._confirmar()
    assert dialogo.resultado is True


# ------------------------------------------------------------------ diagrama y tráfico
def test_diagrama_pinta_sus_estados(qtbot):
    diagrama = Diagrama()
    qtbot.addWidget(diagrama)
    for estado in ("ESPERANDO_EMPAREJAMIENTO", "CONECTADO", "RECIBIENDO", "LISTO", "ERROR", "PAUSADO"):
        diagrama.set_estado(estado)
        imagen = diagrama.grab()
        assert not imagen.isNull()
    assert diagrama.estado() == "PAUSADO"


def test_barras_de_trafico_acumulan(qtbot):
    barras = BarrasTrafico()
    qtbot.addWidget(barras)
    barras.agregar(3)
    barras.agregar(3)          # repetido: no duplica
    barras.agregar(8)
    assert barras.historial() == [3, 8]
    assert not barras.grab().isNull()


# ------------------------------------------------------------------ tabla
def test_acciones_de_fila_se_colocan(qtbot):
    tabla = QTableWidget(2, 2)
    tabla.setItem(0, 0, QTableWidgetItem("A1"))
    tabla.setItem(0, 1, QTableWidgetItem("Arroz"))
    tabla.setItem(1, 0, QTableWidgetItem("A2"))
    tabla.setItem(1, 1, QTableWidgetItem("Azúcar"))
    qtbot.addWidget(tabla)
    tabla.show()
    elegidas = []
    acciones = components.AccionesFila(tabla, [("↗", "Ver", elegidas.append)])
    qtbot.addWidget(acciones)
    acciones._fila = 0
    acciones._colocar()
    acciones.show()
    assert acciones.width() > 0
    acciones._botones[0].click()
    assert elegidas == [0]


# ------------------------------------------------------------------ progreso de scroll
def test_indicador_de_progreso(qtbot, host):
    from app.views.motion import ProgresoScroll

    indicador = ProgresoScroll(host)
    qtbot.addWidget(indicador)
    indicador.set_rango(5, 0, 10)
    assert not indicador.grab().isNull()
