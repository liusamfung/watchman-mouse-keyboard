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

En el código no hace falta escribir esto a mano: `comun/repositorio.py` (clase `Repositorio`) ejecuta los `PRAGMA` en cada conexión, crea `eventos.db` a partir de `schema.sql` la primera vez y es el único módulo que accede a la base (decisión de arquitectura 4). El servicio y la interfaz crean cada uno su propio `Repositorio` sobre el mismo archivo.

Ruta sugerida en Windows: `C:\ProgramData\CapturadorEventos\eventos.db` (configurable con la variable de entorno `CAPTURADOR_RUTA_DB` o pasando la ruta al crear el `Repositorio`). Los archivos `*.db`, `*.db-wal` y `*.db-shm` no se suben a Git.

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

## Llaves foráneas

Cada fila es un campo que apunta a otra tabla. Es la misma lista que los comentarios `-- FK →` de `schema.sql` y los `Ref` del DBML (`estructura-dbdiagramio`): si cambias una, cambia las tres.

| Campo | FK → | Obligatoria | Para qué sirve |
|---|---|---|---|
| `limite_modelo.id_modelo` | `modelo_periferico.id` | Sí | El modelo al que se le fija este límite |
| `periferico.id_modelo` | `modelo_periferico.id` | Sí | Qué modelo es (se reconoce por VID/PID) |
| `periferico.id_equipo` | `equipo.id` | Sí | En qué PC está conectado |
| `sesion.id_equipo` | `equipo.id` | Sí | PC donde corrió el servicio |
| `evento.id_sesion` | `sesion.id` | Sí | Sesión en la que ocurrió el evento |
| `evento.id_periferico` | `periferico.id` | Sí | Dispositivo que generó el evento |
| `incidente.id_sesion` | `sesion.id` | No, puede ser NULL | Sesión en la que ocurrió el incidente |
| `contador_diario.id_periferico` | `periferico.id` | Sí (además es parte de la clave primaria) | Periférico al que pertenece el conteo |
| `alerta.id_periferico` | `periferico.id` | Sí | Periférico que llegó al umbral |

Ninguna llave foránea define `ON DELETE`: SQLite usa su comportamiento por defecto (`NO ACTION`) y rechaza borrar una fila que otra todavía referencia. El proyecto no borra filas; el esquema prevé marcar con `activo = 0` los periféricos retirados.

## Qué ofrece el repositorio (`comun/repositorio.py`)

Las pantallas, los reportes y el análisis no escriben SQL: piden lo que necesitan a la clase `Repositorio`. Los rangos de fechas son semiabiertos (`desde` entra, `hasta` no), con formato `AAAA-MM-DD` o fecha y hora ISO 8601, y `None` significa "sin límite". Una fecha que no es ISO 8601 lanza `ValueError`. Ninguna lectura de eventos devuelve la tecla (RNF4): los nombres de teclas solo salen como totales por día.

