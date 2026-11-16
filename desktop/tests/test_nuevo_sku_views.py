"""Aviso flotante «Nuevo SKU» y sus dos decisiones, sin Oracle: widget, diálogo y flujos con un runner falso.

El aviso no reserva espacio: es un overlay arriba a la derecha. «Crear y procesar» pide nombre y categoría y
llama a ``db.nuevo_sku_alta``; «No crear» confirma y llama a ``db.descartar_nuevo_sku``. En ambos casos la
consulta corre por ``QueryRunner`` (aquí, ``FakeRunner``) y nunca en el hilo de la interfaz.
"""

from datetime import datetime

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog

from app import db
from app.auth import ADMIN, INVENTARIO, ErrorDeAcceso, Sesion
from app.main import build_window
from app.models import NuevoSkuFila
from app.views.aviso_nuevo_sku import AvisoNuevoSku, DialogoNuevoSku
from app.views.isla import GestorIsla
from fakes import FakeRemoto, FakeRunner

ANA = Sesion("ana.gomez", "Ana Gómez", ADMIN, correo="ana@example.com")
LUIS = Sesion("luis", "Luis Ortiz", INVENTARIO, correo="luis@example.com")
AHORA = datetime(2026, 11, 16, 5, 20)


def _filas(*datos) -> list[NuevoSkuFila]:
    """(sku, cantidad, fecha) → filas de V_NUEVOS_SKU, con id/seq crecientes."""
    return [NuevoSkuFila(i + 1, "tel-1", i + 1, sku, str(cant), fecha)
            for i, (sku, cant, fecha) in enumerate(datos)]


def _ventana(qtbot, sesion=ANA) -> "MainWindow":
    """La ventana completa con datos falsos: sin Oracle, sin hilos y sin sondeo automático."""
    ventana = build_window(FakeRemoto(), auto_refresh_ms=0)
    ventana.comprobar_oracle = lambda: None
    ventana.contar_notificaciones = lambda: None
    ventana._runner = FakeRunner()
    qtbot.addWidget(ventana)
    ventana.show()
    ventana.iniciar(sesion)
    vista = ventana.paginas.currentWidget()
    if hasattr(vista, "refresh"):
        vista.refresh = lambda: None   # el flujo refresca la vista actual: en la prueba no consulta Oracle
    return ventana


