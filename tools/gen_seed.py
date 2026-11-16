#!/usr/bin/env python3
"""Genera de forma reproducible la semilla de inventario.

Produce dos archivos a partir de una semilla aleatoria fija:
  * db/init/02_seed.sql  -> catalogos, conteo continuo ACTUAL y stock del sistema.
  * tools/truth.json     -> el stock FISICO "real" por SKU, del que parte fake_phone.py.

Uso: python tools/gen_seed.py --seed 42
"""

import argparse
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTEO_ID = "ACTUAL"
CONTEO_NOMBRE = "Conteo continuo"
SKU_PREFIX = "770123400"  # + 4 digitos = 13 digitos (estilo EAN-13)
N_SIN_STOCK = 2           # SKUs que existen en el catalogo con stock 0 (siempre tienen fila)

# (categoria, tolerancia_pct, [(nombre, unidad, costo COP)])
CATEGORIAS = [
    ("Abarrotes", 2.0, [
        ("Arroz 500 g", "UND", 2400), ("Azúcar 1 kg", "UND", 3900),
        ("Aceite de Girasol 1 L", "UND", 11500), ("Lentejas 500 g", "UND", 3100),
        ("Fríjol Cargamanto 500 g", "UND", 7800), ("Harina de Trigo 1 kg", "UND", 3600),
        ("Sal Refinada 500 g", "UND", 1300), ("Pasta Espagueti 250 g", "UND", 2300),
        ("Atún en Lata 160 g", "UND", 5200), ("Panela Cuadrada 500 g", "UND", 2900),
        ("Café Molido 250 g", "UND", 9800), ("Avena en Hojuelas 400 g", "UND", 4100),
        ("Galletas Saltinas x6", "UND", 3400), ("Aceite de Oliva 250 mL", "UND", 14800),
        ("Salsa de Tomate 400 g", "UND", 4600),
    ]),
    ("Bebidas", 2.0, [
        ("Agua Botella 600 mL", "UND", 1800), ("Gaseosa Cola 1.5 L", "UND", 4800),
        ("Jugo de Naranja 1 L", "UND", 4300), ("Cerveza Lata 330 mL", "UND", 2900),
        ("Té Frío 500 mL", "UND", 3100), ("Bebida Energizante 250 mL", "UND", 4700),
        ("Agua con Gas 600 mL", "UND", 2200), ("Jugo de Mora 1 L", "UND", 4500),
        ("Gaseosa Lima-Limón 400 mL", "UND", 2400), ("Agua Saborizada 500 mL", "UND", 2600),
        ("Malta 330 mL", "UND", 2700), ("Bebida Hidratante 500 mL", "UND", 3600),
        ("Agua de Coco 330 mL", "UND", 3900), ("Café Frío en Lata 250 mL", "UND", 4200),
        ("Limonada 1 L", "UND", 3800),
    ]),
    ("Aseo", 1.0, [
        ("Jabón de Barra 300 g", "UND", 2100), ("Detergente en Polvo 1 kg", "UND", 8900),
        ("Suavizante 1 L", "UND", 7400), ("Cloro 1 L", "UND", 3200),
        ("Lavaplatos 500 g", "UND", 4300), ("Papel Higiénico x4", "UND", 6800),
        ("Servilletas x100", "UND", 2500), ("Esponja Multiusos", "UND", 1500),
        ("Limpiador de Pisos 1 L", "UND", 6100), ("Bolsas de Basura x10", "UND", 3700),
        ("Jabón Líquido Manos 500 mL", "UND", 5400), ("Trapero de Algodón", "UND", 8200),
        ("Desinfectante 900 mL", "UND", 6400), ("Ambientador Aerosol 360 mL", "UND", 7900),
        ("Toallas de Cocina x2", "UND", 4900),
    ]),
    ("Ferretería", 0.5, [
        ("Martillo 16 oz", "UND", 24500), ("Destornillador de Pala 6 mm", "UND", 8900),
        ("Alicate Universal 8 in", "UND", 21800), ("Cinta Métrica 5 m", "UND", 13900),
        ("Cinta Aislante 10 m", "UND", 3800), ("Tornillos Caja x100", "UND", 7200),
        ("Puntillas 2 in 1 lb", "UND", 5400), ("Candado 40 mm", "UND", 15700),
        ("Bombillo LED 9 W", "UND", 6200), ("Extensión Eléctrica 3 m", "UND", 14800),
        ("Guantes de Carnaza", "PAR", 9600), ("Brocha 2 in", "UND", 5100),
        ("Llave Inglesa 10 in", "UND", 32500), ("Nivel de Burbuja 12 in", "UND", 11800),
        ("Taladro Percutor 600 W", "UND", 189000),
    ]),
    ("Lácteos", 0.0, [
        ("Leche Entera 1 L", "UND", 4200), ("Leche Deslactosada 1 L", "UND", 4900),
        ("Yogurt de Fresa 1 L", "UND", 6300), ("Queso Campesino 500 g", "UND", 11800),
        ("Queso Mozzarella 500 g", "UND", 15200), ("Mantequilla 250 g", "UND", 7600),
        ("Kumis 1 L", "UND", 5800), ("Crema de Leche 200 mL", "UND", 4400),
        ("Arequipe 250 g", "UND", 6900), ("Cuajada 500 g", "UND", 8700),
        ("Leche en Polvo 400 g", "UND", 17900), ("Yogurt Natural 1 L", "UND", 5600),
        ("Queso Crema 200 g", "UND", 6200), ("Leche de Almendras 1 L", "UND", 9800),
        ("Yogurt Griego 150 g", "UND", 3300),
    ]),
    ("Papelería", 1.0, [
        ("Cuaderno 100 Hojas", "UND", 3900), ("Lápiz HB x12", "UND", 6800),
        ("Bolígrafo Azul x12", "UND", 9200), ("Resma Carta 500 h", "UND", 18900),
        ("Marcadores x6", "UND", 11400), ("Cinta de Enmascarar", "UND", 2900),
        ("Pegante en Barra", "UND", 2600), ("Tijeras Escolares", "UND", 4100),
        ("Carpeta Plástica", "UND", 1800), ("Calculadora Básica", "UND", 22900),
        ("Resaltadores x4", "UND", 8600), ("Notas Adhesivas x3", "UND", 5200),
        ("Sacapuntas", "UND", 1200), ("Borrador de Nata", "UND", 900),
        ("Regla 30 cm", "UND", 1700),
    ]),
    ("Cuidado Personal", 1.0, [
        ("Shampoo 400 mL", "UND", 12900), ("Jabón de Tocador x3", "UND", 5800),
        ("Crema Dental 100 g", "UND", 4900), ("Cepillo Dental", "UND", 3200),
        ("Desodorante Roll-on", "UND", 9400), ("Toallas Higiénicas x10", "UND", 6100),
        ("Crema Corporal 400 mL", "UND", 15800), ("Protector Solar 120 mL", "UND", 38900),
        ("Enjuague Bucal 500 mL", "UND", 14200), ("Afeitadora Desechable x3", "UND", 6700),
        ("Acondicionador 400 mL", "UND", 13600), ("Gel Antibacterial 250 mL", "UND", 7300),
        ("Pañitos Húmedos x80", "UND", 8900), ("Cortaúñas", "UND", 4500),
        ("Peine", "UND", 3100),
    ]),
    ("Mascotas", 2.0, [
        ("Concentrado Perro 2 kg", "UND", 28900), ("Concentrado Gato 1.5 kg", "UND", 31200),
        ("Arena para Gato 4 kg", "UND", 19800), ("Snack para Perro 100 g", "UND", 5600),
        ("Collar Mediano", "UND", 14900), ("Correa 1.5 m", "UND", 17600),
        ("Plato Metálico", "UND", 8800), ("Juguete de Hueso", "UND", 7200),
        ("Shampoo para Mascotas 250 mL", "UND", 16400), ("Antipulgas Spot-on", "UND", 38500),
        ("Cama Pequeña", "UND", 54900), ("Pelota de Goma", "UND", 4800),
        ("Rascador de Cartón", "UND", 21500), ("Pechera Ajustable", "UND", 24800),
        ("Comida Húmeda Gato 85 g", "UND", 3100),
    ]),
]