| Método | Devuelve | Lo usa |
|---|---|---|
| `listar_perifericos(id_equipo=None, incluir_retirados=True)` | `list[ResumenPeriferico]` con modelo, etiqueta, estado, uso y porcentaje frente al límite | P01, P02 |
| `obtener_periferico(id)` | un `ResumenPeriferico` o `None` | P03 |
| `totales_por_elemento(id_periferico, tipo_conteo)` | `dict` con el total de cada tecla, botón o rueda | P03 (teclas con mayor desgaste) |
| `limites_del_periferico(id)` | `dict` de tipo de conteo a límite | evaluador |
| `listar_sesiones(id_equipo=None, dia=None)` | `list[FilaSesion]`, de la más reciente a la más antigua | P04 |
| `actividad_del_dia(dia, id_equipo=None)` | `(segundos de teclado, segundos de mouse)`: suma de las sesiones que empezaron ese día | P04 |
| `incidentes_recientes(limite=50)` | `list[FilaIncidente]` | P01, P07 |
| `listar_alertas(estado=None)` | `list[FilaAlerta]`, de la más reciente a la más antigua | P01, P07 |
| `alertas_pendientes()` | `list[FilaAlerta]` sin enviar, de la más antigua a la más reciente | notificador |
| `crear_alerta(id_periferico, umbral, fecha_creacion, detalle=None)` | `True` si la creó, `False` si ya existía (una sola por periférico y umbral) | evaluador |
| `registrar_intento_de_alerta(id_alerta, fecha_intento, proximo_reintento, error)` | nada; lanza `LookupError` si la alerta no está pendiente | notificador |
| `marcar_alerta_enviada(id_alerta, fecha_envio)` | nada; lanza `LookupError` si la alerta no está pendiente | notificador |
| `horas_de_eventos(desde, hasta, tipo_dispositivo=None, incluir_liberaciones=False)` | `list[str]` con la fecha y hora de cada evento | análisis (mapa de calor y patrones) |
| `filas_de_eventos(desde, hasta)` | filas: id, sesión, periférico, tipo de evento, fecha y hora, x, y | reporte de eventos |
| `filas_de_totales_diarios(desde, hasta)` | filas: fecha, periférico, tipo de conteo, total | reporte de totales diarios |
| `filas_de_contadores(desde, hasta)` | filas: fecha, periférico, tipo de conteo, elemento, cantidad | reporte de contadores |
| `filas_de_alertas(desde, hasta)` | filas: periférico, umbral, estado, intentos, fecha de creación, fecha de envío (el rango aplica a la creación) | reporte de alertas |

**El límite es por elemento** (20 000 pulsaciones por tecla, 10 000 clics por botón, 15 000 pasos de la rueda). Por eso el porcentaje de `UsoDeConteo` y de `ResumenPeriferico.porcentaje_maximo` sale del elemento más gastado (`mayor_uso`) y no de la suma de todos (`total`): una tecla a punto de agotarse debe verse aunque el teclado entero tenga muchas pulsaciones repartidas.

En las filas de los reportes, la columna "periférico" es la etiqueta de inventario o, si todavía no la tiene, `ID n`. Las horas de eventos dejan fuera las teclas liberadas por defecto: cada pulsación genera dos eventos (presionada y liberada) y contarlos doble haría pesar más al teclado que al mouse.

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

## Base de ejemplo para desarrollar

Para programar las pantallas, los reportes o el análisis no hace falta Windows ni un teclado real: este comando crea una base con varias semanas de uso inventado.

```bash
python -m pruebas.base_de_ejemplo ruta/ejemplo.db
```

Luego se abre con `Repositorio("ruta/ejemplo.db")`, o con la variable de entorno `CAPTURADOR_RUTA_DB=ruta/ejemplo.db` para que la interfaz la use. Trae un teclado K120 retirado (`TEC-0007`, al 100 %), un teclado K120 por confirmar al 92 % con una alerta pendiente, un mouse B100 confirmado (`MOU-0108`), un mouse de modelo desconocido sin límites, sesiones normales e inesperadas (la última en curso), incidentes de todos los tipos y eventos repartidos por día y hora. Opciones: `--hasta AAAA-MM-DD` (último día con datos, por defecto hoy), `--dias N` (de 10 a 365, por defecto 21) y `--semilla N` (la misma semilla da exactamente la misma base).

- Es seguro volver a ejecutarlo: si el archivo ya es una base de ejemplo, se vuelve a crear. Si el archivo existe y **no** lo es (por ejemplo, la base real), no lo toca y avisa.
- Los eventos son una muestra reducida; los contadores son los que reflejan el desgaste.
- Los nombres de teclas, los correos (dominio `.invalid`) y las etiquetas son inventados, y no hay ninguna contraseña (RNF4, RNF10).

Para ver el VID/PID de un teclado en Windows: `Get-PnpDevice -Class Keyboard | Select FriendlyName, InstanceId`.
