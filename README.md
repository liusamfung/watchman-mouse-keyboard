# watchman-mouse-keyboard

Capturador y auditor de eventos de entrada (teclado y mouse) para equipos Windows, con control de desgaste de periféricos y alertas a Soporte TI.

Proyecto grupal del curso **Programación de Interfaces** (UTP), Caso 4.

**Equipo:** Liu Sam Fung (Scrum Master), Aldair Lozano, Marcos Matos y José Espinoza.

## ¿Qué hace?

El sistema se instala en cada PC de trabajo y, de forma transparente para el trabajador:

- Detecta qué teclado o mouse generó cada evento, usando su VID/PID.
- Cuenta el desgaste de cada periférico: pulsaciones por tecla, clics por botón y pasos de scroll.
- Envía un correo a Soporte TI cuando un periférico llega al **90 %** y al **100 %** de la vida útil que garantiza el fabricante.
- Guarda eventos y sesiones, genera reportes en CSV y muestra un mapa de calor del uso por hora y día.

El objetivo es prevenir fallos: que el trabajador no se quede sin teclado o mouse, y que Soporte TI no tenga que revisar cada PC a mano.

**Privacidad:** el sistema nunca guarda el orden ni la secuencia de las teclas. Solo almacena contadores agregados por día.

## Cómo ejecutarlo

**Windows es el sistema de destino.** Se puede programar en macOS o Linux, pero lo que depende de Windows (Raw Input, el Administrador de credenciales, el Programador de tareas) y el aspecto real de la interfaz se confirman en un PC con Windows con [`docs/pruebas-en-windows.md`](docs/pruebas-en-windows.md).

Todos los comandos se ejecutan desde la carpeta raíz del repositorio.

### 1. Preparar el entorno (una sola vez)

Hace falta Git y **Python 3.12 o superior**. La interfaz usa Tkinter: en Windows, instala Python desde [python.org](https://www.python.org/downloads/) y deja marcada la opción "tcl/tk and IDLE" (viene marcada por defecto). En macOS con Homebrew, instala también el paquete de Tk de tu versión de Python (por ejemplo `brew install python-tk@3.14`).

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements-desarrollo.txt
```

macOS o Linux:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-desarrollo.txt
```

### 2. Comprobar que todo funciona

Pruebas automáticas y revisión de tipos (en Windows, cambia `.venv/bin/` por `.venv\Scripts\`):

```bash
.venv/bin/python -m pytest pruebas
```

```bash
.venv/bin/basedpyright
```

Debe terminar sin fallos, sin errores y sin advertencias. Algunas pruebas se omiten solas si falta algo: las del capturador de C++ si no hay compilador, y las de la ventana si Python no trae Tk.

### 3. Ver la interfaz con datos de ejemplo

El primer comando crea una base de datos con datos inventados (un teclado retirado, uno al 92 % con una alerta pendiente, un mouse, sesiones, incidentes y eventos); el segundo abre la ventana con esa base. El archivo `ejemplo.db` no se sube a Git.

```bash
.venv/bin/python -m pruebas.base_de_ejemplo ejemplo.db
```

```bash
.venv/bin/python -m ui --base ejemplo.db
```

Sin `--base`, la interfaz abre la base real del sistema (`C:\ProgramData\CapturadorEventos\eventos.db` en Windows, o la que indique la variable de entorno `CAPTURADOR_RUTA_DB`). Para programar una pantalla, lee [`docs/interfaz.md`](docs/interfaz.md).

### 4. Probar la captura sin un teclado real

Eventos inventados con el simulador de Python (cinco líneas JSON):

```bash
.venv/bin/python pruebas/capturador_simulado.py --cantidad 5 --intervalo 0
```

El capturador de C++ en modo simulado, junto con el script de prueba manual que lo lee desde Python y mide el retraso (RNF1). En macOS o Linux se compila con `clang++` o `g++`; en Windows se compila con CMake (ver [`capturador/README.md`](capturador/README.md)) y el programa se llama `captura.exe`:

```bash
mkdir -p capturador/build && clang++ -std=c++17 -Icapturador/src capturador/src/principal.cpp capturador/src/escritor.cpp capturador/src/evento.cpp capturador/src/reglas_de_captura.cpp capturador/src/simulador.cpp -o capturador/build/captura
```

```bash
.venv/bin/python -m pruebas.manual_windows --capturador capturador/build/captura --simulado --segundos 5
```

El resultado debe terminar con `Veredicto (RNF1 < 1000 ms, sin caídas): CUMPLE`. En un PC con Windows, sin `--simulado`, el mismo script prueba el capturador real con tu teclado y tu mouse.

### 5. Lo que todavía no se puede ejecutar

- **El producto completo** (capturar, guardar, avisar por correo y verlo en la ventana): falta el punto de entrada del servicio (`servicio/principal.py`), el evaluador de umbrales y el notificador de correo. Se siguen en los issues del repositorio.
- **Las pantallas** de la interfaz todavía muestran el aviso "en construcción"; cada una se implementa en su propio issue.

## Más documentación

| Para | Lee |
|---|---|
| Entender la arquitectura y las decisiones | [`docs/arquitectura/README.md`](docs/arquitectura/README.md) |
| Los requerimientos RF1–RF23 y RNF1–RNF12 | [`docs/requerimientos.md`](docs/requerimientos.md) |
| La base de datos y lo que ofrece el repositorio | [`docs/base-de-datos/README.md`](docs/base-de-datos/README.md) |
| Programar una pantalla de la interfaz | [`docs/interfaz.md`](docs/interfaz.md) |
| Probar en un PC con Windows | [`docs/pruebas-en-windows.md`](docs/pruebas-en-windows.md) |
| Las reglas del proyecto (idioma, privacidad, comentarios, commits) | [`CLAUDE.md`](CLAUDE.md) |
