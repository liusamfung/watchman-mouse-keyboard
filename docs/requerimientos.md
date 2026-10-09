# Requerimientos del sistema

Versión aprobada para el Avance 2. Los RF1 a RF15 y RNF1 a RNF8 vienen del enunciado del Caso 4 y conservan su numeración. RF16 a RF23 y RNF9 a RNF12 se añadieron por la funcionalidad de alerta de desgaste. RNF4 está reformulado.

Contexto de la ampliación: la finalidad del proyecto es prevenir que los trabajadores se queden sin teclado o mouse durante el día, y que Soporte TI no tenga que revisar cada PC a mano. Por eso el sistema cuenta el desgaste de cada periférico y avisa por correo antes de que llegue al límite que garantiza el fabricante.

## Requerimientos funcionales

| N.º | Requerimiento | Origen |
|---|---|---|
| RF1 | Identificar el tipo de dispositivo que generó cada evento: teclado o mouse. | Enunciado |
| RF2 | Con Python, ejecutar el binario de C++ como un subproceso. | Enunciado |
| RF3 | Con Python, leer en tiempo real los eventos enviados por stdout. | Enunciado |
| RF4 | Enviar los eventos capturados desde C++ por stdout en formato JSON. | Enunciado |
| RF5 | Detectar eventos del teclado, incluyendo pulsaciones y liberaciones. | Enunciado |
| RF6 | Registrar eventos relevantes del mouse: movimiento, clic izquierdo, clic derecho y desplazamiento. | Enunciado |
| RF7 | Registrar las coordenadas X/Y del cursor en los eventos de movimiento del mouse. | Enunciado |
| RF8 | Asociar un identificador único a cada evento almacenado. | Enunciado |
| RF9 | Registrar errores de comunicación y eventos inválidos. | Enunciado |
| RF10 | Detectar cuando el proceso de C++ finaliza inesperadamente (por ejemplo, se desconecta el mouse o el teclado). | Enunciado |
| RF11 | Permitir iniciar y detener la captura de eventos desde el módulo de Python. | Enunciado |
| RF12 | Calcular el tiempo de actividad registrado del mouse y del teclado en cada sesión. | Enunciado |
| RF13 | Almacenar los eventos capturados en la base de datos SQLite. | Enunciado |
| RF14 | Generar reportes de los eventos y métricas registrados en formato CSV. | Enunciado |
| RF15 | Analizar patrones de uso del teclado y del mouse con los eventos registrados. | Enunciado |
| RF16 | Llevar contadores de desgaste por periférico: pulsaciones por tecla, clics por botón y pasos de scroll. | Nuevo |
| RF17 | Reconocer el modelo del periférico por VID/PID y consultar su límite de vida útil en una tabla de límites por modelo (uno por tipo de conteo). | Nuevo |
| RF18 | Asociar cada periférico físico a un equipo mediante una etiqueta de inventario (sticker). Si la unidad no se puede identificar con certeza, la asignación queda "por confirmar" hasta que Soporte TI la confirme. | Nuevo |
| RF19 | Generar una alerta cuando un contador llegue al 90 % y otra al 100 % del límite, una sola vez por periférico y umbral. | Nuevo |
| RF20 | Enviar la alerta por correo a Soporte TI con reintentos al minuto, a los 5 minutos y luego cada 15 minutos. Si no se puede enviar, guardarla como pendiente y reenviarla en la siguiente sesión. | Nuevo |
| RF21 | Iniciar el programa automáticamente al iniciar sesión en Windows y relanzarlo de forma transparente si se cierra inesperadamente. | Nuevo |
| RF22 | Mostrar un mapa de calor (heatmap) o distribución por horas del uso de los dispositivos de entrada, para evaluar patrones de fatiga laboral. | Nuevo (herramienta del enunciado) |
| RF23 | Ofrecer una interfaz de escritorio para Soporte TI con estado, periféricos, sesiones, análisis, reportes, alertas e incidentes, y configuración. | Nuevo |

## Requerimientos no funcionales

| N.º | Requerimiento | Origen |
|---|---|---|
| RNF1 | Procesar los eventos en tiempo real sin retrasos perceptibles en la captura. | Enunciado |
| RNF2 | Ejecutarse, como mínimo, en el sistema operativo Windows. | Enunciado |
| RNF3 | Usar SQLite como almacenamiento local, sin servidor de base de datos externo. | Enunciado |
| RNF4 | **Reformulado.** Solo se almacenan contadores agregados por periférico y por día. La identidad de la tecla se usa únicamente en memoria y nunca se escribe en logs, y no se guarda el orden ni la secuencia de teclas, credenciales, contraseñas ni información sensible del usuario. | Reformulado |
| RNF5 | Separar el código en módulos independientes para captura, procesamiento, persistencia y generación de reportes. | Enunciado |
| RNF6 | Que la estructura de SQLite permita almacenar grandes cantidades de eventos sin comprometer significativamente las consultas principales (índices, claves foráneas, WAL). | Enunciado |
| RNF7 | Usar exclusivamente tecnologías y bibliotecas gratuitas o de código abierto. | Enunciado |
| RNF8 | Usar un formato de datos estandarizado y fácil de procesar (JSON) entre C++ y Python. | Enunciado |
| RNF9 | Los límites por modelo, los umbrales de alerta y los destinatarios deben ser configurables sin tocar el código. | Nuevo |
| RNF10 | Las credenciales (contraseña del correo) deben guardarse fuera del código y del repositorio, en el Administrador de credenciales de Windows mediante `keyring`. | Nuevo |
| RNF11 | El sistema debe operar de forma transparente para el trabajador: sin ventanas, mensajes ni impacto perceptible en el equipo. | Nuevo |
| RNF12 | El sistema debe tolerar apagados bruscos sin perder los datos ya guardados ni duplicar o perder alertas. | Nuevo |

## Actores

- **Trabajador**: actor pasivo. Usa su teclado y su mouse con normalidad; no ve ninguna pantalla del sistema.
- **Soporte TI**: usa la interfaz de escritorio en el PC del trabajador, presencialmente o por escritorio remoto, porque cada PC tiene su propia base de datos. Recibe las alertas por correo.

## Limitaciones conocidas

- Cada PC guarda su propia base de datos, así que no hay vista consolidada de toda la empresa.
- La contraseña del correo está en cada PC. Un usuario avanzado con acceso a la cuenta de Windows podría extraerla; por eso debe usarse una cuenta dedicada y con permisos mínimos.
- Dos periféricos idénticos comparten VID/PID, y por eso la unidad física depende de la etiqueta de inventario que confirme Soporte TI.
- El enunciado menciona `SetWindowsHookEx`; el proyecto usa Raw Input porque permite identificar qué dispositivo generó cada evento.
