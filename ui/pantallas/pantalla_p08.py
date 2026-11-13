"""Pantalla P08 · Configuración (RNF9, RNF10, RF17, RF23). PANTALLA DE RELLENO: la implementa el issue #34 (Liu).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P08_Configuracion.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP08(Pantalla):
    """Configuración: límites por modelo, umbrales, destinatarios, servidor de correo y contraseña."""

    TITULO: ClassVar[str] = "Configuración"
    SUBTITULO: ClassVar[str] = "Límites por modelo, umbrales de aviso, destinatarios y servidor de correo."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(34, "Liu")
