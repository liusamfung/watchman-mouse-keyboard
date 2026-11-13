# Cómo programar una pantalla de la interfaz

Guía para quien implementa una de las pantallas P01 a P08 (RF23). La estructura ya está hecha: la ventana, el menú, el encabezado y la barra de estado. Cada pantalla es **un archivo** en `ui/pantallas/`, así que dos personas nunca editan el mismo archivo.

## Cómo empezar (5 minutos)

1. Crea tu rama desde `main` actualizada: `git switch main && git pull && git switch -c feat/pantalla-p02` (con el nombre de tu pantalla).
2. Crea la base de ejemplo, con datos inventados y sin tocar ninguna base real:
   - macOS o Linux: `.venv/bin/python -m pruebas.base_de_ejemplo ejemplo.db`
   - Windows: `.venv\Scripts\python -m pruebas.base_de_ejemplo ejemplo.db`
3. Abre la interfaz con esa base: `python -m ui --base ejemplo.db` (en Windows, con `.venv\Scripts\python`). Verás tu pantalla con el aviso "en construcción".
4. Abre el mockup de tu pantalla en `docs/mockups/` y el archivo de tu pantalla en `ui/pantallas/`.

> Windows es el sistema de destino. Si en tu PC no abre la ventana, falta Tkinter: instala Python desde python.org con la opción "tcl/tk and IDLE". El Python de Homebrew en macOS necesita `brew install python-tk`.

## Qué archivo es tuyo

| Pantalla | Archivo | Issue |
|---|---|---|
| P01 Panel principal | `ui/pantallas/pantalla_p01.py` | #33 |
| P02 Periféricos | `ui/pantallas/pantalla_p02.py` | #22 (y #23, el diálogo de etiqueta) |
| P03 Detalle del periférico | `ui/pantallas/pantalla_p03.py` | #24 |
| P04 Sesiones | `ui/pantallas/pantalla_p04.py` | #25 |
| P05 Análisis de uso | `ui/pantallas/pantalla_p05.py` | #27 |
| P06 Reportes | `ui/pantallas/pantalla_p06.py` | #28 |
| P07 Alertas e incidentes | `ui/pantallas/pantalla_p07.py` | #26 |
| P08 Configuración | `ui/pantallas/pantalla_p08.py` | #34 |

Si necesitas un archivo nuevo (por ejemplo, un diálogo), créalo en `ui/pantallas/` con otro nombre. **No edites** los archivos compartidos (`ui/aplicacion.py`, `ui/pantalla_base.py`, `ui/registro.py`, `ui/estilo.py`, `ui/formato.py`, `ui/componentes.py`, `comun/repositorio.py`, `pyproject.toml`): si te falta algo, pídelo en tu issue y se agrega aparte, para que los pull requests no choquen.

## La forma de una pantalla

```python
from typing import ClassVar, override

from ui.componentes import Columna, FilaDeTabla, Tabla
from ui.formato import porcentaje
from ui.pantalla_base import Pantalla


class PantallaP02(Pantalla):
    """Periféricos: lista con el desgaste frente al límite."""

    TITULO: ClassVar[str] = "Periféricos"
    SUBTITULO: ClassVar[str] = "Teclados y mouse registrados en este equipo, con su desgaste frente al límite del fabricante."

    @override
    def construir(self) -> None:
        """Dibuja los widgets. Se llama UNA vez, la primera vez que se visita la pantalla."""
        columnas = [Columna("tipo", "Tipo", 100), Columna("modelo", "Modelo", 160), Columna("uso", "Vida útil usada", 140)]
        self.tabla: Tabla = Tabla(self, columnas)   # los widgets que se usan después se guardan en `self`, con su tipo
        self.tabla.pack(fill="both", expand=True)

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Se llama CADA vez que se muestra la pantalla: pide los datos y refresca la tabla."""
        filas = [
            FilaDeTabla((p.tipo, p.modelo, porcentaje(p.porcentaje_maximo)), id=str(p.id))
            for p in self.repo.listar_perifericos()
        ]
        self.tabla.llenar(filas)
```

