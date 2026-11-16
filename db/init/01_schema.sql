-- Esquema de inventario fisico continuo para Oracle XE 11g.
-- El contenedor ejecuta este script como SYS: todo se crea en el esquema APP.
-- 11g no tiene IDENTITY: los IDs numericos usan secuencia + trigger BEFORE INSERT.
-- Textos en caracteres (VARCHAR2(n CHAR)); solo DATOS_RAW se mide en bytes.
WHENEVER SQLERROR EXIT FAILURE ROLLBACK
SET DEFINE OFF
GRANT CREATE SEQUENCE, CREATE TRIGGER, CREATE VIEW, CREATE JOB TO app;
ALTER USER app QUOTA UNLIMITED ON users;
ALTER SESSION SET CURRENT_SCHEMA = app;

-- ---------------------------------------------------------------- catalogos
-- Un unico conteo continuo: ACTUAL. No hay cierre ni estado CERRADO.
CREATE TABLE conteos (
    id_conteo    VARCHAR2(30 CHAR)  NOT NULL,
    nombre       VARCHAR2(100 CHAR) NOT NULL,
    estado       VARCHAR2(10 CHAR)  DEFAULT 'ABIERTO' NOT NULL,
    fecha_inicio TIMESTAMP          DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_conteos PRIMARY KEY (id_conteo),
    CONSTRAINT ck_conteos_estado CHECK (estado = 'ABIERTO')
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

-- Stock del sistema por SKU (una fila por producto y conteo: ACTUAL). El operador nunca lo ve.
CREATE TABLE stock_sistema (
    id_conteo         VARCHAR2(30 CHAR) NOT NULL,
    sku               VARCHAR2(30 CHAR) NOT NULL,
    cantidad_sistema  NUMBER(12, 3)     DEFAULT 0 NOT NULL,
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
    -- Estados de una lectura:
    --   PENDIENTE  -> recien recibida, esperando al batch.
    --   PROCESANDO -> reclamada por una corrida del batch.
    --   PROCESADO  -> validada e insertada en REGISTROS_PROCESADOS.
    --   ERROR      -> no es una lectura valida (formato, cantidad, danados...) o fallo inesperado.
    --   NUEVO_SKU  -> la lectura es valida pero su SKU no esta en PRODUCTOS: NO es un error, espera a
    --                 que el Administrador decida desde el escritorio ("Crear y procesar" o "No crear").
    --   DESCARTADO -> el Administrador decidio no tomar esa lectura (SKU nuevo no creado): no cuenta
    --                 como lectura y la purga la elimina como si estuviera procesada.
    CONSTRAINT ck_transito_estado CHECK (estado IN ('PENDIENTE', 'PROCESANDO', 'PROCESADO', 'ERROR',
                                                    'NUEVO_SKU', 'DESCARTADO'))
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
    sku              VARCHAR2(30 CHAR)  NOT NULL,
    cantidad         NUMBER(12, 3)      NOT NULL,
    operador         VARCHAR2(60 CHAR),
    nota             VARCHAR2(255 CHAR),
    fecha_captura    TIMESTAMP          NOT NULL,
    vigente          CHAR(1)            DEFAULT 'S' NOT NULL,
    fecha_procesado  TIMESTAMP          DEFAULT SYSTIMESTAMP,
    danados          NUMBER(12, 3),
    CONSTRAINT pk_registros_procesados PRIMARY KEY (id_registro),
    CONSTRAINT uq_registros_transito UNIQUE (id_transito),
    CONSTRAINT fk_registros_transito FOREIGN KEY (id_transito)
        REFERENCES captura_transito (id_transito) ON DELETE SET NULL,
    CONSTRAINT fk_registros_conteo FOREIGN KEY (id_conteo) REFERENCES conteos (id_conteo),
    CONSTRAINT fk_registros_producto FOREIGN KEY (sku) REFERENCES productos (sku),
    CONSTRAINT ck_registros_vigente CHECK (vigente IN ('S', 'N'))
);

CREATE INDEX ix_registros_grupo ON registros_procesados (id_conteo, sku);

CREATE OR REPLACE TRIGGER trg_registro_bi
BEFORE INSERT ON registros_procesados
FOR EACH ROW WHEN (NEW.id_registro IS NULL)
BEGIN
    :NEW.id_registro := seq_registro.NEXTVAL;
END;
/

-- Resultado de la conciliacion por SKU. Sin valor_diferencia ni clasificacion.
-- CANT_CONTADA, DIFERENCIA y DIFERENCIA_PCT son NULL cuando el SKU aun no tiene lectura.
CREATE TABLE conciliacion (
    id_conteo         VARCHAR2(30 CHAR) NOT NULL,
    sku               VARCHAR2(30 CHAR) NOT NULL,
    cant_sistema      NUMBER(12, 3)     NOT NULL,
    cant_contada      NUMBER(12, 3),
    diferencia        NUMBER(12, 3),
    diferencia_pct    NUMBER(10, 2),
    fecha_calculo     TIMESTAMP         DEFAULT SYSTIMESTAMP,
    CONSTRAINT pk_conciliacion PRIMARY KEY (id_conteo, sku),
    CONSTRAINT fk_conciliacion_conteo FOREIGN KEY (id_conteo) REFERENCES conteos (id_conteo),
    CONSTRAINT fk_conciliacion_producto FOREIGN KEY (sku) REFERENCES productos (sku)
);

-- ------------------------------------------------------------ bitacoras
CREATE SEQUENCE seq_sync START WITH 1 INCREMENT BY 1;

-- Fotos de evidencia. El archivo vive en la carpeta FOTOS_DIR del PC; aqui, su ruta relativa.
CREATE TABLE fotos (
    uuid_dispositivo  VARCHAR2(50 CHAR)  NOT NULL,
    seq               NUMBER             NOT NULL,
    ruta              VARCHAR2(200 CHAR) NOT NULL,
    bytes             NUMBER             NOT NULL,
    recibida          TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_fotos PRIMARY KEY (uuid_dispositivo, seq)
);

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

-- ------------------------------------------------------- cuentas de la aplicacion
-- Cuentas del PC (ADMIN, INVENTARIO) y de los operadores del movil (OPERADOR, origen MOVIL).
-- Estado: PENDIENTE hasta que el administrador la aprueba (ACTIVO) o la rechaza; SUSPENDIDO con motivo.
-- La clave nunca se guarda en claro (PBKDF2). Las cuentas del movil guardan '-' y no entran al PC.
-- CORREO: obligatorio en cuentas del escritorio, opcional en las del movil. No es unico (el login es USUARIO).
CREATE TABLE usuarios (
    usuario          VARCHAR2(30 CHAR)  NOT NULL,
    nombre           VARCHAR2(60 CHAR)  NOT NULL,
    correo           VARCHAR2(120 CHAR),
    rol              VARCHAR2(12 CHAR),
    clave_hash       VARCHAR2(200 CHAR) NOT NULL,
    clave_pendiente  VARCHAR2(200 CHAR),
    clave_motivo     VARCHAR2(300 CHAR),   -- motivo del rechazo de una solicitud de contraseña
    estado           VARCHAR2(10 CHAR)  DEFAULT 'PENDIENTE' NOT NULL,
    motivo           VARCHAR2(300 CHAR),
    resuelto_por     VARCHAR2(30 CHAR),
    resuelto         TIMESTAMP,
    origen           VARCHAR2(10 CHAR)  DEFAULT 'ESCRITORIO' NOT NULL,
    uuid_dispositivo VARCHAR2(50 CHAR),
    intentos         NUMBER             DEFAULT 0 NOT NULL,
    bloqueado_hasta  TIMESTAMP,
    creado           TIMESTAMP          DEFAULT SYSTIMESTAMP,
    pregunta         VARCHAR2(200 CHAR),
    respuesta_hash   VARCHAR2(200 CHAR),
    foto             VARCHAR2(200 CHAR),
    tema             VARCHAR2(10 CHAR)  DEFAULT 'sistema' NOT NULL,
    idioma           VARCHAR2(2 CHAR)   DEFAULT 'es' NOT NULL,
    CONSTRAINT pk_usuarios PRIMARY KEY (usuario),
    CONSTRAINT ck_usuarios_rol CHECK (rol IS NULL OR rol IN ('ADMIN', 'INVENTARIO', 'OPERADOR')),
    CONSTRAINT ck_usuarios_estado CHECK (estado IN ('PENDIENTE', 'ACTIVO', 'RECHAZADO', 'SUSPENDIDO')),
    CONSTRAINT ck_usuarios_origen CHECK (origen IN ('ESCRITORIO', 'MOVIL')),
    CONSTRAINT ck_usuarios_correo CHECK (origen = 'MOVIL' OR correo IS NOT NULL),
    CONSTRAINT ck_usuarios_tema CHECK (tema IN ('claro', 'sistema', 'oscuro')),
    CONSTRAINT ck_usuarios_idioma CHECK (idioma IN ('es', 'en'))
);

-- Matriz de permisos: nivel de cada rol en cada modulo (NINGUNO, CONSULTA, GESTION).
-- Los valores iniciales los siembra 06_permisos.sql; el escritorio puede completarlos si faltan.
CREATE TABLE permisos (
    rol     VARCHAR2(12 CHAR) NOT NULL,
    modulo  VARCHAR2(30 CHAR) NOT NULL,
    nivel   VARCHAR2(10 CHAR) NOT NULL,
    CONSTRAINT pk_permisos PRIMARY KEY (rol, modulo),
    CONSTRAINT ck_permisos_nivel CHECK (nivel IN ('NINGUNO', 'CONSULTA', 'GESTION'))
);

-- Configuracion general. La pantalla Configuracion edita lote.intervalo_min y fotos.max_mb;
-- fotos.dir es informativa (el servicio usa FOTOS_DIR). Las claves respaldos.* son de la pantalla Respaldos.
CREATE TABLE configuracion (
    clave       VARCHAR2(40 CHAR)  NOT NULL,
    valor       VARCHAR2(200 CHAR) NOT NULL,
    modificado  TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_configuracion PRIMARY KEY (clave)
);

-- Estado que el servicio Bluetooth publica para el escritorio (una sola fila, ID = 1).
CREATE TABLE servicio_bt (
    id            NUMBER             NOT NULL,
    estado        VARCHAR2(30 CHAR)  NOT NULL,
    codigo        VARCHAR2(10 CHAR),
    recibidos     NUMBER             DEFAULT 0 NOT NULL,
    ultimo_error  VARCHAR2(400 CHAR),
    desde         TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
    latido        TIMESTAMP          DEFAULT SYSTIMESTAMP NOT NULL,
    pausado       CHAR(1)            DEFAULT 'N' NOT NULL,
    respuesta     CHAR(1),
    listos        NUMBER             DEFAULT 0 NOT NULL,
    CONSTRAINT pk_servicio_bt PRIMARY KEY (id)
);
