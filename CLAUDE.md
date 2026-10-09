# Capturador y Auditor de Eventos de Entrada (Caso 4)

Proyecto grupal del curso **Programación de interfaces** (UTP). Repositorio: `watchman-mouse-keyboard`.
Equipo: Liu Sam Fung (Scrum Master), Aldair Lozano, Marcos Matos y Jose Espinoza. Todos programan.

## Regla de idioma

Todo en **español**: respuestas, comentarios, mensajes de commit, documentación, nombres de tablas y columnas. Los identificadores de código en Python y C++ también van en español cuando sea natural (`contador_diario`, `evaluar_umbral`). Solo cambia a inglés si el usuario lo pide.

## Qué hace el sistema

Se instala en cada PC de trabajo. Detecta qué teclado o mouse generó cada evento, cuenta el desgaste (pulsaciones por tecla, clics por botón, pasos de scroll) y **avisa por correo a Soporte TI cuando un periférico llega al 90 % y al 100 % de la vida útil que garantiza el fabricante**. El objetivo es prevenir fallos: que el trabajador no se quede sin teclado o mouse y que Soporte TI no tenga que revisar cada PC a mano. Además guarda eventos y sesiones, genera reportes CSV y un mapa de calor del uso por hora y día.

Actores: **Trabajador** (pasivo, no ve pantallas, el sistema es transparente) y **Soporte TI** (usa la interfaz en el PC del trabajador, presencial o por escritorio remoto, porque cada PC tiene su propia base de datos).

## Stack y componentes

```
C++ (Raw Input) ──stdout JSON──▶ Servicio Python ──▶ SQLite (eventos.db) ◀── Interfaz Tkinter
                                      │                                          │
                                      └── correo (smtplib) + keyring             └── reportes CSV
```

- **Capturador (C++, Windows)**: usa **Raw Input** (no `SetWindowsHookEx`) para identificar el dispositivo por VID/PID. Escribe un evento JSON por línea en stdout. **No toca la base de datos.**
- **Servicio de monitoreo (Python, `pythonw`, sin ventana)**: lanza el capturador con `subprocess`, lee su stdout en tiempo real, valida, guarda, cuenta el desgaste, evalúa umbrales y envía correos. Si el capturador se cae, lo relanza.
- **Interfaz de escritorio (Python + Tkinter/ttk)**: 8 pantallas (P01 a P08) para Soporte TI. Se usa Tkinter porque es lo que se ve en clase.
- **Base de datos**: SQLite local por equipo, sin servidor ni puerto. Ruta sugerida `C:\ProgramData\CapturadorEventos\eventos.db` (configurable).
- **Reportes**: CSV con el módulo `csv`.

## Decisiones de arquitectura (no las cambies sin preguntar)

1. **Dos procesos Python separados** (servicio e interfaz). Se comunican **solo por SQLite**: la interfaz escribe la orden de iniciar o detener en la tabla `configuracion` y el servicio la lee periódicamente.
2. **Inicio automático**: tarea del Programador de tareas de Windows con disparador **"al iniciar sesión"**, no "al encender el equipo" (por el aislamiento de la sesión 0, un servicio al arranque no podría ver el teclado y el mouse del usuario). Algunos diagramas antiguos dicen "al encender el equipo"; el texto correcto es **al iniciar sesión**.
3. **Sesión** = desde que el servicio inicia (al iniciar sesión en Windows) hasta que el equipo se apaga. El total diario es la suma de las sesiones del día.
4. **Solo Python accede a SQLite**, y lo hace a través de un único módulo de repositorio. Conexión con `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON` y `busy_timeout` (hay dos procesos escribiendo y leyendo).
5. **Identificación del periférico**: el modelo se reconoce por VID/PID. Dos unidades idénticas suelen compartir VID/PID y a veces no tienen número de serie, así que la **unidad física** se identifica con una **etiqueta de inventario** (por ejemplo `TEC-0042`) que Soporte TI confirma; mientras tanto la asignación queda `por_confirmar`.
6. **Alertas**: una sola por periférico y umbral (índice único `(id_periferico, umbral)`). Se guarda como `pendiente` **antes** de intentar enviar. Reintentos: al minuto, a los 5 minutos y luego cada 15. Si no se pudo enviar, queda pendiente y se reenvía en la siguiente sesión.
7. **Correo**: `smtplib`, SMTP 587 con TLS, cuenta de Gmail dedicada con contraseña de aplicación.

