-- Escenario fijo de conciliación (conteo T-01). Lo cargan las pruebas; NO es la semilla.
-- Secciones: @cleanup (borra todo lo del escenario), @setup (catálogo y stock),
-- @lecturas (las 5 lecturas, como filas de staging pendientes). Sin ';' dentro de literales.

-- @cleanup
DELETE FROM registros_procesados
 WHERE id_conteo IN ('T-01', 'T-99') OR sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9') OR cod_ubicacion IN ('U1', 'U2', 'U3');
DELETE FROM conciliacion WHERE id_conteo = 'T-01' OR sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM captura_transito WHERE uuid_dispositivo LIKE 'tst-%';
DELETE FROM sync_sesiones WHERE uuid_dispositivo LIKE 'tst-%';
DELETE FROM stock_sistema WHERE id_conteo = 'T-01';
DELETE FROM conteos WHERE id_conteo = 'T-01';
DELETE FROM productos WHERE sku IN ('A1', 'A2', 'A3', 'A4', 'A5', 'ZZ9');
DELETE FROM ubicaciones WHERE cod_ubicacion IN ('U1', 'U2', 'U3');
DELETE FROM dispositivos WHERE uuid LIKE 'tst-%';

-- @setup
INSERT INTO conteos (id_conteo, nombre, estado) VALUES ('T-01', 'Conteo de prueba', 'ABIERTO');
INSERT INTO ubicaciones (cod_ubicacion, zona, descripcion) VALUES ('U1', 'Z1', 'Estante de prueba 1');
INSERT INTO ubicaciones (cod_ubicacion, zona, descripcion) VALUES ('U2', 'Z1', 'Estante de prueba 2');
INSERT INTO ubicaciones (cod_ubicacion, zona, descripcion) VALUES ('U3', 'Z2', 'Estante de prueba 3');
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A1', 'Producto A1', 'Abarrotes', 'UND', 2000, 2);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A2', 'Producto A2', 'Abarrotes', 'UND', 1000, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A3', 'Producto A3', 'Aseo', 'UND', 3000, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A4', 'Producto A4', 'Aseo', 'UND', 500, 0);
INSERT INTO productos (sku, nombre, categoria, unidad, costo_unit, tolerancia_pct) VALUES ('A5', 'Producto A5', 'Lácteos', 'UND', 700, 0);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('T-01', 'A1', 100);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('T-01', 'A2', 50);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('T-01', 'A3', 20);
INSERT INTO stock_sistema (id_conteo, sku, cantidad_sistema) VALUES ('T-01', 'A4', 10);

-- @lecturas
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 1, 'REC|1|1731170400000|T-01|U1|A1|60|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 2, 'REC|2|1731170401000|T-01|U2|A1|41|Luis|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 3, 'REC|3|1731170402000|T-01|U1|A2|45|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 4, 'REC|4|1731170403000|T-01|U1|A3|23|Ana|');
INSERT INTO captura_transito (uuid_dispositivo, seq, datos_raw) VALUES ('tst-escenario', 5, 'REC|5|1731170404000|T-01|U2|A5|4|Luis|');
