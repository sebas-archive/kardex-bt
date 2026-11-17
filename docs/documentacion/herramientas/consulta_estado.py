"""Consulta de solo lectura del estado de Oracle tras una sincronización (para la evidencia de comunicación)."""
import os
import sys

import oracledb

oracledb.init_oracle_client()
conn = oracledb.connect(user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"], dsn=os.environ["DB_DSN"])
cur = conn.cursor()


def mostrar(titulo: str, sql: str) -> None:
    cur.execute(sql)
    filas = cur.fetchall()
    cols = [d[0] for d in cur.description]
    print(f"-- {titulo}")
    print(" | ".join(cols))
    for f in filas:
        print(" | ".join("" if v is None else str(v) for v in f))
    print()


mostrar("Filas recibidas por dispositivo (CAPTURA_TRANSITO)",
        "SELECT uuid_dispositivo, COUNT(*) AS filas, MIN(seq) AS seq_min, MAX(seq) AS seq_max FROM captura_transito GROUP BY uuid_dispositivo ORDER BY 1")
mostrar("Cuentas del teléfono", "SELECT usuario, estado, rol, origen FROM usuarios WHERE origen = 'MOVIL' ORDER BY usuario")
mostrar("CAPTURA_TRANSITO por estado (staging)",
        "SELECT estado, COUNT(*) AS filas, MIN(seq) AS seq_min, MAX(seq) AS seq_max FROM captura_transito GROUP BY estado ORDER BY estado")
mostrar("Filas duplicadas por (uuid, seq)",
        "SELECT COUNT(*) AS duplicadas FROM (SELECT uuid_dispositivo, seq FROM captura_transito GROUP BY uuid_dispositivo, seq HAVING COUNT(*) > 1)")
mostrar("REGISTROS_PROCESADOS", "SELECT COUNT(*) AS total, SUM(CASE WHEN vigente = 'S' THEN 1 ELSE 0 END) AS vigentes FROM registros_procesados")
mostrar("Últimas corridas del batch",
        "SELECT * FROM (SELECT origen, procesados, errores, TO_CHAR(fin, 'HH24:MI:SS') AS fin FROM log_batch ORDER BY id DESC) WHERE ROWNUM <= 3")
mostrar("CONCILIACION (muestra)",
        "SELECT * FROM (SELECT sku, cant_sistema, cant_contada, diferencia FROM conciliacion WHERE cant_contada IS NOT NULL ORDER BY sku) WHERE ROWNUM <= 5")
mostrar("Errores", "SELECT mensaje_error, COUNT(*) AS filas FROM captura_transito WHERE estado = 'ERROR' GROUP BY mensaje_error")
sys.stdout.flush()
