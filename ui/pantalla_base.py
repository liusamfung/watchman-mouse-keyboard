"""Clase base de todas las pantallas (P01 a P08) y el contexto que reciben.

Cómo funciona: cada pantalla es una subclase de `Pantalla` en su propio archivo de `ui/pantallas/`. La ventana (`Aplicacion`) crea
la pantalla la primera vez que se visita y llama a `construir` una sola vez (dibuja los widgets); luego, cada vez que se muestra,
llama a `al_mostrar` (que refresca los datos). Así los datos no se quedan viejos al volver a una pantalla.

Reglas para quien programa una pantalla:
- Los datos se piden al repositorio (`self.repo`); una pantalla NUNCA ejecuta SQL ni importa `sqlite3`.
- Para ir a otra pantalla, `self.contexto.ir_a("p03", id_periferico=5)`: los parámetros llegan a `al_mostrar` de la otra.
- Las pantallas no escriben en logs ni imprimen nombres de teclas (RNF4).
- Lo que no dibuja (formatear, calcular porcentajes, armar filas) va en funciones aparte, para probarlo sin abrir una ventana.

Se relaciona con: usa `comun/repositorio.py` (el `Repositorio` del contexto) y `tkinter.ttk` · la heredan las 8 pantallas de
`ui/pantallas/` y la crea `ui/aplicacion.py`.
"""
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk
from typing import ClassVar, Protocol

from comun.repositorio import Repositorio


class Navegacion(Protocol):
    """Lo que hace `contexto.ir_a`: muestra otra pantalla y le pasa parámetros (por ejemplo, `id_periferico=5`)."""

    def __call__(self, clave: str, /, **parametros: object) -> None: ...


@dataclass(frozen=True, slots=True)
class Contexto:
    """Lo que la ventana le entrega a cada pantalla: el repositorio, la ruta de la base y cómo ir a otra pantalla."""

    repo: Repositorio
    ruta_db: Path
    ir_a: Navegacion


class Pantalla(ttk.Frame):
    """Una pantalla de la interfaz. Las subclases definen sus textos y reemplazan `construir` y `al_mostrar`."""

    TITULO: ClassVar[str] = ""  # el título grande de la pantalla y el texto de su botón del menú
    SUBTITULO: ClassVar[str] = ""  # la frase gris bajo el título (puede quedar vacía)
    # Si la pantalla no tiene botón en el menú (por ejemplo, el detalle de un periférico), el menú resalta a su "padre".
    MENU_PADRE: ClassVar[str | None] = None

    def __init__(self, padre: tk.Misc, contexto: Contexto) -> None:
        """Crea el marco de la pantalla y llama a `construir`. Lo llama `Aplicacion` la primera vez que se visita la pantalla."""
        super().__init__(padre)
        self.contexto: Contexto = contexto
        self.construir()

    @property
    def repo(self) -> Repositorio:
        """El repositorio, para pedir datos (nunca SQL). Es el mismo para todas las pantallas."""
        return self.contexto.repo

    def construir(self) -> None:
        """Dibuja los widgets de la pantalla. Se llama UNA vez, al crearla. Las subclases la reemplazan."""

    def al_mostrar(self, **parametros: object) -> None:
        """Se llama CADA vez que se muestra la pantalla: aquí se piden los datos y se refrescan los widgets.

        parametros: los que mandó quien navegó con `contexto.ir_a` (por ejemplo, `id_periferico`); si entró por el menú, vienen vacíos.
        Si lanza una excepción, la ventana muestra un aviso y no se cierra. Las subclases la reemplazan.
        """
        _ = parametros  # la versión base no usa los parámetros; las subclases sí

    def mostrar_en_construccion(self, issue: int, responsable: str) -> None:
        """Pone un aviso de "pantalla en construcción". Las pantallas de relleno lo usan; al implementar la pantalla, se borra."""
        ttk.Label(self, text=f"Pantalla en construcción · issue #{issue} ({responsable})", style="Suave.TLabel").pack(
            anchor="w", pady=20
        )
