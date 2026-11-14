-- Escenario fijo de conciliación del conteo continuo ACTUAL. Lo cargan las pruebas; NO es la semilla.
-- Secciones: @cleanup (borra todo lo del escenario), @setup (catálogo y stock), @lecturas (las 5 lecturas,
-- como filas de staging pendientes; la 2 es un recuento de A1: reemplaza a la 1). Sin ';' dentro de literales.

-- @cleanup
DELETE FROM registros_procesados WHERE sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM conciliacion WHERE sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM captura_transito WHERE uuid_dispositivo LIKE 'tst-%';
DELETE FROM sync_sesiones WHERE uuid_dispositivo LIKE 'tst-%';
DELETE FROM fotos WHERE uuid_dispositivo LIKE 'tst-%';
DELETE FROM stock_sistema WHERE sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM productos WHERE sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM dispositivos WHERE uuid LIKE 'tst-%';

-- @setup
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A1', 'Producto A1', 'Abarrotes', 'UND', 2000, 2);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A2', 'Producto A2', 'Abarrotes', 'UND', 1000, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A3', 'Producto A3', 'Aseo', 'UND', 3000, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A4', 'Producto A4', 'Aseo', 'UND', 500, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A5', 'Producto A5', 'Lácteos', 'UND', 700, 0);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', 'A1', 100);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', 'A2', 50);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', 'A3', 20);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', 'A4', 10);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('ACTUAL', 'A5', 0);

-- @lecturas
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 1, 'REC|1|1731170400000|ACTUAL|A1|60|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 2, 'REC|2|1731170401000|ACTUAL|A1|101|Luis|recuento');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 3, 'REC|3|1731170402000|ACTUAL|A2|45|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 4, 'REC|4|1731170403000|ACTUAL|A3|23|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 5, 'REC|5|1731170404000|ACTUAL|A5|4|Luis|');
