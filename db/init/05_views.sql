-- Vistas que consume la aplicacion de escritorio (los agregados se calculan en Oracle).
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

-- Indicadores por conteo. "Contados" = SKU que ya no estan SIN_CONTAR.
-- Exactitud (IRA) = SKU OK / SKU contados.
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
               COUNT(k.sku)                                                         AS skus_totales,
               COUNT(CASE WHEN k.clasificacion <> 'SIN_CONTAR' THEN 1 END)          AS contados,
               COUNT(CASE WHEN k.clasificacion = 'OK' THEN 1 END)                   AS ok,
               COUNT(CASE WHEN k.clasificacion = 'FALTANTE' THEN 1 END)             AS faltantes,
               COUNT(CASE WHEN k.clasificacion = 'SOBRANTE' THEN 1 END)             AS sobrantes,
               NVL(SUM(CASE WHEN k.clasificacion = 'FALTANTE' THEN k.valor_diferencia END), 0) AS valor_faltante,
               NVL(SUM(CASE WHEN k.clasificacion = 'SOBRANTE' THEN k.valor_diferencia END), 0) AS valor_sobrante
          FROM conteos c
          LEFT JOIN conciliacion k ON k.id_conteo = c.id_conteo
         GROUP BY c.id_conteo) t;

-- Diferencia en unidades y en pesos por categoria (los SIN_CONTAR no suman).
CREATE OR REPLACE VIEW v_dif_categoria AS
SELECT k.id_conteo,
       p.categoria,
       NVL(SUM(k.diferencia), 0)       AS diferencia,
       NVL(SUM(k.valor_diferencia), 0) AS valor_diferencia
  FROM conciliacion k
  JOIN productos p ON p.sku = k.sku
 GROUP BY k.id_conteo, p.categoria;

-- SKU ordenados por el valor absoluto de su diferencia (los SIN_CONTAR, sin valor, al final).
CREATE OR REPLACE VIEW v_top_desvios AS
SELECT k.id_conteo, k.sku, p.nombre, p.categoria, k.diferencia, k.valor_diferencia, k.clasificacion
  FROM conciliacion k
  JOIN productos p ON p.sku = k.sku
 ORDER BY k.id_conteo, ABS(k.valor_diferencia) DESC NULLS LAST, k.sku;


-- Lecturas por operador y hora de captura (cuenta tambien las reemplazadas por un recuento).
CREATE OR REPLACE VIEW v_actividad AS
SELECT r.id_conteo,
       NVL(r.operador, '(sin operador)')           AS operador,
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
       (SELECT MAX(fin) KEEP (DENSE_RANK LAST ORDER BY id) FROM log_batch)    AS ultimo_run,
       (SELECT MAX(origen) KEEP (DENSE_RANK LAST ORDER BY id) FROM log_batch) AS ultimo_origen
  FROM dual;
