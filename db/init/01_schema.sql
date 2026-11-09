-- Esquema de inventario fisico para Oracle XE 11g.
-- El contenedor ejecuta este script como SYS: todo se crea en el esquema APP.
-- 11g no tiene IDENTITY: los IDs numericos usan secuencia + trigger BEFORE INSERT.
-- Textos en caracteres (VARCHAR2(n CHAR)); solo DATOS_RAW se mide en bytes.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
GRANT CREATE SEQUENCE, CREATE TRIGGER, CREATE VIEW, CREATE JOB TO app;
ALTER USER app QUOTA UNLIMITED ON users;
ALTER SESSION SET CURRENT_SCHEMA = app;

-- ---------------------------------------------------------------- catalogos
CREATE TABLE conteos (
    id_conteo    VARCHAR2(30 CHAR)  NOT NULL,
    nombre       VARCHAR2(100 CHAR) NOT NULL,
    estado       VARCHAR2(10 CHAR)  DEFAULT 'ABIERTO' NOT NULL,
    fecha_inicio TIMESTAMP          DEFAULT SYSTIMESTAMP,
    fecha_cierre TIMESTAMP,
    CONSTRAINT pk_conteos PRIMARY KEY (id_conteo),
    CONSTRAINT ck_conteos_estado CHECK (estado IN ('ABIERTO', 'CERRADO'))
);

CREATE TABLE productos (
    sku             VARCHAR2(30 CHAR)  NOT NULL,
    nombre          VARCHAR2(120 CHAR) NOT NULL,
    categoria       VARCHAR2(40 CHAR)  NOT NULL,
    unidad          VARCHAR2(10 CHAR)  NOT NULL,
    costo_unit      NUMBER(12, 2)      NOT NULL,
    tolerancia_pct  NUMBER(5, 2)       DEFAULT 0 NOT NULL,
    CONSTRAINT pk_productos PRIMARY KEY (sku)
);

CREATE TABLE ubicaciones (
    cod_ubicacion VARCHAR2(20 CHAR)  NOT NULL,
    zona          VARCHAR2(10 CHAR)  NOT NULL,
    descripcion   VARCHAR2(100 CHAR),
    CONSTRAINT pk_ubicaciones PRIMARY KEY (cod_ubicacion)
);

-- Foto del stock teorico al abrir el conteo.
CREATE TABLE stock_sistema (
    id_conteo         VARCHAR2(30 CHAR) NOT NULL,
    sku               VARCHAR2(30 CHAR) NOT NULL,
    cantidad_sistema  NUMBER(12, 3)     NOT NULL,
    CONSTRAINT pk_stock_sistema PRIMARY KEY (id_conteo, sku),
    CONSTRAINT fk_stock_conteo FOREIGN KEY (id_conteo) REFERENCES conteos (id_conteo),
    CONSTRAINT fk_stock_producto FOREIGN KEY (sku) REFERENCES productos (sku)
);

CREATE TABLE dispositivos (
    uuid        VARCHAR2(50 CHAR) NOT NULL,
    nombre      VARCHAR2(60 CHAR),
    ultima_sync TIMESTAMP,
    CONSTRAINT pk_dispositivos PRIMARY KEY (uuid)
);

-- ------------------------------------------------------------------ staging
CREATE SEQUENCE seq_transito START WITH 1 INCREMENT BY 1;

CREATE TABLE captura_transito (
    id_transito       NUMBER             NOT NULL,
    uuid_dispositivo  VARCHAR2(50 CHAR)  NOT NULL,
    seq               NUMBER             NOT NULL,
    datos_raw         VARCHAR2(4000 BYTE) NOT NULL,
    estado            VARCHAR2(12 CHAR)  DEFAULT 'PENDIENTE' NOT NULL,
    mensaje_error     VARCHAR2(400 CHAR),
    fecha_recepcion   TIMESTAMP          DEFAULT SYSTIMESTAMP,
    fecha_reclamo     TIMESTAMP,
    CONSTRAINT pk_captura_transito PRIMARY KEY (id_transito),
    CONSTRAINT uq_transito_dispositivo_seq UNIQUE (uuid_dispositivo, seq),
    CONSTRAINT ck_transito_estado CHECK (estado IN ('PENDIENTE', 'PROCESANDO', 'PROCESADO', 'ERROR'))
);

CREATE INDEX ix_transito_estado ON captura_transito (estado);

CREATE OR REPLACE TRIGGER trg_transito_bi
BEFORE INSERT ON captura_transito
FOR EACH ROW WHEN (NEW.id_transito IS NULL)
BEGIN
    :NEW.id_transito := seq_transito.NEXTVAL;
END;
/

-- --------------------------------------------------------------- definitivo
CREATE SEQUENCE seq_registro START WITH 1 INCREMENT BY 1;

