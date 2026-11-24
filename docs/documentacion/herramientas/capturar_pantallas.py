"""Captura las pantallas REALES de la aplicación de escritorio (PyQt6) ejecutándose contra Oracle.

No dibuja nada propio: construye ``app.main.build_window`` (la misma ventana que abre ``python -m app.main``),
inicia sesión con las cuentas de demostración, navega a cada sección y guarda ``QWidget.grab()``.
Se ejecuta dentro de la imagen ``inventario-bt-app`` con Oracle en marcha (ver ``capturar.sh``).

Uso: python capturar_pantallas.py <carpeta_salida>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APP_SIN_ANIMACIONES", "1")   # estado final de cada vista, sin esperar a las animaciones

from PyQt6.QtTest import QTest                      # noqa: E402
from PyQt6.QtWidgets import QApplication            # noqa: E402

SALIDA = Path(sys.argv[1] if len(sys.argv) > 1 else "capturas")
CLAVE_DEMO = os.environ.get("CLAVE_DEMO", "Demo1234")   # cuenta de demostración documentada en el README


def esperar(ms: int = 1800) -> None:
    """Deja correr el bucle de eventos: las consultas salen en hilos y vuelven por señales."""
    QTest.qWait(ms)


def guardar(widget, ruta: str) -> None:
    destino = SALIDA / ruta
    destino.parent.mkdir(parents=True, exist_ok=True)
    pix = widget.grab()
    pix.save(str(destino), "PNG")
    print(f"{destino} {pix.width()}x{pix.height()}")


def principal() -> int:
    app = QApplication(sys.argv)
    from app.main import build_window
    from app.servicio_remoto import ServicioRemoto
    from app.views.base import estilo
    from app import auth, i18n

    app.setApplicationName("Kardex")
    app.setStyleSheet(estilo())

    # 1. Pantalla de acceso (sin sesión)
    ventana = build_window(ServicioRemoto())
    ventana.resize(1240, 800)
    ventana.show()
    esperar(1500)
    guardar(ventana, "aplicacion/acceso/01_acceso.png")
    ventana.close()

    for usuario, carpeta in (("admin", "roles/administrador"), ("inventario", "roles/inventario")):
        sesion = auth.iniciar_sesion(usuario, CLAVE_DEMO)
        ventana = build_window(ServicioRemoto(), sesion=sesion)
        ventana.resize(1240, 800)
        ventana.show()
        esperar(2500)
        secciones = ventana.secciones()
        print(usuario, sesion.rol, secciones)
        for i, titulo in enumerate(secciones, 1):
            ventana.ir_a(titulo)
            esperar(2600)
            nombre = titulo.lower().replace(" ", "_").replace("ó", "o").replace("í", "i").replace("á", "a")
            guardar(ventana, f"{carpeta}/{i:02d}_{nombre}.png")
        if usuario == "admin":
            # Perfil, notificaciones (hoja flotante) y navegación
            ventana.abrir_perfil()
            esperar(2000)
            guardar(ventana, "roles/administrador/20_perfil.png")
            ventana.abrir_hoja_notificaciones()
            esperar(1500)
            guardar(ventana, "aplicacion/navegacion/notificaciones_hoja.png")
            ventana.ir_a(secciones[0])
            esperar(2200)
            guardar(ventana, "aplicacion/pantalla_principal/dashboard_admin_1240x800.png")
            # Resoluciones
            for ancho, alto in ((900, 600), (1920, 1080)):
                ventana.resize(ancho, alto)
                esperar(1800)
                guardar(ventana, f"aplicacion/resoluciones/dashboard_{ancho}x{alto}.png")
                ventana.ir_a(i18n.t("Inventario"))
                esperar(1800)
                guardar(ventana, f"aplicacion/resoluciones/inventario_{ancho}x{alto}.png")
                ventana.ir_a(secciones[0])
            ventana.resize(1240, 800)
            # Barra lateral contraída
            ventana.alternar_lateral()
            esperar(1200)
            guardar(ventana, "aplicacion/navegacion/lateral_contraida.png")
            ventana.alternar_lateral()
            esperar(800)
            # Reconstrucción de las vistas (tras aplicar tema e idioma): se captura el estado de carga inicial
            ventana._aplicar_tema_idioma("oscuro", "es")
            ventana._reconstruir_vistas()
            esperar(2500)
            guardar(ventana, "aplicacion/pantalla_principal/dashboard_estado_de_carga.png")
            ventana.ir_a(i18n.t("Inventario"))
            esperar(2000)
            guardar(ventana, "aplicacion/pantalla_principal/inventario_tras_reconstruir_vistas.png")
        ventana.close()
        esperar(300)
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
