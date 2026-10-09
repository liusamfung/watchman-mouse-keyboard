-- ============================================================================
-- Esquema de SQLite: Capturador y Auditor de Eventos (Caso 4)
-- Fuente de verdad de las tablas. El DBML (estructura-dbdiagramio) es solo
-- para dibujar el diagrama en dbdiagram.io; si cambias una tabla aquí,
-- actualiza también el DBML y el diccionario (README.md de esta carpeta).
--
-- Reglas:
--   * Las fechas se guardan como texto ISO 8601, por ejemplo 2026-10-09T08:15:30
--   * Nunca se guarda qué tecla se pulsó en la tabla evento (RNF4)
--   * Nunca se guarda la contraseña del correo en este esquema (RNF10)
-- ============================================================================

-- Estos PRAGMA deben ejecutarse en CADA conexión (el servicio y la interfaz).
-- journal_mode = WAL se queda guardado en el archivo; los demás no.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

-- ---------- Inventario ----------

CREATE TABLE IF NOT EXISTS equipo (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL UNIQUE            -- por ejemplo PC-CONTAB-014
);

-- Catálogo de modelos conocidos (RF17)
CREATE TABLE IF NOT EXISTS modelo_periferico (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fabricante  TEXT NOT NULL,
    nombre      TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('teclado', 'mouse')),
    vid         TEXT NOT NULL,              -- hexadecimal, por ejemplo 046D
    pid         TEXT NOT NULL,              -- hexadecimal, por ejemplo C31C
    UNIQUE (vid, pid)
);

-- Límite de vida útil por modelo y tipo de conteo (RF17, RNF9)
CREATE TABLE IF NOT EXISTS limite_modelo (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    id_modelo    INTEGER NOT NULL REFERENCES modelo_periferico (id),
    tipo_conteo  TEXT NOT NULL CHECK (tipo_conteo IN ('pulsacion_tecla', 'clic_boton', 'scroll_paso')),
    limite       INTEGER NOT NULL CHECK (limite > 0),
    UNIQUE (id_modelo, tipo_conteo)
);

-- Cada teclado o mouse físico asociado a un equipo (RF18)
CREATE TABLE IF NOT EXISTS periferico (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    id_modelo          INTEGER NOT NULL REFERENCES modelo_periferico (id),
    id_equipo          INTEGER NOT NULL REFERENCES equipo (id),
    etiqueta           TEXT UNIQUE,         -- por ejemplo TEC-0042; NULL hasta que soporte la confirme
    estado_asignacion  TEXT NOT NULL DEFAULT 'confirmada' CHECK (estado_asignacion IN ('confirmada', 'por_confirmar')),
    activo             INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    fecha_asignacion   TEXT NOT NULL,
    fecha_retiro       TEXT                 -- NULL mientras esté en uso
);

-- ---------- Registro de uso ----------

