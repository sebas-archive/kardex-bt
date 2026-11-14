-- Configuracion general y estado inicial del servicio Bluetooth.
-- La aplicacion puede reaplicar estos valores (migrar() solo crea si faltan); aqui quedan sembrados
-- para que el servicio y el escritorio funcionen en una base nueva.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
ALTER SESSION SET CURRENT_SCHEMA = app;

INSERT INTO configuracion (clave, valor) VALUES ('lote.intervalo_min', '1');
INSERT INTO configuracion (clave, valor) VALUES ('fotos.max_mb', '2');
INSERT INTO configuracion (clave, valor) VALUES ('fotos.dir', '/work/fotos');
-- Programacion del respaldo automatico: la edita la pantalla Respaldos, no Configuracion.
INSERT INTO configuracion (clave, valor) VALUES ('respaldos.auto', 'S');
INSERT INTO configuracion (clave, valor) VALUES ('respaldos.hora', '23:00');
INSERT INTO configuracion (clave, valor) VALUES ('respaldos.conservar', '7');

INSERT INTO servicio_bt (id, estado, pausado, listos) VALUES (1, 'DETENIDO', 'N', 0);

COMMIT;
