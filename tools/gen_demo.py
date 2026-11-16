#!/usr/bin/env python3
"""Genera de forma reproducible los datos de demostración: db/init/08_demo.sql.

Parte del catálogo de gen_seed.py (mismos --seed) y le añade 13 meses de historia para que todas las pantallas
y gráficas tengan algo que mostrar:

  * cuentas: Administrador, Inventario, 4 operadores del celular y 3 solicitudes (pendientes y rechazada);
  * 4 teléfonos, sesiones de sincronización, lecturas con recuentos, dañados, errores y SKU nuevos;
  * corridas del batch (con y sin errores) y la conciliación recalculada con PKG_BATCH.

Las fechas son relativas al momento en que Oracle crea la base (hoy, ayer, hace 30 días...).
Contraseña de las cuentas del PC: ver CLAVE_DEMO.

Uso (desde la raíz):  python tools/gen_seed.py --seed 42 && python tools/gen_demo.py --seed 42
"""

import argparse
import math
from datetime import date, timedelta
import base64
import hashlib
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_seed  # noqa: E402
from gen_seed import lit  # noqa: E402

CLAVE_DEMO = "Demo1234"
RESPUESTA_DEMO = "bogota"
PREGUNTA_ADMIN = "¿En qué ciudad naciste?"
DIAS = 400   # un año y un mes de historia

# (usuario, nombre, uuid del teléfono, nombre del teléfono, peso)
OPERADORES = [
    ("ana.torres", "Ana Torres", "dev-ana-0001", "Celular de Ana", 0.35),
    ("luis.gomez", "Luis Gómez", "dev-luis-0002", "Celular de Luis", 0.25),
    ("marta.rios", "Marta Ríos", "dev-marta-0003", "Celular de Marta", 0.25),
    ("diego.pena", "Diego Peña", "dev-diego-0004", "Celular de Diego", 0.15),
]

# Probabilidad de que un SKU de la categoría siga SIN contar (el avance por categoría sale desigual).
SIN_CONTAR = {"Abarrotes": 0.05, "Bebidas": 0.08, "Aseo": 0.10, "Ferretería": 0.35, "Lácteos": 0.0,
              "Papelería": 0.20, "Cuidado Personal": 0.15, "Mascotas": 0.40}
# Probabilidad de que una lectura de la categoría traiga unidades dañadas.
DANADOS = {"Abarrotes": 0.12, "Bebidas": 0.22, "Aseo": 0.18, "Ferretería": 0.05, "Lácteos": 0.20,
           "Papelería": 0.08, "Cuidado Personal": 0.10, "Mascotas": 0.18}
NOTAS = ["Caja abierta", "Empaque golpeado", "Estante 3", "Revisar fecha de vencimiento", "Contado dos veces",
         "Pasillo B", "Mercancía mal ubicada", "Etiqueta ilegible"]
# Horas locales de trabajo con su peso (el pico es media mañana y media tarde).
HORAS = [(8, 4), (9, 8), (10, 10), (11, 9), (12, 3), (13, 4), (14, 8), (15, 10), (16, 7), (17, 3)]
UTC_DESDE_LOCAL = 5   # Colombia: UTC-5


def hash_clave(clave: str) -> str:
    """Mismo formato que app.auth.crear_hash (PBKDF2-HMAC-SHA256, 200000 vueltas), sin importar la app."""
    sal = random.SystemRandom().randbytes(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, 200_000)
    return "$".join(("pbkdf2-sha256", "200000", base64.b64encode(sal).decode(), base64.b64encode(derivada).decode()))


