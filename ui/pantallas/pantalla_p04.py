"""Pantalla P04 · Sesiones (RF12, RF23). PANTALLA DE RELLENO: la implementa el issue #25 (Aldair).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P04_Sesiones.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP04(Pantalla):
    """Sesiones: sesiones del equipo y total del día seleccionado, que es la suma de sus sesiones."""

    TITULO: ClassVar[str] = "Sesiones"
    SUBTITULO: ClassVar[str] = "Desde que se inicia sesión en Windows hasta que se apaga el equipo."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(25, "Aldair")
