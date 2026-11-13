"""Pantalla P02 · Periféricos (RF23, RF17, RF18). PANTALLA DE RELLENO: la implementa el issue #22 (Aldair).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P02_Perifericos.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP02(Pantalla):
    """Periféricos: lista de periféricos con su desgaste frente al límite, incluidos los retirados (la confirmación de etiqueta es el issue #23)."""

    TITULO: ClassVar[str] = "Periféricos"
    SUBTITULO: ClassVar[str] = "Teclados y mouse registrados en este equipo, con su desgaste frente al límite del fabricante."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(22, "Aldair")