- `construir` dibuja; `al_mostrar` carga datos. Así, al volver a una pantalla, los datos están al día.
- Los datos se piden con `self.repo` (el `Repositorio`). La tabla de métodos disponibles está en `docs/base-de-datos/README.md`, sección "Qué ofrece el repositorio".
- **Nunca ejecutes SQL ni importes `sqlite3` en `ui/`.** Hay una prueba que lo comprueba.
- Para ir a otra pantalla: `self.contexto.ir_a("p03", id_periferico=5)`. Los parámetros llegan a `al_mostrar` de la pantalla de destino.
- Para avisar algo a la persona usa `tkinter.messagebox`. Si una pantalla lanza un error, la ventana lo muestra y sigue funcionando.

## Lo que ya te dan los archivos compartidos

| Qué | Dónde | Para qué |
|---|---|---|
| `Tabla`, `Columna`, `FilaDeTabla` | `ui/componentes.py` | Una tabla con barra de desplazamiento. `llenar(filas)`, `limpiar()`, `elegida()` y un aviso al elegir una fila. `ETIQUETA_ALERTA` pinta una fila de rojo y `ETIQUETA_RETIRADO` de gris |
| `porcentaje`, `duracion`, `fecha_legible`, `hora_legible`, `fecha_hora_legible` | `ui/formato.py` | Textos en español listos para mostrar: `91 %`, `3 h 12 min`, `05/11/2026`, `08:02 a. m.` |
| Colores y estilos | `ui/estilo.py` | `style="Titulo.TLabel"`, `"Subtitulo.TLabel"`, `"Exito.TLabel"` (verde), `"Peligro.TLabel"` (rojo), `"Suave.TLabel"` (gris) |
| `self.contexto.ruta_db` | `ui/pantalla_base.py` | La ruta de la base abierta |

## Reglas que se revisan en cada pull request

1. **Funciona en Windows.** No uses nada de un solo sistema operativo: rutas con `pathlib.Path`, ninguna fuente escrita a mano (usa los estilos) y solo opciones de Tk 8.6 (la versión de Python 3.12 y 3.13 en Windows). Si tienes un PC con Windows, abre tu pantalla ahí antes del pull request.
2. **Lo que no dibuja va en funciones aparte** (calcular un porcentaje, armar las filas, elegir un color) y se prueba sin abrir una ventana, en `pruebas/test_pantalla_p02.py` (con tu número).
3. **Privacidad (RNF4):** una tecla se muestra solo como total por tecla (por ejemplo, las 10 más gastadas), nunca con orden ni secuencia, y nunca se imprime ni se escribe en un log. En pruebas y ejemplos usa teclas inventadas.
4. **Una pantalla nunca se queda en blanco:** si no hay datos (sin alertas, sin sesiones, un periférico sin límite), muestra un mensaje, no un error.
5. `pytest` y `basedpyright` sin errores ni advertencias. En `ui/` se relajó solo la regla de "resultado sin usar" (los métodos de Tk devuelven valores que nadie usa), así que no hace falta escribir `_ =` delante de `configure`, `grid` o `bind`.
6. Cabecera de archivo con `Se relaciona con:` y docstrings en español (regla "Comentarios en el código" de `CLAUDE.md`). Los archivos de relleno ya traen un ejemplo.
7. Commits `RFn: verbo en infinitivo + qué hace` y `Closes #N` en el pull request.

## Probar sin abrir una ventana

Las pruebas de `pruebas/test_ui_aplicacion.py` abren la ventana de verdad pero oculta, y se omiten solas si Python no trae Tk. Para tu pantalla, lo más rápido es probar las funciones puras. Si quieres probar también tus widgets, usa la ventana de esas pruebas como ejemplo (`Aplicacion(repo, ruta)` y `ventana.mostrar("p02")`).
