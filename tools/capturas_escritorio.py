#!/usr/bin/env python3
"""Capturas de la aplicación de escritorio con **datos de ejemplo** (no toca Oracle ni el Bluetooth).

Arma la ventana real con las consultas reemplazadas por un conteo ficticio de 58 SKU y guarda un PNG por pantalla
en ``docs/img/``. Sirve para revisar el diseño y para la documentación; no prueba la conexión a la base.

    docker compose run --rm -e QT_QPA_PLATFORM=offscreen -e APP_SIN_ANIMACIONES=1 app python tools/capturas_escritorio.py
"""

from __future__ import annotations

import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("APP_SIN_ANIMACIONES", "1")  # cada cuadro sale en su estado final

RAIZ = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RAIZ / "desktop"), str(RAIZ / "server"), str(RAIZ / "desktop" / "tests")]

from PyQt6.QtWidgets import QApplication  # noqa: E402

from app import auth, db  # noqa: E402
from app.main import build_window  # noqa: E402
from app.models import Conteo, ErrorFila, EstadoBatch, FilaConciliacion, Lectura, ResumenConteo  # noqa: E402
from app.sync_bridge import SyncBridge  # noqa: E402
from fakes import FakeStore, FakeTransport  # noqa: E402

C = "CONT-2026-11"
CATEGORIAS = {"Abarrotes": ("Arroz", "Azúcar", "Sal", "Aceite", "Pasta", "Harina", "Lentejas", "Fríjol", "Café", "Panela", "Avena", "Atún"),
              "Aseo": ("Jabón", "Detergente", "Suavizante", "Cloro", "Esponja", "Limpiapisos", "Lavaloza", "Papel higiénico", "Servilletas"),
              "Bebidas": ("Gaseosa", "Jugo", "Agua", "Té frío", "Malta", "Energizante", "Avena líquida", "Refresco"),
              "Lácteos": ("Leche", "Yogur", "Queso", "Mantequilla", "Kumis", "Crema de leche", "Arequipe"),
              "Snacks": ("Papas", "Galletas", "Chocolatina", "Maní", "Platanitos", "Gomas", "Rosquitas", "Ponqué"),
              "Cuidado personal": ("Champú", "Crema dental", "Desodorante", "Jabón de tocador", "Cepillo", "Toallas", "Gel", "Talco",
                                   "Crema corporal", "Enjuague", "Algodón", "Protector solar", "Cuchillas", "Pañitos")}
OPERADORES = ("Ana Gómez", "Luis Ortiz", "Marta Ruiz", "Carlos Peña")
T0 = datetime(2026, 11, 12, 8, 0)


def conteo_de_ejemplo() -> list[FilaConciliacion]:
    """58 SKU: la mayoría cuadra, algunos faltan o sobran y unos pocos no se contaron."""
    azar = random.Random(42)
    filas, n = [], 0
    for categoria, nombres in CATEGORIAS.items():
        for nombre in nombres:
            n += 1
            sku = f"77012340{n:05d}"
            costo = azar.choice((1200, 1800, 2500, 3200, 4800, 6500, 9800, 14500))
            sistema = float(azar.randint(12, 220))
            suerte = azar.random()
            if suerte < 0.08:
                filas.append(FilaConciliacion(sku, nombre, categoria, sistema, 0.0, None, None, None, "SIN_CONTAR"))
                continue
            dif = 0.0 if suerte < 0.62 else float(azar.choice((-18, -9, -6, -4, -2, -1, 1, 2, 3, 5, 8, 14)))
            contada = max(0.0, sistema + dif)
            pct = round(100 * dif / sistema, 2)
            clase = "OK" if abs(pct) <= 1.0 else "FALTANTE" if dif < 0 else "SOBRANTE"
            filas.append(FilaConciliacion(sku, nombre, categoria, sistema, contada, dif, pct, dif * costo, clase))
    return filas


FILAS = conteo_de_ejemplo()
ANA = auth.Sesion("ana.gomez", "Ana Gómez", auth.ADMIN)


def resumen() -> ResumenConteo:
    contados = [f for f in FILAS if f.clasificacion != "SIN_CONTAR"]
    cuenta = {c: sum(f.clasificacion == c for f in FILAS) for c in ("OK", "FALTANTE", "SOBRANTE")}
    valor = {c: sum(f.valor_diferencia for f in FILAS if f.clasificacion == c) for c in ("FALTANTE", "SOBRANTE")}
    return ResumenConteo(C, len(FILAS), len(contados), round(100 * len(contados) / len(FILAS), 2), cuenta["OK"], cuenta["FALTANTE"],
                         cuenta["SOBRANTE"], round(100 * cuenta["OK"] / len(contados), 2), valor["FALTANTE"], valor["SOBRANTE"])