-- ID_TRANSITO es UNIQUE (una fila de staging no puede procesarse dos veces) y
-- ON DELETE SET NULL: la purga del transito no debe bloquearse por las lecturas ya procesadas.
CREATE TABLE registros_procesados (
    id_registro      NUMBER             NOT NULL,
    id_transito      NUMBER,
    id_conteo        VARCHAR2(30 CHAR)  NOT NULL,
    cod_ubicacion    VARCHAR2(20 CHAR)  NOT NULL,
    sku              VARCHAR2(30 CHAR)  NOT NULL,
    cantidad         NUMBER(12, 3)      NOT NULL,
    operador         VARCHAR2(60 CHAR),
    nota             VARCHAR2(255 CHAR),
    fecha_captura    TIMESTAMP          NOT NULL,
    vigente          CHAR(1)            DEFAULT 'S' NOT NULL,
    fecha_procesado  TIMESTAMP          DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_registros_procesados PRIMARY KEY (id_registro),
    CONSTRAINT uq_registros_transito UNIQUE (id_transito),
    CONSTRAINT fk_registros_transito FOREIGN KEY (id_transito)
        REFERENCES captura_transito (id_transito) ON DELETE SET NULL,
    CONSTRAINT fk_registros_conteo FOREIGN KEY (id_conteo) REFERENCES conteos (id_conteo),
    CONSTRAINT fk_registros_ubicacion FOREIGN KEY (cod_ubicacion) REFERENCES ubicaciones (cod_ubicacion),
    CONSTRAINT fk_registros_producto FOREIGN KEY (sku) REFERENCES productos (sku),
    CONSTRAINT ck_registros_vigente CHECK (vigente IN ('S', 'N'))
);

CREATE INDEX ix_registros_grupo ON registros_procesados (id_conteo, cod_ubicacion, sku);

CREATE OR REPLACE TRIGGER trg_registro_bi
BEFORE INSERT ON registros_procesados
FOR EACH ROW WHEN (NEW.id_registro IS NULL)
BEGIN
    :NEW.id_registro := seq_registro.NEXTVAL;
END;
/

CREATE TABLE conciliacion (
    id_conteo         VARCHAR2(30 CHAR) NOT NULL,
    sku               VARCHAR2(30 CHAR) NOT NULL,
    cant_sistema      NUMBER(12, 3),
    cant_contada      NUMBER(12, 3),
    diferencia        NUMBER(12, 3),
    diferencia_pct    NUMBER(10, 2),
    valor_diferencia  NUMBER(14, 2),
    clasificacion     VARCHAR2(12 CHAR) NOT NULL,
    fecha_calculo     TIMESTAMP         DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_conciliacion PRIMARY KEY (id_conteo, sku),
    CONSTRAINT fk_conciliacion_conteo FOREIGN KEY (id_conteo) REFERENCES conteos (id_conteo),
    CONSTRAINT fk_conciliacion_producto FOREIGN KEY (sku) REFERENCES productos (sku),
    CONSTRAINT ck_conciliacion_clase CHECK (clasificacion IN ('OK', 'FALTANTE', 'SOBRANTE', 'SIN_CONTAR'))
);

-- ------------------------------------------------------------ bitacoras
CREATE SEQUENCE seq_sync START WITH 1 INCREMENT BY 1;

CREATE TABLE sync_sesiones (
    id                NUMBER            NOT NULL,
    uuid_dispositivo  VARCHAR2(50 CHAR) NOT NULL,
    inicio            TIMESTAMP         DEFAULT SYSTIMESTAMP,
    fin               TIMESTAMP,
    recibidos         NUMBER            DEFAULT 0 NOT NULL,
    aceptados         NUMBER            DEFAULT 0 NOT NULL,
    CONSTRAINT pk_sync_sesiones PRIMARY KEY (id)
);

CREATE OR REPLACE TRIGGER trg_sync_bi
BEFORE INSERT ON sync_sesiones
FOR EACH ROW WHEN (NEW.id IS NULL)
BEGIN
    :NEW.id := seq_sync.NEXTVAL;
END;
/

CREATE SEQUENCE seq_log_batch START WITH 1 INCREMENT BY 1;

CREATE TABLE log_batch (
    id          NUMBER            NOT NULL,
    inicio      TIMESTAMP         DEFAULT SYSTIMESTAMP,
    fin         TIMESTAMP,
    procesados  NUMBER            DEFAULT 0 NOT NULL,
    errores     NUMBER            DEFAULT 0 NOT NULL,
    origen      VARCHAR2(20 CHAR),
    CONSTRAINT pk_log_batch PRIMARY KEY (id)
);

CREATE OR REPLACE TRIGGER trg_log_batch_bi
BEFORE INSERT ON log_batch
FOR EACH ROW WHEN (NEW.id IS NULL)
BEGIN
    :NEW.id := seq_log_batch.NEXTVAL;
END;
/
