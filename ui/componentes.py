"""Widgets compartidos por las pantallas. Por ahora, la tabla (`Tabla`), que usan casi todas.

Cómo funciona: `Tabla` es un `ttk.Treeview` con barra de desplazamiento y encabezados ya configurados. Se le pasan las columnas
al crearla y las filas (como texto ya formateado) con `llenar`. Una fila puede llevar un identificador (por ejemplo, el id del
periférico) para saber cuál eligió la persona, y una etiqueta de color (`ETIQUETA_ALERTA`, `ETIQUETA_RETIRADO`).

Se relaciona con: usa `tkinter.ttk` y los colores de `ui/estilo.py` · la usan las pantallas de `ui/pantallas/` y la prueban
`pruebas/test_ui_aplicacion.py`. Si una pantalla necesita otro widget compartido, se pide en su issue: este archivo lo cambia solo
quien mantiene la base de la interfaz, para que no choquen los pull requests.
"""
import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from tkinter import ttk
from typing import Literal

from ui.estilo import FONDO_ALERTA, ROJO, TEXTO_RETIRADO

ETIQUETA_ALERTA = "alerta"  # fila con fondo rosado y letra roja: un periférico con una alerta pendiente
ETIQUETA_RETIRADO = "retirado"  # fila con letra gris: un periférico retirado


@dataclass(frozen=True, slots=True)
class Columna:
    """Una columna de la tabla: su identificador interno, el título del encabezado y su ancho en píxeles."""

    id: str
    titulo: str
    ancho: int = 120
    ancla: Literal["w", "center", "e"] = "w"  # alineación del texto: izquierda, centro o derecha (para números)


@dataclass(frozen=True, slots=True)
class FilaDeTabla:
    """Una fila: los textos (uno por columna), un identificador opcional y una etiqueta de color opcional."""

    valores: tuple[str, ...]
    id: str | None = None
    etiqueta: str | None = None


class Tabla(ttk.Frame):
    """Una tabla de solo lectura con barra de desplazamiento. Una fila se elige con un clic."""

    def __init__(self, padre: tk.Misc, columnas: Sequence[Columna], alto: int = 8,
                 al_elegir: Callable[[str | None], None] | None = None) -> None:
        """Crea la tabla.

        columnas: las columnas, de izquierda a derecha.
        alto: cuántas filas se ven a la vez (si hay más, aparece la barra de desplazamiento).
        al_elegir: se llama con el identificador de la fila elegida, o con None si ya no hay ninguna elegida.
        """
        super().__init__(padre)
        self._columnas: tuple[Columna, ...] = tuple(columnas)
        self._al_elegir: Callable[[str | None], None] | None = al_elegir
        self.arbol: ttk.Treeview = ttk.Treeview(
            self, columns=[c.id for c in self._columnas], show="headings", selectmode="browse", height=alto
        )
        for columna in self._columnas:
            self.arbol.heading(columna.id, text=columna.titulo)
            self.arbol.column(columna.id, width=columna.ancho, anchor=columna.ancla)
        self.arbol.tag_configure(ETIQUETA_ALERTA, background=FONDO_ALERTA, foreground=ROJO)
        self.arbol.tag_configure(ETIQUETA_RETIRADO, foreground=TEXTO_RETIRADO)
        # Nota: el stub de Tk de `yview` está sobrecargado y basedpyright no lo reconoce como una función; por eso el comentario de abajo.
        barra =ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        self.arbol.configure(yscrollcommand=barra.set)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        _ = self.arbol.bind("<<TreeviewSelect>>", self._avisar_eleccion)

    def llenar(self, filas: Iterable[FilaDeTabla]) -> None:
        """Reemplaza todas las filas por `filas`. Lanza ValueError si una fila no tiene tantos valores como columnas."""
        self.limpiar()
        for fila in filas:
            if len(fila.valores) != len(self._columnas):
                raise ValueError(f"la fila tiene {len(fila.valores)} valores y la tabla {len(self._columnas)} columnas")
            _ = self.arbol.insert("", "end", iid=fila.id, values=fila.valores, tags=(fila.etiqueta,) if fila.etiqueta else ())

    def limpiar(self) -> None:
        """Borra todas las filas."""
        self.arbol.delete(*self.arbol.get_children())

    def elegida(self) -> str | None:
        """El identificador de la fila elegida, o None si no hay ninguna (o si la fila elegida no tiene identificador)."""
        elegidas = self.arbol.selection()
        return str(elegidas[0]) if elegidas else None

    def cantidad(self) -> int:
        """Cuántas filas tiene la tabla."""
        return len(self.arbol.get_children())

    def _avisar_eleccion(self, _evento: object) -> None:
        """Pasa la elección de la fila a `al_elegir`, si se pidió."""
        if self._al_elegir is not None:
            self._al_elegir(self.elegida())
