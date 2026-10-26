# Prueba del capturador en Windows

Guía para comprobar en un PC con Windows lo que no se puede probar en macOS: que **Raw Input** recibe el teclado y el mouse, que se lee bien el VID/PID y que los eventos llegan a Python en menos de 1 segundo (RNF1). Dura unos 15 minutos.

> **Importante:** durante las pruebas el programa escribe en pantalla las teclas que pulsas. **No escribas contraseñas ni datos personales.** Al terminar, pega en el reporte solo los resultados que pide la guía, nunca el texto de la pantalla de la parte A.

## Qué necesitas

| Para | Necesitas |
|---|---|
| Parte A (obligatoria) | Un PC con Windows 10 u 11 y el archivo `captura.exe`. No hay que instalar nada. |
| Partes B y C | Además, Python 3.12 o superior (con la opción "Add Python to PATH", que instala el comando `py`) y este repositorio descargado (`git clone` o el ZIP de GitHub). |
| Parte D (opcional) | Visual Studio 2022 Build Tools con "Desarrollo para el escritorio con C++" y CMake. |

El `captura.exe` se compiló desde macOS con MinGW-w64, a partir del código de `capturador/`. Se enlazó de forma estática: solo usa las bibliotecas propias de Windows.

## Parte A: el capturador solo (5 minutos)

Abre PowerShell en la carpeta donde está `captura.exe` y ejecútalo:

```powershell
.\captura.exe
```

El programa no abre ninguna ventana propia y no muestra nada hasta que haya actividad. Haz cada acción y marca el resultado:

| # | Acción | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| A1 | Pulsa y suelta la tecla `E` una vez | Dos líneas: `tecla_presionada` (con `"tecla":"E"`) y `tecla_liberada` (sin `tecla`) | |
| A2 | Mantén pulsada la tecla `A` durante 3 segundos y suéltala | **Una** línea `tecla_presionada` y, al soltar, una `tecla_liberada`. Sin repeticiones | |
| A3 | Pulsa `Enter`, la barra espaciadora y `F5` | Los nombres salen como `ENTER`, `ESPACIO` y `F5`, aunque el teclado esté en otro idioma | |
| A4 | Mueve el mouse sin parar durante 3 segundos | Líneas `mouse_movimiento` con `x` e `y`, **a lo sumo unas 10 por segundo** | |
| A5 | Haz un clic izquierdo y uno derecho | Una línea `clic_izquierdo` y una `clic_derecho` | |
| A6 | Gira la rueda un paso hacia arriba y uno hacia abajo | `scroll` con `"pasos":1` y `"pasos":-1` | |
| A7 | Mira el `vid` y el `pid` de las líneas | Coinciden con los de tus dispositivos (ver más abajo) | |
| A8 | Cambia a otra ventana y sigue escribiendo | Las líneas siguen apareciendo (el programa recibe teclas aunque no tenga el foco) | |
| A9 | Pulsa `Ctrl+C` | El programa termina | |

Para comparar el VID/PID (A7), en otra ventana de PowerShell:

```powershell
Get-PnpDevice -Class Keyboard | Select FriendlyName, InstanceId
Get-PnpDevice -Class Mouse | Select FriendlyName, InstanceId
```

El `InstanceId` contiene algo como `VID_046D&PID_C31C`. Un teclado o mouse virtual, de escritorio remoto o PS/2 puede no tener VID/PID: en ese caso el capturador escribe `0000`, y es lo esperado.

## Parte B: el capturador y Python juntos (5 minutos)

Desde la carpeta raíz del repositorio, con `captura.exe` copiado dentro:

```powershell
py -m pruebas.manual_windows --capturador captura.exe --segundos 30
```

El script solo usa la biblioteca estándar de Python: no hace falta crear un entorno virtual ni instalar nada.

Durante los 30 segundos escribe, mueve el mouse, haz clic y gira la rueda. Al final aparece un resumen. Compruébalo:

| # | Qué mirar | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| B1 | Mientras corre la prueba | **No aparece ninguna ventana negra nueva** ni parpadea una (RNF11) | |
| B2 | `Eventos válidos recibidos` | Mayor que 0 | |
| B3 | `Dispositivos vistos` | Aparecen tu teclado y tu mouse con su `VID:PID` | |
| B4 | `Líneas descartadas` | 0 | |
| B5 | `Caídas del capturador` | 0 | |
| B6 | `Retraso hasta Python` | El **máximo** es menor a 1000 ms (RNF1) | |
| B7 | `Veredicto` | `CUMPLE` | |

## Parte C: recuperación si el capturador se cae (3 minutos)

Ejecuta una prueba más larga:

```powershell
py -m pruebas.manual_windows --capturador captura.exe --segundos 60
```

A los 15 segundos, abre el Administrador de tareas, busca `captura.exe` (en "Detalles") y finalízalo. Sigue escribiendo hasta que termine la prueba.

| # | Qué mirar | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| C1 | `Caídas del capturador` | Al menos 1 | |
| C2 | `Eventos válidos recibidos` | Siguen aumentando después de la caída (el capturador se relanzó solo, RF21) | |
| C3 | Después de relanzar | `captura.exe` vuelve a aparecer en el Administrador de tareas | |

El veredicto será `NO CUMPLE` en esta parte porque hubo una caída: es lo esperado.

## Parte D (opcional): compilar desde el código

En una consola "Developer PowerShell for VS 2022", desde la raíz del repositorio:

```powershell
cmake -S capturador -B capturador\build
cmake --build capturador\build --config Release
ctest --test-dir capturador\build -C Release
.\capturador\build\Release\captura.exe --simulado --cantidad 5
```

Resultado esperado: la compilación termina sin errores ni advertencias, `ctest` informa que pasa la prueba `unitarias` y el último comando escribe 5 líneas JSON. Esta parte comprueba también que `CMakeLists.txt` funciona, algo que aún no se ha podido verificar.

## Reporte de la prueba

Escribe en la conversación del equipo, o en un comentario del pull request:

1. La versión de Windows (por ejemplo, Windows 11 23H2) y el modelo del teclado y del mouse.
2. La tabla de las partes A, B y C con "sí" o "no" en cada fila.
3. El bloque `Resultado de la prueba` de la parte B, copiado tal cual. Ese bloque **no** contiene teclas.
4. Cualquier cosa que haya sorprendido: una ventana que apareció, una tecla con nombre raro (por ejemplo `VK_E5`), un dispositivo con `0000`, etc.

## Qué no cubre esta guía

- El nombre del producto (`nombre`) todavía no se envía.
- El inicio automático con el Programador de tareas (RF21) se probará en el Sprint 6.
- Si dos teclados están conectados a la vez, el filtro de repetición es común a los dos. Es una simplificación conocida.