def construir(seed: int):
    rng = random.Random(seed + 1000)
    productos, sistema, _ = gen_seed.construir(seed)

    # ---- valor contado final de cada SKU (None = sin contar)
    finales = {}
    for p in productos:
        if rng.random() < SIN_CONTAR[p["categoria"]]:
            finales[p["sku"]] = None
            continue
        s = sistema[p["sku"]]
        if s == 0:
            finales[p["sku"]] = rng.randint(4, 15)
            continue
        r = rng.random()
        if r < 0.58:
            q = s
        elif r < 0.80:
            q = max(0, s - max(1, round(s * rng.uniform(0.04, 0.30))))
        elif r < 0.93:
            q = s + max(1, round(s * rng.uniform(0.03, 0.20)))
        else:
            q = max(0, s + rng.choice([-1, 1]))
        finales[p["sku"]] = q

    # ---- operador por (día, categoría): una persona cubre una categoría en un día
    asignacion = {}

    def operador_de(dia: int, categoria: str):
        clave = (dia, categoria)
        if clave not in asignacion:
            asignacion[clave] = rng.choices(OPERADORES, weights=[o[4] for o in OPERADORES])[0]
        return asignacion[clave]

    horas, pesos = zip(*HORAS)
    eventos = []   # dict(dia, off, kind, ...) con off = (clase, valor) para t()

    def instante(dia: int):
        if dia == 0:
            return ("n", rng.randint(900, 3 * 3600))                       # hace 15 min .. 3 h
        h = rng.choices(horas, weights=pesos)[0]
        seg = (h + UTC_DESDE_LOCAL) * 3600 + rng.randint(0, 3599)
        return ("b", -dia * 86400 + seg)

    # ---- peso de cada día: más actividad reciente, picos en los cierres de trimestre, algo de estacionalidad y sin domingos
    hoy = date.today()
    cierres = [date(y, m, d) for y in (hoy.year - 1, hoy.year) for m, d in ((3, 31), (6, 30), (9, 30), (12, 31))]

    def peso_dia(d: int) -> float:
        f = hoy - timedelta(days=d)
        if f.weekday() == 6 and d > 0:
            return 0.0
        w = (1 + 1.5 * math.exp(-d / 70)) * (1 + 0.35 * math.sin(2 * math.pi * f.timetuple().tm_yday / 365))
        if any(abs((f - c).days) <= 6 for c in cierres):
            w *= 2.6   # conteo de cierre de trimestre
        return w

    pesos_dias = [peso_dia(d) for d in range(DIAS)]

    # ---- lecturas: cada SKU contado se recuenta entre 6 y 14 veces en el año; la más reciente es el valor final
    por_sku = {p["sku"]: p for p in productos}
    for sku, final in finales.items():
        if final is None:
            continue
        p = por_sku[sku]
        n = rng.randint(6, 14)
        dias_de_lectura = sorted(set(rng.choices(range(DIAS), weights=pesos_dias, k=n)), reverse=True)  # del más viejo al más nuevo
        for i, d in enumerate(dias_de_lectura):
            ultima = i == len(dias_de_lectura) - 1
            if ultima:
                cant = final
            elif rng.random() < 0.25:
                cant = final
            else:
                cant = max(0, round(final * rng.uniform(0.75, 1.25)) + rng.choice([-2, -1, 0, 1, 2]))
            dan = None
            if cant >= 1 and rng.random() < DANADOS[p["categoria"]]:
                dan = rng.randint(1, max(1, min(cant, round(cant * 0.2) + 1)))
            op = operador_de(d, p["categoria"])
            eventos.append({"dia": d, "off": instante(d), "tipo": "REC", "op": op, "sku": sku, "cant": cant,
                            "dan": dan, "nota": rng.choice(NOTAS) if rng.random() < 0.18 else "", "vigente": ultima})
    # el recuento más viejo manda: se ordena por tiempo y la última de cada SKU queda vigente
    for ev in eventos:
        ev["_t"] = tiempo(ev["off"])
    eventos.sort(key=lambda e: e["_t"])
    ultimo_por_sku = {}
    for ev in eventos:
        ultimo_por_sku[ev["sku"]] = ev
    for ev in eventos:
        ev["vigente"] = ultimo_por_sku[ev["sku"]] is ev

    # ---- lecturas defectuosas y de SKU nuevo (para Sincronización y los avisos)
    def extra(dia, tipo, texto_raw, op, estado, msg):
        eventos.append({"dia": dia, "off": instante(dia), "tipo": tipo, "op": op, "raw": texto_raw,
                        "estado": estado, "msg": msg, "_t": 0})
    ana, luis, marta, diego = OPERADORES
    sku_ok = productos[5]["sku"]
    plantillas = [
        ("{ts}|ACTUAL|%s|abc|{op}||", "CANTIDAD_INVALIDA"),
        ("{ts}|ACTUAL|%s|5|{op}||9", "DANADOS_INVALIDO"),
        ("{ts}|ACTUAL|%s|-3|{op}||", "CANTIDAD_INVALIDA"),
        ("{ts}|ACTUAL|%s|2,5|{op}||", "CANTIDAD_INVALIDA"),
    ]
    for _ in range(36):
        plantilla, motivo = rng.choice(plantillas)
        d = rng.choices(range(1, DIAS), weights=pesos_dias[1:])[0]
        extra(d, "RAW", plantilla % rng.choice(productos)["sku"], operador_de(d, rng.choice(productos)["categoria"]), "ERROR", motivo)
    extra(0, "RAW", "{ts}|ACTUAL|7701234009901|6|{op}|Producto sin etiqueta del sistema|", ana, "NUEVO_SKU", "SKU_DESCONOCIDO")
    extra(0, "RAW", "{ts}|ACTUAL|7701234009902|12|{op}||1", ana, "NUEVO_SKU", "SKU_DESCONOCIDO")
    extra(5, "RAW", "{ts}|ACTUAL|7701234009903|2|{op}|Regalo de proveedor|", luis, "DESCARTADO", None)
    extra(40, "RAW", "{ts}|ACTUAL|7701234009904|8|{op}|Muestra de proveedor|", marta, "DESCARTADO", None)
    for ev in eventos:
        if ev["_t"] == 0:
            ev["_t"] = tiempo(ev["off"])
    eventos.sort(key=lambda e: e["_t"])

    # ---- sesiones: (operador, día) -> una sincronización al final de la jornada
    grupos = defaultdict(list)
    for ev in eventos:
        grupos[(ev["op"][0], ev["dia"])].append(ev)
    sesiones = []
    for (_, dia), evs in grupos.items():
        evs.sort(key=lambda e: e["_t"])
        fin_lectura = evs[-1]["_t"]
        sesiones.append({"op": evs[0]["op"], "eventos": evs, "t_sync": fin_lectura + rng.randint(120, 480)})
    sesiones.sort(key=lambda s: s["t_sync"])

    # seq contiguo por teléfono, en el orden en que se sincronizan
    contador = defaultdict(int)
    for s in sesiones:
        for ev in s["eventos"]:
            contador[s["op"][2]] += 1
            ev["seq"] = contador[s["op"][2]]
    return productos, sistema, finales, sesiones, rng


