# Base de datos

SQLite local por equipo, sin servidor ni puerto. El archivo `eventos.db` lo crea la aplicación en la primera ejecución a partir de `schema.sql`.

| Archivo | Para qué sirve |
|---|---|
| `schema.sql` | Esquema real de SQLite (tablas, restricciones, índices, `PRAGMA` y datos iniciales). Es la fuente de verdad. |
| `estructura-dbdiagramio` | DBML para dibujar el diagrama en [dbdiagram.io](https://dbdiagram.io). Conviene renombrarlo a `estructura.dbml` con `git mv`. |

## Cómo usarla

Cada conexión (servicio e interfaz) debe ejecutar estos `PRAGMA`, porque solo `journal_mode` queda guardado en el archivo:

```python
conexion = sqlite3.connect(ruta_db)
conexion.execute("PRAGMA journal_mode = WAL")
conexion.execute("PRAGMA foreign_keys = ON")
conexion.execute("PRAGMA busy_timeout = 5000")
```

Ruta sugerida en Windows: `C:\ProgramData\CapturadorEventos\eventos.db` (configurable). Los archivos `*.db`, `*.db-wal` y `*.db-shm` no se suben a Git.

## Diccionario de tablas

| Tabla | Para qué sirve | Requisitos |
|---|---|---|
| `equipo` | El computador donde está instalado el sistema. | RF18 |
| `modelo_periferico` | Catálogo de modelos conocidos, identificados por VID y PID. | RF17 |
| `limite_modelo` | Límite de vida útil de cada modelo, uno por tipo de conteo (tecla, clic, scroll). | RF17, RNF9 |
| `periferico` | Cada teclado o mouse físico, con etiqueta de inventario y equipo asignado. | RF18 |
| `sesion` | Periodo desde que el servicio inicia hasta que el equipo se apaga, con segundos de actividad. | RF12 |
| `evento` | Cada evento válido: tipo y hora, y coordenadas en los movimientos del mouse. | RF7, RF8, RNF4 |
| `contador_diario` | Pulsaciones por tecla, clics y scroll acumulados por día y por periférico. | RF16, RNF4 |
| `alerta` | Avisos del 90 % y del 100 %, con su estado de envío y reintentos. | RF19, RF20, RNF12 |
| `incidente` | Errores de comunicación, eventos inválidos, caídas del capturador y apagados inesperados. | RF9, RF10 |
| `configuracion` | Umbrales, destinatarios, servidor SMTP y orden de iniciar o detener la captura. | RNF9, RNF10 |

## Relaciones

- Un `equipo` tiene muchos `periferico` y muchas `sesion`.
- Un `modelo_periferico` tiene muchos `periferico` y varios `limite_modelo` (uno por tipo de conteo).
- Una `sesion` tiene muchos `evento` y muchos `incidente`.
- Un `periferico` genera muchos `evento`, muchos `contador_diario` y hasta dos `alerta` (90 % y 100 %).
- `configuracion` no se relaciona con otras tablas.

## Decisiones de diseño

1. **Privacidad (RNF4).** `evento` no tiene columna con la tecla pulsada. Las teclas solo existen como contadores agregados en `contador_diario`, sin orden ni secuencia.
2. **Sin alertas duplicadas.** El índice único `(id_periferico, umbral)` en `alerta` permite una sola alerta por umbral, aunque el programa se reinicie.
3. **Alertas que sobreviven a fallos (RNF12).** La alerta se guarda como `pendiente` antes de intentar el envío. Si no hay internet, se reintenta al minuto, a los 5 minutos y luego cada 15; lo que quede pendiente se reenvía en la siguiente sesión.
4. **La contraseña no está en la base (RNF10).** Va en el Administrador de credenciales de Windows con `keyring`. `configuracion` solo guarda servidor, puerto y remitente.
5. **Total acumulado sin columna extra.** El desgaste total de una tecla es la suma de sus filas en `contador_diario`; así no hay un total duplicado que pueda desactualizarse. El porcentaje de uso es ese total dividido entre el límite de `limite_modelo`.
6. **Etiqueta nula al inicio.** Dos teclados idénticos comparten VID/PID, así que `periferico.etiqueta` puede estar vacía y la asignación queda `por_confirmar` hasta que Soporte TI la confirme (RF18).
7. **Fechas como texto ISO 8601.** SQLite no tiene tipo fecha. Formato `2026-10-09T08:15:30`; los días del contador usan `2026-10-09`.
8. **Enumeraciones con `CHECK`.** SQLite no tiene `ENUM`; los valores permitidos de `tipo`, `estado`, `tipo_conteo`, etc. se validan con restricciones `CHECK`.

## Datos de ejemplo

`schema.sql` inserta dos modelos Logitech (K120, `046D:C31C`, y B100, `046D:C077`) con límites de ejemplo tomados de los mockups: 20 000 pulsaciones por tecla, 10 000 clics por botón y 15 000 pasos de scroll. **Son valores de ejemplo**: hay que comprobar cada VID/PID en el equipo real y cada límite con la ficha técnica del fabricante.

Para ver el VID/PID de un teclado en Windows: `Get-PnpDevice -Class Keyboard | Select FriendlyName, InstanceId`.