def conciliacion(id_conteo, clasificacion=None, categoria=None, texto=None, limit=1000, solo_diferencia=False, valor_min=None, orden="sku"):
    filas = [f for f in FILAS
             if (not clasificacion or f.clasificacion == clasificacion) and (not categoria or f.categoria == categoria)
             and (not texto or texto.upper() in f.sku or texto.upper() in f.nombre.upper())]
    return filas[:limit]


def instalar_datos() -> None:
    """Reemplaza las consultas de ``app.db`` y la lista de cuentas por los datos de ejemplo."""
    azar = random.Random(7)
    por_categoria = sorted({f.categoria for f in FILAS})
    actividad = [(op, f"{T0 + timedelta(hours=h):%Y-%m-%d %H:%M}", azar.randint(4, 26)) for h in range(7) for op in OPERADORES[: 2 + h % 3]]
    errores = [ErrorFila(900 + i, f"7c1e-ana-{i % 2}", 40 + i, motivo, f"REC|{40 + i}|1794480000000|{C}|{sku}|{cant}|Ana Gómez|", T0)
               for i, (motivo, sku, cant) in enumerate((("SKU_DESCONOCIDO", "7709990001234", "3"), ("SKU_DESCONOCIDO", "7709990005678", "12"),
                                                        ("CANTIDAD_INVALIDA", FILAS[9].sku, "1,5")))]
    datos = {
        "fetch_conteos": lambda: [Conteo(C, "Inventario físico noviembre 2026", "ABIERTO"), Conteo("CONT-2026-10", "Inventario físico octubre 2026", "CERRADO")],
        "fetch_resumen": lambda id_conteo: resumen(),
        "fetch_conciliacion": conciliacion,
        "fetch_dif_por_categoria": lambda id_conteo: [(c, sum(f.valor_diferencia or 0 for f in FILAS if f.categoria == c)) for c in por_categoria],
        "fetch_top_desvios": lambda id_conteo, n=10: sorted((f for f in FILAS if f.valor_diferencia), key=lambda f: -abs(f.valor_diferencia))[:n],
        "fetch_actividad": lambda id_conteo: actividad,
        "fetch_lecturas": lambda id_conteo, sku: [Lectura(24.0, "Ana Gómez", T0, False, None), Lectura(26.0, "Luis Ortiz", T0 + timedelta(minutes=9), True, "recuento")],
        "fetch_estado_batch": lambda: EstadoBatch(6, 0, 412, len(errores), T0 + timedelta(hours=7, minutes=12), "SYNC"),
        "fetch_errores": lambda limit=100: errores,
    }
    for nombre, funcion in datos.items():
        setattr(db, nombre, funcion)
    auth.listar = lambda: [auth.Usuario("ana.gomez", "Ana Gómez", auth.ADMIN, True), auth.Usuario("luis", "Luis Ortiz", auth.INVENTARIO, True),
                           auth.Usuario("marta.ruiz", "Marta Ruiz", auth.INVENTARIO, True), auth.Usuario("carlos", "Carlos Peña", auth.INVENTARIO, False)]


def main() -> int:
    destino = RAIZ / "docs" / "img"
    for vieja in destino.glob("escritorio-*.png"):
        vieja.unlink()
    app = QApplication(sys.argv)
    instalar_datos()
    puente = SyncBridge(FakeTransport(), FakeStore(), discoverable_s=120)
    ventana = build_window(puente, auto_refresh_ms=0)
    ventana.resize(1280, 800)
    ventana.show()
    guardadas = []

    def asentar(ms: int = 700) -> None:
        fin = datetime.now() + timedelta(milliseconds=ms)
        while datetime.now() < fin:
            app.processEvents()

    def capturar(nombre: str) -> None:
        asentar()
        ruta = destino / f"escritorio-{nombre}.png"
        ventana.grab().save(str(ruta))
        guardadas.append(ruta.name)

    # Acceso: iniciar sesión y crear cuenta.
    ventana.acceso.txt_usuario.setText("ana.gomez")
    ventana.acceso.txt_clave.setText("conteo2026")
    capturar("01-acceso")
    ventana.acceso.mostrar_formulario(1)
    ventana.acceso.txt_nombre.setText("Luis Ortiz")
    ventana.acceso.txt_usuario_nuevo.setText("luis")
    ventana.acceso.txt_clave_nueva.setText("Conteo-2026")
    ventana.acceso.txt_confirmacion.setText("Conteo-2026")
    capturar("02-crear-cuenta")

    ventana.iniciar(ANA)
    asentar(1500)
    for numero, titulo in enumerate(("Dashboard", "Inventario", "Sincronización", "Gráficas", "Perfil", "Usuarios"), start=3):
        ventana.ir_a(titulo)
        if titulo == "Sincronización":
            puente.start()
        if titulo == "Usuarios":
            ventana.vista("Usuarios").seleccionar("luis")
        capturar(f"{numero:02d}-{titulo.lower().replace('ó', 'o').replace('á', 'a')}")
        if titulo == "Sincronización":
            puente.cancel()
    print("\n".join(guardadas))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