# ------------------------------------------------------------------ el widget
def test_el_aviso_muestra_una_tarjeta_por_sku_agrupado(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    aviso.mostrar(_filas(("khs", 3, AHORA), ("KHS", 2, AHORA), ("77700", 1, None)))

    assert aviso.isVisible()
    assert aviso.skus() == ["KHS", "77700"]          # agrupado por SKU normalizado en mayúsculas
    tarjeta = aviso.tarjetas()[0]
    assert tarjeta.lbl_titulo.text() == "Nuevo SKU"
    assert tarjeta.lbl_sku.text() == "KHS"
    assert tarjeta.lbl_subtitulo.text() == "2 lecturas · última 16/11 05:20"
    assert tarjeta.btn_crear.text() == "Crear y procesar"
    assert tarjeta.btn_no_crear.text() == "No crear"
    assert aviso.tarjetas()[1].lbl_subtitulo.text() == "1 lectura"


def test_mas_de_tres_sku_muestra_el_resto(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    aviso.mostrar(_filas(*[(sku, 1, AHORA) for sku in ("A1", "A2", "A3", "A4", "A5")]))
    assert aviso.skus() == ["A1", "A2", "A3"]
    assert aviso.mas() == "+2 más"


def test_los_botones_emiten_el_sku_y_ocultar_limpia(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    aviso.mostrar(_filas(("khs", 1, AHORA)))
    with qtbot.waitSignal(aviso.crear_solicitado, timeout=2000) as crear:
        qtbot.mouseClick(aviso.tarjetas()[0].btn_crear, Qt.MouseButton.LeftButton)
    assert crear.args == ["KHS"]
    with qtbot.waitSignal(aviso.descartar_solicitado, timeout=2000) as descartar:
        qtbot.mouseClick(aviso.tarjetas()[0].btn_no_crear, Qt.MouseButton.LeftButton)
    assert descartar.args == ["KHS"]
    aviso.mostrar([])
    assert not aviso.isVisible() and aviso.skus() == []


def test_la_x_oculta_la_tarjeta_y_reaparece_con_lecturas_nuevas(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    filas = _filas(("A1", 1, AHORA), ("A2", 1, AHORA))
    aviso.mostrar(filas)
    qtbot.mouseClick(aviso.tarjetas()[0].btn_cerrar, Qt.MouseButton.LeftButton)
    assert aviso.skus() == ["A2"]
    assert aviso.ocultos() == "1 oculto · mostrar"
    aviso.mostrar(filas)                               # el sondeo repite lo mismo: sigue oculto
    assert aviso.skus() == ["A2"]
    aviso.mostrar(_filas(("A1", 1, AHORA), ("A2", 1, AHORA), ("A1", 1, AHORA)))   # llega otra lectura de A1
    assert aviso.skus() == ["A1", "A2"]
    assert aviso.ocultos() == ""


def test_cerrar_todas_deja_el_enlace_para_mostrarlas(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    aviso.mostrar(_filas(("A1", 1, AHORA), ("A2", 1, AHORA)))
    aviso.cerrar_sku("A1")
    aviso.cerrar_sku("a2")
    assert aviso.skus() == []
    assert aviso.isVisible() and aviso.ocultos() == "2 ocultos · mostrar"
    qtbot.mouseClick(aviso.btn_ocultos, Qt.MouseButton.LeftButton)
    assert aviso.skus() == ["A1", "A2"]


def test_olvidar_quita_solo_ese_sku(qtbot):
    aviso = AvisoNuevoSku()
    qtbot.addWidget(aviso)
    aviso.mostrar(_filas(("KHS", 1, AHORA), ("FUHHY", 1, AHORA)))
    aviso.olvidar("khs")
    assert aviso.skus() == ["FUHHY"]


def test_el_dialogo_muestra_el_sku_en_solo_lectura_y_en_mayusculas(qtbot):
    dialogo = DialogoNuevoSku("khs")
    qtbot.addWidget(dialogo)
    assert dialogo.txt_sku.text() == "KHS" and dialogo.txt_sku.isReadOnly()
    dialogo.txt_nombre.setText("Producto nuevo")
    dialogo._aceptar()                                  # falta la categoría: no se acepta
    assert dialogo.result() == 0 and not dialogo.lbl_error.isHidden()
    dialogo.txt_categoria.setText("Aseo")
    dialogo._aceptar()
    assert dialogo.result() == QDialog.DialogCode.Accepted
    assert dialogo.datos() == ("KHS", "Producto nuevo", "Aseo")


# ------------------------------------------------------------------ overlay, no layout
def test_el_aviso_flota_sobre_el_contenido_arriba_a_la_derecha(qtbot):
    ventana = _ventana(qtbot)
    ventana.resize(1240, 800)
    qtbot.wait(20)
    aviso = ventana.aviso_nuevo_sku
    aviso.mostrar(_filas(("KHS", 1, AHORA)))
    assert aviso.parentWidget() is ventana and aviso.isVisible()
    area = ventana.area_contenido()
    assert area.contains(aviso.geometry())
    assert aviso.geometry().right() >= area.right() - 40          # pegado a la derecha
    ventana.resize(1000, 700)
    qtbot.wait(30)
    assert ventana.area_contenido().contains(aviso.geometry())     # se recoloca al redimensionar


# ------------------------------------------------------------------ flujos (runner falso)
def test_crear_y_procesar_da_de_alta_con_el_sku_del_aviso(qtbot, monkeypatch):
    pendientes = _filas(("khs", 3, AHORA))
    llamadas = []

    def fetch_nuevos():
        return list(pendientes)

    def alta(quien, sku, nombre, categoria):
        llamadas.append((quien.usuario, sku, nombre, categoria))
        pendientes.clear()                             # la lectura ya está procesada: el aviso desaparece

    monkeypatch.setattr(db, "fetch_nuevos_sku", fetch_nuevos)
    monkeypatch.setattr(db, "nuevo_sku_alta", alta)
    monkeypatch.setattr(DialogoNuevoSku, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DialogoNuevoSku, "datos", lambda self: ("KHS", "Producto nuevo", "Aseo"))

    ventana = _ventana(qtbot)
    ventana._consultar_nuevos_sku()
    aviso = ventana.aviso_nuevo_sku
    assert aviso.isVisible() and aviso.skus() == ["KHS"]

    qtbot.mouseClick(aviso.tarjetas()[0].btn_crear, Qt.MouseButton.LeftButton)

    assert llamadas == [("ana.gomez", "KHS", "Producto nuevo", "Aseo")]
    assert "SKU creado KHS · lectura procesada" in ventana.avisos_visibles()
    assert not aviso.isVisible()                       # se quitó el SKU y el sondeo ya no lo trae


def test_no_crear_confirma_y_descarta_la_lectura(qtbot, monkeypatch):
    pendientes = _filas(("khs", 2, AHORA))
    descartes = []
    capturado = {}

    def fetch_nuevos():
        return list(pendientes)

    def descartar(quien, sku):
        descartes.append((quien.usuario, sku))
        pendientes.clear()

    def confirmar(self, titulo, descripcion="", al_confirmar=None, al_cancelar=None,
                  verbo="Confirmar", cancelar="Cancelar", peligro=True, entiendo=False):
        capturado.update(titulo=titulo, descripcion=descripcion, verbo=verbo, al_confirmar=al_confirmar)
        return 0

    monkeypatch.setattr(db, "fetch_nuevos_sku", fetch_nuevos)
    monkeypatch.setattr(db, "descartar_nuevo_sku", descartar)
    monkeypatch.setattr(GestorIsla, "confirmar", confirmar)

    ventana = _ventana(qtbot)
    ventana._consultar_nuevos_sku()
    aviso = ventana.aviso_nuevo_sku
    qtbot.mouseClick(aviso.tarjetas()[0].btn_no_crear, Qt.MouseButton.LeftButton)

    assert capturado["titulo"] == "¿No tomar la lectura?"
    assert capturado["descripcion"] == "El SKU KHS no se contará."
    assert capturado["verbo"] == "No crear"
    assert descartes == []                              # nada se ejecuta hasta confirmar
    capturado["al_confirmar"]()
    assert descartes == [("ana.gomez", "KHS")]
    assert "Lectura descartada KHS" in ventana.avisos_visibles()
    assert not aviso.isVisible()


def test_sin_permiso_el_aviso_no_se_cierra_y_el_motivo_va_a_la_isla(qtbot, monkeypatch):
    pendientes = _filas(("khs", 1, AHORA))

    def sin_permiso(quien, sku, nombre, categoria):
        raise ErrorDeAcceso("Solo el Administrador puede dar de alta un SKU.")

    monkeypatch.setattr(db, "fetch_nuevos_sku", lambda: list(pendientes))
    monkeypatch.setattr(db, "nuevo_sku_alta", sin_permiso)
    monkeypatch.setattr(DialogoNuevoSku, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(DialogoNuevoSku, "datos", lambda self: ("KHS", "Producto nuevo", "Aseo"))

    ventana = _ventana(qtbot, LUIS)
    ventana._consultar_nuevos_sku()
    aviso = ventana.aviso_nuevo_sku
    qtbot.mouseClick(aviso.tarjetas()[0].btn_crear, Qt.MouseButton.LeftButton)

    assert any("Solo el Administrador" in texto for texto in ventana.avisos_visibles())
    assert aviso.isVisible() and aviso.skus() == ["KHS"]   # se queda para reintentar o descartar


def test_al_cerrar_sesion_el_aviso_y_su_sondeo_se_apagan(qtbot, monkeypatch):
    monkeypatch.setattr(db, "fetch_nuevos_sku", lambda: _filas(("khs", 1, AHORA)))
    ventana = _ventana(qtbot)
    ventana._consultar_nuevos_sku()
    assert ventana.aviso_nuevo_sku.isVisible()
    ventana.cerrar_sesion()
    assert not ventana.aviso_nuevo_sku.isVisible()
    assert not ventana._timer_nuevos.isActive()


# --------------------------------------------------- la campana al aparecer un SKU nuevo
def test_el_sondeo_refresca_la_campana_cuando_cambia_el_conjunto_de_nuevos(qtbot, monkeypatch):
    """``fetch_nuevos_sku`` deja el aviso en Notificaciones: si aparece o se resuelve un SKU, el contador
    de la campana se actualiza ya, sin esperar al refresco global."""
    lotes = [
        _filas(("khs", 1, AHORA)),
        _filas(("khs", 1, AHORA)),                                    # mismo conjunto: no se refresca
        _filas(("khs", 1, AHORA), ("fuhhy", 1, AHORA)),
        _filas(),                                                     # resuelto: tampoco hace falta
    ]
    monkeypatch.setattr(db, "fetch_nuevos_sku", lambda: list(lotes.pop(0)))
    ventana = _ventana(qtbot)
    campana: list[int] = []
    ventana.contar_notificaciones = lambda: campana.append(1)

    ventana._consultar_nuevos_sku()   # aparece KHS
    ventana._consultar_nuevos_sku()   # sigue igual
    ventana._consultar_nuevos_sku()   # aparece FUHHY
    ventana._consultar_nuevos_sku()   # ya no hay pendientes
    assert len(campana) == 3

