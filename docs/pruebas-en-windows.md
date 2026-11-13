# Prueba del capturador y de la interfaz en Windows

Guía para comprobar en un PC con Windows lo que no se puede probar en macOS: que **Raw Input** recibe el teclado y el mouse, que se lee bien el VID/PID y que los eventos llegan a Python en menos de 1 segundo (RNF1). Las partes A a C duran unos 15 minutos. Las partes E a G (pruebas automáticas, interfaz y base de datos en `C:\ProgramData`) agregan unos 25 minutos más; Windows es el sistema de destino, así que todo lo que se programa en macOS debe confirmarse aquí.

> **Importante:** durante las pruebas el programa escribe en pantalla las teclas que pulsas. **No escribas contraseñas ni datos personales.** Al terminar, pega en el reporte solo los resultados que pide la guía, nunca el texto de la pantalla de la parte A.

## Qué necesitas

| Para | Necesitas |
|---|---|
| Parte A (obligatoria) | Un PC con Windows 10 u 11 y el archivo `captura.exe`. No hay que instalar nada. |
| Partes B y C | Además, Python 3.12 o superior (con la opción "Add Python to PATH", que instala el comando `py`) y este repositorio descargado (`git clone` o el ZIP de GitHub). |
| Parte D (opcional) | Visual Studio 2022 Build Tools con "Desarrollo para el escritorio con C++" y CMake. |
| Partes E, F y G | Python 3.12 o superior **instalado desde python.org** con la opción "tcl/tk and IDLE" marcada (viene marcada por defecto; trae Tkinter, que usa la interfaz) y este repositorio actualizado (`git pull` en `main`). No hace falta `captura.exe`. |

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

## Parte E: las pruebas automáticas completas en Windows (10 minutos)

