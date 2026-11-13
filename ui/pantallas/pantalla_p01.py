"""Pantalla P01 · Panel principal (RF11, RF23). PANTALLA DE RELLENO: la implementa el issue #33 (Liu).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P01_PanelPrincipal.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP01(Pantalla):
    """Panel principal: estado de la captura, botones para iniciar y detener, periféricos del equipo y alertas pendientes."""

    TITULO: ClassVar[str] = "Panel principal"
    SUBTITULO: ClassVar[str] = ""

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(33, "Liu")
