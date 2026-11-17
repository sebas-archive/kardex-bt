"""Copia las capturas de la APK generadas por CapturasTest (Compose + Robolectric nativo, 1080×2340) y arma montajes de
3×2 pantallas para el documento. Son renderizados del código real de la app con datos de ejemplo, NO fotografías de un
teléfono físico (en este equipo no hay un teléfono conectado: `adb devices` está vacío). Uso: sin argumentos, desde la raíz."""
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ORIGEN = Path("mobile/app/build/capturas")
DESTINO = Path("docs/documentacion/capturas/movil")
(DESTINO / "originales").mkdir(parents=True, exist_ok=True)
for p in sorted(ORIGEN.glob("*.png")):
    shutil.copy(p, DESTINO / "originales" / p.name)

F = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 30)
MONTAJES = {
    "movil_montaje_1_acceso": ["01-acceso-entrar", "02-acceso-crear-cuenta", "03-acceso-recuperar",
                                "04-acceso-clave-incorrecta", "05-acceso-bienvenida", "26-estado-cuenta"],
    "movil_montaje_2_captura": ["06-inicio", "08-catalogo", "09-contar", "10-contar-sku-desconocido",
                                 "12-contado-aqui", "13-pendientes"],
    "movil_montaje_3_sincronizacion": ["15-sincronizar-buscar", "16-sincronizar-conectando", "17-sincronizar-enviando",
                                        "18-sincronizar-listo", "19-sincronizar-pc-ocupado", "20-sincronizar-sin-conexion"],
    "movil_montaje_4_apariencia": ["14-notificaciones", "21-mi-cuenta", "25-foto-editor",
                                    "22-inicio-oscuro", "23-contar-oscuro", "24-acceso-oscuro"],
}
ROTULOS = {
    "01-acceso-entrar": "Acceso", "02-acceso-crear-cuenta": "Crear cuenta", "03-acceso-recuperar": "Recuperar contraseña",
    "04-acceso-clave-incorrecta": "Error de acceso", "05-acceso-bienvenida": "Bienvenida", "26-estado-cuenta": "Cuenta pendiente",
    "06-inicio": "Inicio", "08-catalogo": "Catálogo", "09-contar": "Contar", "10-contar-sku-desconocido": "SKU fuera del catálogo",
    "12-contado-aqui": "Contado", "13-pendientes": "Pendientes",
    "15-sincronizar-buscar": "Buscando el PC", "16-sincronizar-conectando": "Conectando", "17-sincronizar-enviando": "Enviando lecturas",
    "18-sincronizar-listo": "Listo", "19-sincronizar-pc-ocupado": "PC ocupado", "20-sincronizar-sin-conexion": "Sin conexión",
    "14-notificaciones": "Notificaciones", "21-mi-cuenta": "Mi cuenta", "25-foto-editor": "Editor de foto",
    "22-inicio-oscuro": "Inicio (oscuro)", "23-contar-oscuro": "Contar (oscuro)", "24-acceso-oscuro": "Acceso (oscuro)",
}
PW, PH, GAP, ETI = 540, 1170, 24, 50
for nombre, partes in MONTAJES.items():
    hoja = Image.new("RGB", (3 * PW + 4 * GAP, 2 * (PH + ETI) + 3 * GAP), "white")
    d = ImageDraw.Draw(hoja)
    for i, p in enumerate(partes):
        im = Image.open(ORIGEN / f"{p}.png").convert("RGB").resize((PW, PH), Image.LANCZOS)
        x = GAP + (i % 3) * (PW + GAP)
        y = GAP + (i // 3) * (PH + ETI + GAP)
        d.text((x, y), ROTULOS[p], font=F, fill="black")
        hoja.paste(im, (x, y + ETI))
        d.rectangle([x - 1, y + ETI - 1, x + PW, y + ETI + PH], outline="#9ca3af")
    hoja.save(DESTINO / f"{nombre}.png")
    print(nombre, hoja.size)
