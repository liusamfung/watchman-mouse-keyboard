# Contrato JSON entre el capturador (C++) y el servicio (Python)

> **Estado: acordado para el Sprint 3 (25/10/2026).** Define qué escribe el capturador por `stdout` y qué espera leer el servicio. Es el único acuerdo entre las dos mitades del Sprint 3: con él, cada persona prueba su parte sin esperar a la otra. Las decisiones tomadas están al final del documento.

Cubre RF1, RF3, RF4, RF5, RF6, RF7, RF9 y RNF4, RNF8. Los nombres de los tipos de evento son los mismos que acepta la tabla `evento` de `docs/base-de-datos/schema.sql`.

## Reglas generales

1. **Una línea por evento.** Cada línea de `stdout` es un objeto JSON completo, terminado en `\n` (formato JSON Lines).
2. **Codificación UTF-8**, sin BOM.
3. **El capturador vacía el búfer después de cada línea** (`flush`), para no introducir retrasos (RNF1).
4. **`stdout` es solo para eventos.** Los mensajes técnicos del capturador (arranque, errores) van por `stderr`.
5. **Privacidad (RNF4).** Ni `stdout` ni `stderr` ni ningún log pueden escribir qué tecla se pulsó. El campo `tecla` existe solo para que el servicio incremente su contador en memoria.
6. **Sin base de datos.** El capturador nunca abre `eventos.db`.

## Campos

| Campo | Tipo | Obligatorio en | Descripción |
|---|---|---|---|
| `v` | entero | todos | Versión del contrato. Hoy es `1`. |
| `tipo` | texto | todos | Uno de: `tecla_presionada`, `tecla_liberada`, `mouse_movimiento`, `clic_izquierdo`, `clic_derecho`, `scroll`. |
| `hora` | texto | todos | Hora local del evento en ISO 8601, con milisegundos: `2026-10-25T21:14:03.482`. **La pone el capturador.** |
| `dispositivo` | texto | todos | `teclado` o `mouse`. |
| `vid` | texto | todos | Identificador del fabricante, 4 dígitos hexadecimales en mayúscula (por ejemplo `046D`). |
| `pid` | texto | todos | Identificador del producto, 4 dígitos hexadecimales en mayúscula (por ejemplo `C31C`). |
| `nombre` | texto | opcional | Nombre del producto que informa Windows. |
| `tecla` | texto | `tecla_presionada` | Nombre de la tecla en mayúsculas (`E`, `ENTER`, `ESPACIO`, `F5`), enviado por el capturador. **Solo se usa para el contador.** |
| `x`, `y` | entero | `mouse_movimiento` | Posición **absoluta** del cursor en píxeles de pantalla (`GetCursorPos`). |
| `pasos` | entero | `scroll` | Pasos **enteros** de la rueda. Positivo hacia arriba, negativo hacia abajo. |

Reglas por tipo:

| `tipo` | Debe traer | No debe traer |
|---|---|---|
| `tecla_presionada` | `tecla` | `x`, `y`, `pasos` |
| `tecla_liberada` | — | `tecla`, `x`, `y`, `pasos` |
| `mouse_movimiento` | `x`, `y` | `tecla`, `pasos` |
| `clic_izquierdo` | — | `tecla`, `x`, `y`, `pasos` |
| `clic_derecho` | — | `tecla`, `x`, `y`, `pasos` |
| `scroll` | `pasos` (distinto de 0) | `tecla`, `x`, `y` |

`dispositivo` debe ser coherente con `tipo`: los tipos de tecla solo vienen de un `teclado` y el resto, de un `mouse`.

## Ejemplos

```json
{"v":1,"tipo":"tecla_presionada","hora":"2026-10-25T21:14:03.482","dispositivo":"teclado","vid":"046D","pid":"C31C","nombre":"Logitech K120","tecla":"E"}
{"v":1,"tipo":"tecla_liberada","hora":"2026-10-25T21:14:03.560","dispositivo":"teclado","vid":"046D","pid":"C31C","nombre":"Logitech K120"}
{"v":1,"tipo":"mouse_movimiento","hora":"2026-10-25T21:14:04.101","dispositivo":"mouse","vid":"046D","pid":"C077","x":812,"y":455}
{"v":1,"tipo":"clic_izquierdo","hora":"2026-10-25T21:14:04.730","dispositivo":"mouse","vid":"046D","pid":"C077"}
{"v":1,"tipo":"scroll","hora":"2026-10-25T21:14:05.215","dispositivo":"mouse","vid":"046D","pid":"C077","pasos":-3}
```