## Reglas que nunca se rompen

- **Credenciales fuera del código y de GitHub (RNF10).** La contraseña del correo vive en el Administrador de credenciales de Windows vía `keyring`. En `configuracion` solo van servidor, puerto, remitente y destinatarios. Nunca escribas contraseñas, tokens ni correos reales en el código, en `schema.sql`, en pruebas ni en commits.
- **Privacidad (RNF4).** Nunca se guarda qué tecla se pulsó con orden ni secuencia. La tabla `evento` no tiene columna de tecla. Las teclas solo existen como **contadores agregados por día** en `contador_diario`. La identidad de la tecla se usa solo en memoria y **nunca se escribe en logs** (ni siquiera en modo depuración).
- **Transparencia (RNF11).** El trabajador no ve ventanas, mensajes ni iconos. Cualquier fallo del servicio se registra en `incidente`, nunca se muestra en pantalla.
- **Tolerancia a apagados bruscos (RNF12).** Escribir en la base con frecuencia y en transacciones cortas; los contadores se guardan cada minuto. Al arrancar, cerrar como `inesperado` cualquier sesión que haya quedado abierta.
- No subir `*.db`, `*.db-wal`, `*.db-shm`, `*.csv` de reportes, `.env` ni binarios compilados (ver `.gitignore`).
- Solo bibliotecas gratuitas o de código abierto (RNF7).

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Requerimientos RF1–RF23 y RNF1–RNF12 | `docs/requerimientos.md` |
| Arquitectura explicada y decisiones | `docs/arquitectura/README.md` |
| Diagramas C4 (contexto, contenedores, 3 de componentes, despliegue) | `docs/arquitectura/*.puml` |
| Flujos del Trabajador y de Soporte TI | `docs/flujos/flujo-trabajador.puml`, `docs/flujos/flujo-soporte-ti.puml` |
| Diagramas de procesos (versión inicial, Avance 1) | `docs/flujos/procesos/` |
| Base de datos: diccionario y relaciones | `docs/base-de-datos/README.md` |
| DBML para dbdiagram.io | `docs/base-de-datos/estructura-dbdiagramio` (conviene renombrar a `.dbml`) |
| Esquema real de SQLite | `docs/base-de-datos/schema.sql` |
| Mockups de las pantallas P01–P08 | `docs/mockups/` (ver su `README.md`) |

Lee el documento que corresponda **antes** de implementar esa parte. El esquema de SQLite de `schema.sql` es la fuente de verdad de las tablas; si cambias una tabla, actualiza también el DBML y el diccionario.

## Estructura de código prevista (propuesta, aún no creada)

```
capturador/        C++ (Raw Input). CMakeLists.txt o proyecto de Visual Studio
servicio/          Python: gestor_subproceso, validador, sesion, contador, evaluador, notificador, control
ui/                Python + Tkinter: una clase por pantalla P01–P08
comun/             Python: repositorio SQLite, configuración, constantes (compartido por servicio e interfaz)
pruebas/           pytest
```

Los nombres de módulos salen de los diagramas de componentes (`docs/arquitectura/diagrama-componentes-*.puml`). Antes de crear carpetas, confirma con el equipo.

## Cómo trabajar

- Plataforma objetivo: **Windows** (RNF2). El desarrollo de partes en Python puede hacerse en otro sistema, pero Raw Input, `keyring` con el Administrador de credenciales y el Programador de tareas se prueban en Windows.
- Python 3.12 o superior. Dependencias mínimas: `keyring`; el resto es biblioteca estándar (`sqlite3`, `subprocess`, `smtplib`, `csv`, `tkinter`). Deja las dependencias en `requirements.txt`.
- Para crear la base de datos: ejecutar `docs/base-de-datos/schema.sql` (incluye los `PRAGMA` y datos de ejemplo de modelos y límites).
- Ramas por funcionalidad (`feat/...`, `fix/...`) y pull request hacia `main`; commits en español, cortos y descriptivos.
- Equipo trabajando por **Scrum**, sprints de 2 semanas, programación de la semana 6 a la 17, entrega final el lunes de la semana 17 (30 de noviembre de 2026). El planning detallado entrará en `docs/planning.md` cuando esté cerrado.
- Si algo del enunciado, los requisitos o los diagramas se contradice, **pregunta** antes de elegir una versión.
