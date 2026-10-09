# Arquitectura

Modelo C4 dibujado con PlantUML (biblioteca estándar `C4`). Los diagramas están en esta carpeta; se pueden renderizar con la extensión de PlantUML de VS Code o con `plantuml archivo.puml`.

| Nivel | Archivo | Qué muestra |
|---|---|---|
| 1. Contexto | `diagrama-contexto.puml` | El sistema, Soporte TI, el trabajador y los sistemas externos. |
| 2. Contenedores | `diagrama-contenedores.puml` | Capturador, servicio, interfaz, base de datos y reportes. |
| 3. Componentes (C++) | `diagrama-componentes-cpp.puml` | Interior del capturador. |
| 3. Componentes (servicio) | `diagrama-componentes-python.puml` | Interior del servicio de monitoreo. |
| 3. Componentes (interfaz) | `diagrama-componentes-tkinter.puml` | Interior de la interfaz de escritorio. |
| Despliegue | `diagrama-despliegue.puml` | Qué corre en cada equipo y dónde viven los datos. |

> **Nota:** la tarea del Programador de tareas se dispara **al iniciar sesión** del usuario, no al encender el equipo (aislamiento de la sesión 0).

## Visión general

Todo se instala en **cada PC de trabajo**; no hay servidor central. Dos procesos de Python y un ejecutable de C++ comparten una base de datos SQLite local.

1. **Capturador (C++).** Se registra en Windows con Raw Input para recibir los eventos de teclado y mouse junto con el identificador del dispositivo (VID/PID). Escribe un evento JSON por línea en stdout. No conoce la base de datos.
2. **Servicio de monitoreo (Python, `pythonw`).** Lanza el capturador con `subprocess`, lee su stdout, valida cada línea, la guarda, actualiza los contadores de desgaste, evalúa los umbrales y envía los correos. Si el capturador se cae, lo detecta y lo relanza.
3. **Interfaz (Python + Tkinter).** Pantallas P01 a P08 para Soporte TI. Lee la base de datos, escribe la configuración y la orden de iniciar o detener, y genera los reportes CSV.
4. **Base de datos (SQLite).** Punto de encuentro entre el servicio y la interfaz.

## Decisiones y por qué

- **Raw Input y no `SetWindowsHookEx`.** Un gancho global no dice qué dispositivo generó la tecla; Raw Input sí entrega el identificador del dispositivo, necesario para contar el desgaste por periférico.
- **Dos procesos que se comunican por SQLite.** Evita sockets o tuberías adicionales. La interfaz deja la orden de iniciar o detener en `configuracion` y el servicio la lee periódicamente. La base usa WAL para que ambos procesos convivan.
- **Solo Python toca la base de datos.** El capturador es un proceso mínimo que solo produce JSON, lo que facilita probarlo y reemplazarlo.
- **Inicio al iniciar sesión.** Un servicio que arranca con el equipo corre en la sesión 0, aislada, y no ve el teclado ni el mouse del usuario. Por eso se usa una tarea del Programador de tareas con disparador "al iniciar sesión".
- **Contraseña en el Administrador de credenciales de Windows.** El servicio la lee con `keyring`; la interfaz la guarda o la cambia. Nunca está en el código, en el repositorio ni en la base.
- **Correo con `smtplib`.** SMTP en el puerto 587 con TLS, usando una cuenta dedicada y una contraseña de aplicación.

## Flujo de una alerta (resumen)

1. El capturador envía un evento con el VID/PID.
2. El validador lo comprueba y el contador suma la tecla, el clic o el paso de scroll.
3. Cada minuto se guardan los contadores y el evaluador calcula el porcentaje frente al límite del modelo.
4. Al llegar al 90 % o al 100 %, se crea la alerta como `pendiente` (una sola vez por periférico y umbral).
5. El notificador envía el correo; si falla, reintenta al minuto, a los 5 minutos y luego cada 15, y deja la alerta pendiente para la siguiente sesión.