Hasta ahora las pruebas automáticas solo se han ejecutado en macOS. Esta parte comprueba que también pasan en Windows, el sistema de destino. Desde la carpeta raíz del repositorio:

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements-desarrollo.txt
.venv\Scripts\python -m pytest pruebas -q -rs
.venv\Scripts\basedpyright
```

| # | Qué mirar | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| E1 | Última línea de `pytest` | `passed` y **ningún** `failed` ni `error`. Hoy son 271 pruebas: con un compilador de C++ pasan las 271; sin él (lo normal en Windows), `260 passed, 11 skipped`. Anota el número exacto | |
| E2 | Con un compilador moderno (por ejemplo `winget install BrechtSanders.WinLibs.POSIX.UCRT`, gcc 16) | Pasan 270 y se omite 1 (la de "sin modo simulado", que solo aplica fuera de Windows). Un MinGW viejo (mingw.org, gcc 6) no soporta C++17 y debe quitarse del PATH. Sin sanitizers: WinLibs no trae `asan` ni `ubsan` y las pruebas los omiten solas | |
| E2b | Las pruebas omitidas (`skipped`) | Solo las de C++ (`test_capturador_cpp.py`), si no hay `g++` o `clang++` en el PATH. Ninguna de `test_ui_aplicacion.py` debe aparecer como omitida: si aparece "este Python no trae Tk", reinstala Python marcando "tcl/tk and IDLE" | |
| E3 | `basedpyright` | `0 errors, 0 warnings, 0 notes` | |

Si algo falla, copia el nombre de la prueba y las 10 líneas del error: es justo lo que esta parte busca (algo que funciona en macOS y no en Windows, como rutas con `\`, la codificación o los bloqueos de archivos de SQLite).

## Parte F: la base de ejemplo y la interfaz (10 minutos)

La interfaz (`ui/`) tiene hoy su estructura: ventana, menú y las 8 pantallas como "en construcción". Se prueba con la base de ejemplo, que crea datos inventados y no toca ninguna base real:

```powershell
py -m pruebas.base_de_ejemplo $env:TEMP\ejemplo.db
py -m ui --base $env:TEMP\ejemplo.db
```

El primer comando debe mostrar un resumen (`4 periféricos, … sesiones, … eventos, 3 alertas y … incidentes`). El segundo abre la ventana.

| # | Qué mirar | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| F1 | La ventana al abrir | Se abre en "Panel principal" con una banda azul arriba, un menú a la izquierda y una barra de estado abajo, parecido a `docs/mockups/P01_PanelPrincipal.png` | |
| F2 | Banda azul | A la izquierda `Equipo: PC-EJEMPLO-01`; a la derecha `Sesión iniciada hoy a las 08:xx a. m.` (la base de ejemplo termina hoy y su última sesión está en curso) | |
| F3 | Nitidez del texto | El texto se ve **nítido**, no borroso. Pruébalo con la escala de pantalla en 125 % o 150 % (Configuración > Pantalla > Escala) | |
| F4 | Menú | Siete botones, en este orden: Panel principal, Periféricos, Sesiones, Análisis de uso, Reportes, Alertas e incidentes, Configuración | |
| F5 | Haz clic en cada botón | Cambian el título y el subtítulo, el botón de la pantalla actual queda resaltado y aparece el aviso "Pantalla en construcción · issue #…" | |
| F6 | Barra de abajo | Dice `Base de datos: ejemplo.db` | |
| F7 | Cambia el tamaño de la ventana | No se puede hacer más pequeña que unos 900 × 560 y nada se corta al agrandarla | |
| F8 | Cierra con la X | Se cierra sin errores y sin dejar procesos de Python en el Administrador de tareas | |
| F9 | Sin consola: `pyw -m ui --base $env:TEMP\ejemplo.db` | La ventana abre **sin** ninguna ventana negra de consola | |
| F10 | Un archivo que no existe: `pyw -m ui --base C:\no\existe.db` | Aparece un **cuadro de mensaje** que dice `No existe la base de datos: …` (sin consola no hay donde imprimir) | |

Con `py -m ui` (sin la `w`) el mensaje de F10 sale en la consola y el programa termina con código 2.

## Parte G: la base de datos real en `C:\ProgramData` (3 minutos)

El servicio guardará `eventos.db` en `C:\ProgramData\CapturadorEventos\`. Esta parte comprueba que un usuario **normal** (sin ser administrador) puede crear esa carpeta y esa base:

```powershell
py -c "from comun.repositorio import Repositorio, ruta_por_defecto; print(ruta_por_defecto()); r = Repositorio(); print('ok', len(r.listar_perifericos()), 'periféricos'); r.cerrar()"
```

| # | Qué mirar | Resultado esperado | ¿Pasó? |
|---|---|---|---|
| G1 | La salida del comando | Primero `C:\ProgramData\CapturadorEventos\eventos.db` y luego `ok 0 periféricos`, sin errores de permisos | |
| G2 | El archivo | `eventos.db` existe en esa carpeta. Puedes borrar la carpeta `CapturadorEventos` al terminar | |
| G3 | Ejecuta el comando otra vez | Sigue funcionando y dice `ok 0 periféricos` (abrir una base que ya existe no falla) | |

Si G1 falla con `PermissionError`, escribe en el reporte con qué usuario lo ejecutaste: habrá que decidir si la instalación crea la carpeta con permisos para todos los usuarios.

## Reporte de la prueba

Escribe en la conversación del equipo, o en un comentario del pull request:

1. La versión de Windows (por ejemplo, Windows 11 23H2) y el modelo del teclado y del mouse.
2. La tabla de las partes A, B y C con "sí" o "no" en cada fila. Si hiciste las partes E, F y G, también sus tablas y el número de pruebas que pasaron en E1.
3. El bloque `Resultado de la prueba` de la parte B, copiado tal cual. Ese bloque **no** contiene teclas.
4. Cualquier cosa que haya sorprendido: una ventana que apareció, una tecla con nombre raro (por ejemplo `VK_E5`), un dispositivo con `0000`, etc.

## Qué no cubre esta guía

- El nombre del producto (`nombre`) todavía no se envía.
- El inicio automático con el Programador de tareas (RF21) se probará en el Sprint 6.
- Si dos teclados están conectados a la vez, el filtro de repetición es común a los dos. Es una simplificación conocida.
