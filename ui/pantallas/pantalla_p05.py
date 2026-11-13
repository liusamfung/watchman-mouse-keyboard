"""Pantalla P05 · Análisis de uso (RF22, RF15, RF23). PANTALLA DE RELLENO: la implementa el issue #27 (Marcos).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P05_Analisis.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP05(Pantalla):
    """Análisis de uso: mapa de calor por día y hora y patrones de uso."""

    TITULO: ClassVar[str] = "Análisis de uso"
    SUBTITULO: ClassVar[str] = "Mapa de calor del uso por día y hora, y patrones detectados."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(27, "Marcos")
