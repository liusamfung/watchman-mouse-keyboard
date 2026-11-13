"""Punto de entrada de la interfaz: `python -m ui` (o `pythonw -m ui`, sin ventana de consola).

Qué hace: abre la base de datos y la ventana principal. La base es la de `ruta_por_defecto()` (en Windows,
`C:\\ProgramData\\CapturadorEventos\\eventos.db`, o la de la variable CAPTURADOR_RUTA_DB); con `--base ruta` se abre otra, por ejemplo la
de ejemplo que crea `python -m pruebas.base_de_ejemplo`.

Pensado para Windows:
- Antes de crear la ventana se declara que el programa soporta pantallas de alta densidad (escala del 125 % o 150 %); sin esto, Windows
  estira la ventana y el texto se ve borroso.
- Con `pythonw` no hay consola: `sys.stderr` es None y un `print` fallaría. Los problemas se muestran en un cuadro de mensaje.

Se relaciona con: usa `ui/aplicacion.py` y `comun/repositorio.py` (`Repositorio`, `ruta_por_defecto`) · se ejecuta desde la carpeta raíz del
repositorio o desde el acceso directo de Soporte TI.
"""
import argparse
import sys
import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import messagebox

from comun.repositorio import Repositorio, ruta_por_defecto
from ui.aplicacion import Aplicacion


class Opciones(argparse.Namespace):
    """Opciones de la línea de comandos, con sus tipos."""

    base: str | None = None


def _activar_pantallas_de_alta_densidad() -> None:
    """En Windows, declara que el programa sabe escalar su ventana (DPI). No hace nada en otros sistemas ni si falla."""
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # 1 = por monitor del sistema; debe ir antes de crear la ventana
        except (AttributeError, OSError):
            pass  # Windows muy antiguo: la ventana se verá sin escalar, pero funciona


def _informar(texto: str) -> None:
    """Muestra un problema. Con consola va a stderr; sin consola (`pythonw`) va a un cuadro de mensaje, porque `print` fallaría."""
    if sys.stderr is not None:
        print(texto, file=sys.stderr)
        return
    raiz = tk.Tk()
    raiz.withdraw()
    messagebox.showerror("Capturador de eventos", texto)
    raiz.destroy()


def principal(argumentos: Sequence[str] | None = None) -> int:
    """Abre la interfaz. Devuelve 0 al cerrar la ventana, o 2 si `--base` apunta a un archivo que no existe."""
    analizador = argparse.ArgumentParser(prog="python -m ui", description="Interfaz de escritorio para Soporte TI.")
    _ = analizador.add_argument("--base", help="archivo de la base de datos (por defecto, la del sistema o CAPTURADOR_RUTA_DB)")
    opciones = analizador.parse_args(argumentos, namespace=Opciones())
    ruta = Path(opciones.base) if opciones.base else ruta_por_defecto()
    if opciones.base and not ruta.is_file():
        # Con una ruta escrita a mano que no existe, `Repositorio` crearía una base vacía y la persona creería que no hay datos.
        _informar(f"No existe la base de datos: {ruta}")
        return 2
    _activar_pantallas_de_alta_densidad()
    with Repositorio(ruta) as repo:
        ventana = Aplicacion(repo, ruta)
        ventana.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(principal())