def lit(texto: str) -> str:
    """Literal SQL seguro para sqlplus sin depender de NLS_LANG (no-ASCII via UNISTR)."""
    if all(ord(c) < 128 for c in texto):
        return "'" + texto.replace("'", "''") + "'"
    partes = []
    for c in texto:
        if c == "'":
            partes.append("''")
        elif ord(c) < 128 and c != "\\":
            partes.append(c)
        else:
            assert ord(c) <= 0xFFFF, f"caracter fuera del BMP: {c!r}"
            partes.append("\\%04X" % ord(c))
    return "UNISTR('" + "".join(partes) + "')"


def construir(seed: int):
    rng = random.Random(seed)

    productos = []  # dicts: sku, nombre, categoria, unidad, costo, tolerancia
    for categoria, tolerancia, items in CATEGORIAS:
        for nombre, unidad, costo in items:
            productos.append({
                "sku": f"{SKU_PREFIX}{len(productos) + 1:04d}",
                "nombre": nombre,
                "categoria": categoria,
                "unidad": unidad,
                "costo": costo,
                "tolerancia": tolerancia,
            })

    # Dos SKUs existen en el catalogo con stock 0 (la fila de stock_sistema siempre existe).
    sin_stock = set(rng.sample(range(len(productos)), N_SIN_STOCK))
    sistema = {}
    for i, p in enumerate(productos):
        bajo, alto = (3, 40) if p["costo"] >= 20000 else (12, 240)   # lo caro rota menos
        sistema[p["sku"]] = 0 if i in sin_stock else rng.randint(bajo, alto)

    # Verdad fisica: ~15 % de los SKUs difiere del sistema; los de stock 0 quedan como sobrantes.
    con_stock = [p for i, p in enumerate(productos) if i not in sin_stock]
    n_desvios = round(0.15 * len(con_stock))
    desviados = {p["sku"] for p in rng.sample(con_stock, n_desvios)}
    fisico_total = {}
    for p in productos:
        sku = p["sku"]
        q = sistema[sku]
        if q == 0:
            fisico_total[sku] = rng.randint(4, 15)  # stock 0: todo lo contado es sobrante
            continue
        if sku in desviados:
            modo = rng.choice(["falta", "sobra", "chico"])
            if modo == "falta":
                q = max(1, q - rng.randint(3, max(4, q // 4)))
            elif modo == "sobra":
                q = q + rng.randint(2, max(3, q // 5))
            else:
                q = max(1, q + rng.choice([-1, 1]))
        fisico_total[sku] = q

    # Lo que hay fisicamente de cada SKU: una cantidad por producto.
    fisico = [{"sku": p["sku"], "cantidad": fisico_total[p["sku"]]} for p in productos]
    fisico.sort(key=lambda r: r["sku"])

    return productos, sistema, fisico


def render_sql(seed: int, productos, sistema) -> str:
    out = [
        f"-- Generado por tools/gen_seed.py --seed {seed}. No editar a mano.",
        "WHENEVER SQLERROR EXIT FAILURE ROLLBACK",
        "SET DEFINE OFF",
        "ALTER SESSION SET CURRENT_SCHEMA = app;",
        "",
        "INSERT INTO conteos (id_conteo, nombre, estado) "
        f"VALUES ({lit(CONTEO_ID)}, {lit(CONTEO_NOMBRE)}, 'ABIERTO');",
    ]
    for p in productos:
        out.append(
            "INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) "
            f"VALUES ({lit(p['sku'])}, {lit(p['nombre'])}, {lit(p['categoria'])}, "
            f"{lit(p['unidad'])}, {p['costo']}, {p['tolerancia']});"
        )
    for p in productos:
        out.append(
            "INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) "
            f"VALUES ({lit(CONTEO_ID)}, {lit(p['sku'])}, {sistema[p['sku']]});"
        )
    out += ["", "COMMIT;", ""]
    return "\n".join(out)


def render_truth(sistema, fisico) -> str:
    doc = {
        "conteo": CONTEO_ID,
        "sistema": sistema,
        "fisico": fisico,
    }
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--sql", type=Path, default=ROOT / "db" / "init" / "02_seed.sql")
    parser.add_argument("--truth", type=Path, default=ROOT / "tools" / "truth.json")
    args = parser.parse_args()

    productos, sistema, fisico = construir(args.seed)
    args.sql.write_bytes(render_sql(args.seed, productos, sistema).encode("utf-8"))
    args.truth.write_bytes(render_truth(sistema, fisico).encode("utf-8"))


if __name__ == "__main__":
    main()