## Qué hace el servicio con cada línea

| Paso | Componente | Acción |
|---|---|---|
| 1 | Gestor del subproceso | Lee la línea de `stdout` en tiempo real (RF3). |
| 2 | Validador de eventos | Comprueba que es JSON y que cumple las reglas de arriba. |
| 3 | Repositorio SQLite | Busca el `modelo_periferico` por `vid` y `pid`, y el `periferico` del equipo (RF17, RF18). |
| 4 | Repositorio SQLite | Guarda una fila en `evento` con `tipo_evento`, `fecha_hora`, `x` e `y`. **No se guarda `tecla`.** |
| 5 | Contador de desgaste | Suma al contador en memoria y lo guarda en `contador_diario` cada minuto. |

Cómo se convierte cada evento en un conteo:

| `tipo` | `tipo_conteo` | `elemento` | `cantidad` |
|---|---|---|---|
| `tecla_presionada` | `pulsacion_tecla` | valor de `tecla` | +1 |
| `clic_izquierdo` | `clic_boton` | `izquierdo` | +1 |
| `clic_derecho` | `clic_boton` | `derecho` | +1 |
| `scroll` | `scroll_paso` | `rueda` | +valor absoluto de `pasos` |

`tecla_liberada` y `mouse_movimiento` se guardan como evento pero no suman a ningún contador.

## Líneas inválidas (RF9)

El servicio **no se detiene** ante una línea inválida: la descarta, registra un `incidente` y sigue leyendo.

| Caso | `incidente.tipo` |
|---|---|
| La línea no es JSON válido | `error_comunicacion` |
| Es JSON, pero falta un campo obligatorio, sobra un campo prohibido, el tipo es desconocido o un valor está fuera de rango | `evento_invalido` |

**Importante (RNF4):** el `detalle` del incidente describe el problema (por ejemplo, "falta el campo `hora`"), pero **nunca copia la línea completa**, porque podría contener `tecla`.

## Cierre del capturador (RF10)

El capturador no envía un mensaje de despedida. El servicio detecta que terminó porque el subproceso termina (código de salida) o porque `stdout` se cierra. Lo registra como incidente `caida_proceso` y lo relanza.

## Cómo probar sin Windows

El contrato permite sustituir al capturador por un script de Python que escriba estas mismas líneas. Así el servicio, el validador y el contador se desarrollan y prueban en cualquier sistema operativo. Solo la captura real con Raw Input requiere Windows.

## Decisiones acordadas (25/10/2026)

Se priorizó que el sistema sea lo más simple posible y que el capturador haga el trabajo que solo él puede hacer.

| # | Tema | Decisión | Consecuencia para el código |
|---|---|---|---|
| 1 | Hora del evento | La pone **el capturador**. | El servicio guarda `hora` tal como llega; no usa el reloj de Python. |
| 2 | Nombre de la tecla | **C++ envía el nombre** (`E`, `ENTER`). | Python lo usa tal cual como `elemento`; no necesita una tabla de traducción. |
| 3 | Repetición automática | Una tecla mantenida cuenta como **una sola pulsación**. | El capturador recuerda qué teclas están presionadas y **no envía** la repetición hasta que se suelte. Python no puede hacerlo, porque `tecla_liberada` no trae la tecla (RNF4). |
| 4 | Posición del cursor | Posición **absoluta** (`GetCursorPos`). | El capturador lee la posición del cursor en cada movimiento. |
| 5 | Rueda del mouse | **Pasos enteros.** | El capturador convierte el valor de Windows (múltiplos de 120) a pasos enteros y acumula el resto hasta completar un paso. |
| 6 | Dos unidades idénticas | **No se envía** identificador de instancia. | El servicio reconoce el modelo por `vid` y `pid`. Dos unidades iguales en un mismo equipo se distinguen por la etiqueta que confirma Soporte TI (RF18). |