-- Una sesión va desde que el servicio inicia hasta que el equipo se apaga (RF12)
CREATE TABLE IF NOT EXISTS sesion (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_equipo              INTEGER NOT NULL REFERENCES equipo (id),
    inicio                 TEXT NOT NULL,
    fin                    TEXT,            -- NULL mientras la sesión está en curso
    tipo_cierre            TEXT CHECK (tipo_cierre IN ('normal', 'inesperado')),
    seg_actividad_teclado  INTEGER NOT NULL DEFAULT 0,
    seg_actividad_mouse    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sesion_inicio ON sesion (inicio);

-- No guarda qué tecla se pulsó, solo el tipo de evento y la hora (RNF4)
CREATE TABLE IF NOT EXISTS evento (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sesion      INTEGER NOT NULL REFERENCES sesion (id),
    id_periferico  INTEGER NOT NULL REFERENCES periferico (id),
    tipo_evento    TEXT NOT NULL CHECK (tipo_evento IN
                   ('tecla_presionada', 'tecla_liberada', 'mouse_movimiento',
                    'clic_izquierdo', 'clic_derecho', 'scroll')),
    fecha_hora     TEXT NOT NULL,
    x              INTEGER,                 -- solo en mouse_movimiento (RF7)
    y              INTEGER
);
CREATE INDEX IF NOT EXISTS idx_evento_sesion      ON evento (id_sesion);
CREATE INDEX IF NOT EXISTS idx_evento_perif_fecha ON evento (id_periferico, fecha_hora);
CREATE INDEX IF NOT EXISTS idx_evento_fecha       ON evento (fecha_hora);

-- Errores, eventos inválidos, caídas del capturador y apagados inesperados (RF9, RF10)
CREATE TABLE IF NOT EXISTS incidente (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    id_sesion   INTEGER REFERENCES sesion (id),
    tipo        TEXT NOT NULL CHECK (tipo IN
                ('error_comunicacion', 'evento_invalido', 'caida_proceso',
                 'apagado_inesperado', 'error_envio')),
    fecha_hora  TEXT NOT NULL,
    detalle     TEXT,
    accion      TEXT                        -- por ejemplo: relanzado automáticamente
);
CREATE INDEX IF NOT EXISTS idx_incidente_fecha ON incidente (fecha_hora);

-- ---------- Desgaste y alertas ----------

-- Solo contadores agregados por día, sin orden ni secuencia (RF16, RNF4).
-- El total acumulado de un elemento es la suma de sus días.
CREATE TABLE IF NOT EXISTS contador_diario (
    id_periferico  INTEGER NOT NULL REFERENCES periferico (id),
    fecha          TEXT NOT NULL,           -- AAAA-MM-DD
    tipo_conteo    TEXT NOT NULL CHECK (tipo_conteo IN ('pulsacion_tecla', 'clic_boton', 'scroll_paso')),
    elemento       TEXT NOT NULL,           -- tecla, botón (izquierdo, derecho) o rueda
    cantidad       INTEGER NOT NULL DEFAULT 0 CHECK (cantidad >= 0),
    PRIMARY KEY (id_periferico, fecha, tipo_conteo, elemento)
) WITHOUT ROWID;

-- Una alerta por periférico y umbral: no se duplican aunque el programa se reinicie (RF19, RF20, RNF12)
CREATE TABLE IF NOT EXISTS alerta (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_periferico         INTEGER NOT NULL REFERENCES periferico (id),
    umbral                INTEGER NOT NULL CHECK (umbral IN (90, 100)),
    estado                TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'enviada')),
    detalle               TEXT,             -- por ejemplo: E 91 %
    fecha_creacion        TEXT NOT NULL,
    intentos              INTEGER NOT NULL DEFAULT 0,
    fecha_ultimo_intento  TEXT,
    proximo_reintento     TEXT,
    ultimo_error          TEXT,
    fecha_envio           TEXT,             -- NULL mientras esté pendiente
    UNIQUE (id_periferico, umbral)
);
CREATE INDEX IF NOT EXISTS idx_alerta_estado ON alerta (estado);

-- ---------- Configuración ----------

-- Pares clave y valor (RNF9). NUNCA guarda la contraseña (RNF10): esa va en keyring.
CREATE TABLE IF NOT EXISTS configuracion (
    clave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);

-- ============================================================================
-- Datos iniciales
-- ============================================================================

-- Configuración por defecto. Los destinatarios se completan desde la pantalla P08.
INSERT OR IGNORE INTO configuracion (clave, valor) VALUES
    ('umbral_aviso',        '90'),
    ('umbral_critico',      '100'),
    ('destinatarios',       ''),
    ('smtp_servidor',       'smtp.gmail.com'),
    ('smtp_puerto',         '587'),
    ('smtp_remitente',      ''),
    ('orden_captura',       'iniciar'),      -- 'iniciar' o 'detener'; la escribe la interfaz y la lee el servicio
    ('carpeta_reportes',    '');

-- Modelos y límites de EJEMPLO tomados de los mockups.
-- Verifica cada VID/PID en el equipo real (PowerShell: Get-PnpDevice -Class Keyboard)
-- y cada límite con la ficha técnica del fabricante antes de usarlos en producción.
INSERT OR IGNORE INTO modelo_periferico (fabricante, nombre, tipo, vid, pid) VALUES
    ('Logitech', 'K120', 'teclado', '046D', 'C31C'),
    ('Logitech', 'B100', 'mouse',   '046D', 'C077');

INSERT OR IGNORE INTO limite_modelo (id_modelo, tipo_conteo, limite)
SELECT id, 'pulsacion_tecla', 20000 FROM modelo_periferico WHERE vid = '046D' AND pid = 'C31C';
INSERT OR IGNORE INTO limite_modelo (id_modelo, tipo_conteo, limite)
SELECT id, 'clic_boton', 10000 FROM modelo_periferico WHERE vid = '046D' AND pid = 'C077';
INSERT OR IGNORE INTO limite_modelo (id_modelo, tipo_conteo, limite)
SELECT id, 'scroll_paso', 15000 FROM modelo_periferico WHERE vid = '046D' AND pid = 'C077';