# El orden real de los eventos lo da su instante; tiempo() lo convierte a un número comparable
# (segundos desde la medianoche UTC de hoy, y «hace n segundos» se acerca a «ahora» con un tope).
AHORA_TOPE = 12 * 3600   # una hora local del día en que se crea la base no se conoce: «n» se compara como si fuese tarde


def tiempo(off) -> int:
    clase, v = off
    return v if clase == "b" else AHORA_TOPE - v


def sql_t(off) -> str:
    return f"t('{off[0]}', {off[1]})"


def render(seed: int) -> str:
    productos, sistema, finales, sesiones, rng = construir(seed)
    rng2 = random.Random(seed + 2000)
    clave = hash_clave(CLAVE_DEMO)
    resp = hash_clave(RESPUESTA_DEMO)

    o = []
    w = o.append
    w(f"-- Generado por tools/gen_demo.py --seed {seed}. No editar a mano. Borra este archivo para una base sin datos de demo.")
    w("-- Cuentas del PC: admin e inventario, contraseña " + CLAVE_DEMO + ".")
    w("WHENEVER SQLERROR EXIT FAILURE ROLLBACK")
    w("SET DEFINE OFF")
    w("ALTER SESSION SET CURRENT_SCHEMA = app;")
    w("")

    # ---------------------------------------------------------------- cuentas
    def ins(u, nombre, correo, rol, hash_, estado, origen, **kw):
        cols = ["usuario", "nombre", "correo", "rol", "clave_hash", "estado", "origen"]
        vals = [lit(u), lit(nombre), lit(correo) if correo else "NULL", lit(rol) if rol else "NULL",
                lit(hash_), lit(estado), lit(origen)]
        for k, v in kw.items():
            cols.append(k)
            vals.append(v)
        w(f"INSERT INTO usuarios ({', '.join(cols)}) VALUES ({', '.join(vals)});")

    hace = lambda d: f"SYSTIMESTAMP - NUMTODSINTERVAL({d}, 'DAY')"  # noqa: E731
    ins("admin", "Camila Restrepo", "admin@demo.local", "ADMIN", clave, "ACTIVO", "ESCRITORIO",
        pregunta=lit(PREGUNTA_ADMIN), respuesta_hash=lit(resp), creado=hace(420))
    ins("inventario", "Andrés Molina", "inventario@demo.local", "INVENTARIO", clave, "ACTIVO", "ESCRITORIO",
        resuelto_por=lit("admin"), resuelto=hace(417), creado=hace(418))
    for usr, nombre, uuid, _, _ in OPERADORES:
        ins(usr, nombre, None, "OPERADOR", "-", "ACTIVO", "MOVIL", uuid_dispositivo=lit(uuid),
            resuelto_por=lit("admin"), resuelto=hace(414), creado=hace(415))
    ins("sofia.vega", "Sofía Vega", None, None, "-", "PENDIENTE", "MOVIL", creado="SYSTIMESTAMP - NUMTODSINTERVAL(3, 'HOUR')")
    ins("laura.mora", "Laura Mora", "laura.mora@demo.local", None, clave, "PENDIENTE", "ESCRITORIO",
        creado="SYSTIMESTAMP - NUMTODSINTERVAL(1, 'DAY')")
    ins("pedro.ruiz", "Pedro Ruiz", None, None, "-", "RECHAZADO", "MOVIL", motivo=lit("No pertenece a la bodega"),
        resuelto_por=lit("admin"), resuelto=hace(90), creado=hace(91))
    w("")

    # ---------------------------------------------------------------- bloque PL/SQL
    w("DECLARE")
    w("    l_base TIMESTAMP := CAST(TRUNC(SYS_EXTRACT_UTC(SYSTIMESTAMP)) AS TIMESTAMP);")
    w("    l_ahora TIMESTAMP := SYS_EXTRACT_UTC(SYSTIMESTAMP);")
    w("    l_id NUMBER;")
    w("    l_ts TIMESTAMP;")
    w("")
    w("    -- 'b': segundos desde la medianoche UTC de hoy (negativo = días atrás); 'n': segundos antes de ahora.")
    w("    FUNCTION t(p_clase VARCHAR2, p_seg NUMBER) RETURN TIMESTAMP IS")
    w("    BEGIN")
    w("        IF p_clase = 'n' THEN RETURN l_ahora - NUMTODSINTERVAL(p_seg, 'SECOND'); END IF;")
    w("        RETURN l_base + NUMTODSINTERVAL(p_seg, 'SECOND');")
    w("    END;")
    w("")
    w("    FUNCTION ms(p_ts TIMESTAMP) RETURN NUMBER IS")
    w("    BEGIN")
    w("        RETURN ROUND((CAST(p_ts AS DATE) - DATE '1970-01-01') * 86400 * 1000);")
    w("    END;")
    w("")
    w("    PROCEDURE lec(p_dev VARCHAR2, p_seq NUMBER, p_sku VARCHAR2, p_cant NUMBER, p_oper VARCHAR2,")
    w("                  p_nota VARCHAR2, p_dan NUMBER, p_ts TIMESTAMP, p_vig CHAR, p_recv TIMESTAMP) IS")
    w("        l_raw VARCHAR2(4000);")
    w("    BEGIN")
    w("        l_raw := 'REC|' || p_seq || '|' || ms(p_ts) || '|ACTUAL|' || p_sku || '|' || p_cant || '|' || p_oper")
    w("                 || '|' || p_nota || '|' || p_dan;")
    w("        INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw, estado, fecha_recepcion)")
    w("        VALUES (p_dev, p_seq, l_raw, 'PROCESADO', p_recv) RETURNING id_transito INTO l_id;")
    w("        INSERT INTO registros_procesados (id_transito, id_conteo, sku, cantidad, operador, nota, fecha_captura,")
    w("                                          vigente, fecha_procesado, danados)")
    w("        VALUES (l_id, 'ACTUAL', p_sku, p_cant, p_oper, p_nota, p_ts, p_vig, p_recv + NUMTODSINTERVAL(40, 'SECOND'), p_dan);")
    w("    END;")
    w("")
    w("    PROCEDURE cruda(p_dev VARCHAR2, p_seq NUMBER, p_ts TIMESTAMP, p_resto VARCHAR2, p_estado VARCHAR2,")
    w("                    p_msg VARCHAR2, p_recv TIMESTAMP) IS")
    w("        l_raw VARCHAR2(4000);")
    w("    BEGIN")
    w("        l_raw := 'REC|' || p_seq || '|' || ms(p_ts) || '|' || p_resto;")
    w("        INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw, estado, mensaje_error, fecha_recepcion)")
    w("        VALUES (p_dev, p_seq, l_raw, p_estado, p_msg, p_recv);")
    w("    END;")
    w("")
    w("    PROCEDURE ses(p_dev VARCHAR2, p_ini TIMESTAMP, p_n NUMBER, p_proc NUMBER, p_err NUMBER, p_origen VARCHAR2) IS")
    w("        l_fin TIMESTAMP := p_ini + NUMTODSINTERVAL(15 + p_n, 'SECOND');")
    w("    BEGIN")
    w("        INSERT INTO sync_sesiones (uuid_dispositivo, inicio, fin, recibidos, aceptados)")
    w("        VALUES (p_dev, p_ini, l_fin, p_n, p_n);")
    w("        INSERT INTO log_batch (inicio, fin, procesados, errores, origen)")
    w("        VALUES (l_fin + NUMTODSINTERVAL(20, 'SECOND'), l_fin + NUMTODSINTERVAL(24, 'SECOND'), p_proc, p_err, p_origen);")
    w("    END;")
    w("BEGIN")

    ultimos = {}
    for s in sesiones:
        usr, nombre, uuid, _, _ = s["op"]
        evs = s["eventos"]
        # para sesiones de hoy («n») la sincronización ocurre unos minutos después de la última lectura (más cerca de ahora)
        if evs[-1]["off"][0] == "n":
            t_sync = ("n", max(60, evs[-1]["off"][1] - rng2.randint(120, 480)))
        else:
            t_sync = ("b", evs[-1]["off"][1] + rng2.randint(120, 480))
        errores = nuevos = 0
        for ev in evs:
            if ev["tipo"] == "REC":
                p_nota = lit(ev["nota"]) if ev["nota"] else "NULL"
                dan = "NULL" if ev["dan"] is None else ev["dan"]
                w(f"    lec({lit(uuid)}, {ev['seq']}, {lit(ev['sku'])}, {ev['cant']}, {lit(usr)}, {p_nota}, {dan}, "
                  f"{sql_t(ev['off'])}, '{'S' if ev['vigente'] else 'N'}', {sql_t(t_sync)});")
            else:
                resto = ev["raw"].replace("{ts}|", "").replace("{op}", usr)
                if ev["estado"] == "ERROR":
                    errores += 1
                else:
                    nuevos += 1   # NUEVO_SKU y DESCARTADO: ni procesados ni error
                w(f"    cruda({lit(uuid)}, {ev['seq']}, {sql_t(ev['off'])}, {lit(resto)}, {lit(ev['estado'])}, "
                  f"{lit(ev['msg']) if ev['msg'] else 'NULL'}, {sql_t(t_sync)});")
        origen = "MANUAL" if rng2.random() < 0.25 else "JOB"
        w(f"    ses({lit(uuid)}, {sql_t(t_sync)}, {len(evs)}, {len(evs) - errores - nuevos}, {errores}, '{origen}');")
        ultimos[uuid] = t_sync

    w("")
    for usr, nombre, uuid, tel, _ in OPERADORES:
        ult = ultimos.get(uuid, ("n", 3600))
        w(f"    l_ts := {sql_t(ult)};")
        w(f"    INSERT INTO dispositivos (uuid, nombre, ultima_sync) VALUES ({lit(uuid)}, {lit(tel)}, l_ts);")
    w("    COMMIT;")
    w("    pkg_batch.conciliar('ACTUAL');")
    w("END;")
    w("/")
    w("")
    # sqlplus corta una sentencia en la primera línea en blanco: dentro del bloque no puede haber ninguna.
    ini = o.index("DECLARE")
    return "\n".join(o[:ini] + [l for l in o[ini:] if l.strip()] + [""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--sql", type=Path, default=ROOT / "db" / "init" / "08_demo.sql")
    args = parser.parse_args()
    args.sql.write_bytes(render(args.seed).encode("utf-8"))


if __name__ == "__main__":
    main()
