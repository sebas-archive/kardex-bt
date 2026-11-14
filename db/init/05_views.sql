-- Vistas que consume la aplicacion de escritorio (los agregados se calculan en Oracle).
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

-- Indicadores del conteo continuo. "Contados" = SKU con cantidad contada (no NULL).
-- Sin clasificacion: faltantes/sobrantes son solo indicadores numericos del Dashboard.
CREATE OR REPLACE VIEW v_resumen_conteo AS
SELECT t.id_conteo,
       t.skus_totales,
       t.contados,
       CASE WHEN t.skus_totales = 0 THEN 0 ELSE ROUND(t.contados / t.skus_totales * 100, 2) END AS avance_pct,
       t.ok,
       t.faltantes,
       t.sobrantes,
       CASE WHEN t.contados = 0 THEN 0 ELSE ROUND(t.ok / t.contados * 100, 2) END AS exactitud_pct,
       t.valor_faltante,
       t.valor_sobrante
  FROM (SELECT c.id_conteo,
               COUNT(k.sku)                                                        AS skus_totales,
               COUNT(k.cant_contada)                                               AS contados,
               COUNT(CASE WHEN k.diferencia = 0 AND k.cant_contada IS NOT NULL THEN 1 END) AS ok,
               COUNT(CASE WHEN k.diferencia < 0 THEN 1 END)                        AS faltantes,
               COUNT(CASE WHEN k.diferencia > 0 THEN 1 END)                        AS sobrantes,
               NVL(SUM(CASE WHEN k.diferencia < 0 THEN -k.diferencia * p.costo_unit END), 0) AS valor_faltante,
               NVL(SUM(CASE WHEN k.diferencia > 0 THEN k.diferencia * p.costo_unit END), 0)  AS valor_sobrante
          FROM conteos c
          LEFT JOIN conciliacion k ON k.id_conteo = c.id_conteo
          LEFT JOIN productos p ON p.sku = k.sku
         GROUP BY c.id_conteo) t;

-- Diferencia en unidades y en pesos por categoria (los SKU sin lectura no suman).
CREATE OR REPLACE VIEW v_dif_categoria AS
SELECT k.id_conteo,
       p.categoria,
       NVL(SUM(k.diferencia), 0)                  AS diferencia,
       NVL(SUM(k.diferencia * p.costo_unit), 0)   AS valor_diferencia
  FROM conciliacion k
  JOIN productos p ON p.sku = k.sku
 WHERE k.cant_contada IS NOT NULL
 GROUP BY k.id_conteo, p.categoria;

-- SKU ordenados por el valor absoluto de su diferencia (los no contados, sin valor, al final).
CREATE OR REPLACE VIEW v_top_desvios AS
SELECT k.id_conteo, k.sku, p.nombre, p.categoria,
       k.cant_sistema, k.cant_contada, k.diferencia,
       ROUND(NVL(k.diferencia, 0) * p.costo_unit, 2) AS valor_diferencia
  FROM conciliacion k
  JOIN productos p ON p.sku = k.sku
 ORDER BY k.id_conteo, ABS(NVL(k.diferencia, 0) * p.costo_unit) DESC NULLS LAST, k.sku;

-- Lecturas por operador y hora de captura (cuenta tambien las reemplazadas por un recuento).
CREATE OR REPLACE VIEW v_actividad AS
SELECT r.id_conteo,
       NVL(r.operador, '(sin operador)')            AS operador,
       TRUNC(CAST(r.fecha_captura AS DATE), 'HH24') AS hora,
       COUNT(*)                                     AS registros
  FROM registros_procesados r
 GROUP BY r.id_conteo, NVL(r.operador, '(sin operador)'), TRUNC(CAST(r.fecha_captura AS DATE), 'HH24');

-- Estado del staging y ultima corrida del batch que proceso algo.
CREATE OR REPLACE VIEW v_estado_batch AS
SELECT (SELECT COUNT(*) FROM captura_transito WHERE estado = 'PENDIENTE')  AS pendientes,
       (SELECT COUNT(*) FROM captura_transito WHERE estado = 'PROCESANDO') AS procesando,
       (SELECT COUNT(*) FROM captura_transito WHERE estado = 'PROCESADO')  AS procesados,
       (SELECT COUNT(*) FROM captura_transito WHERE estado = 'ERROR')      AS errores,
       (SELECT MAX(fin) KEEP (DENSE_RANK LAST ORDER BY id) FROM log_batch)  AS ultimo_run,
       (SELECT MAX(origen) KEEP (DENSE_RANK LAST ORDER BY id) FROM log_batch) AS ultimo_origen
  FROM dual;

-- Lecturas rechazadas por el batch, con los campos del REC ya separados y decodificados.
-- La pantalla Sincronizacion la usa para mostrar el motivo y para el alta de SKU desconocido.
CREATE OR REPLACE VIEW v_errores_captura AS
SELECT t.id_transito,
       t.uuid_dispositivo,
       t.seq,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 4, NULL, 1), 'UTF-8') AS id_conteo,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 5, NULL, 1), 'UTF-8') AS sku,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 6, NULL, 1), 'UTF-8') AS cantidad,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 7, NULL, 1), 'UTF-8') AS operador,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 8, NULL, 1), 'UTF-8') AS nota,
       UTL_URL.UNESCAPE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 9, NULL, 1), 'UTF-8') AS danados,
       CASE WHEN REGEXP_LIKE(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 3, NULL, 1), '^[0-9]{1,15}$')
            THEN TIMESTAMP '1970-01-01 00:00:00'
                 + NUMTODSINTERVAL(TO_NUMBER(REGEXP_SUBSTR(t.datos_raw, '([^|]*)(\||$)', 1, 3, NULL, 1)) / 1000, 'SECOND')
       END AS fecha_captura,
       t.mensaje_error,
       t.fecha_recepcion
  FROM captura_transito t
 WHERE t.estado = 'ERROR' AND t.datos_raw LIKE 'REC|%';
