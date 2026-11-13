"""Pantalla P03 · Detalle del periférico (RF23). PANTALLA DE RELLENO: la implementa el issue #24 (Aldair).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P03_DetallePeriferico.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP03(Pantalla):
    """Detalle del periférico: datos de un periférico y sus teclas con mayor desgaste. Se llega desde P02 con `ir_a("p03", id_periferico=...)`."""

    TITULO: ClassVar[str] = "Detalle del periférico"
    SUBTITULO: ClassVar[str] = "Datos del periférico y sus teclas con mayor desgaste."
    MENU_PADRE: ClassVar[str | None] = "p02"  # no tiene botón en el menú: se resalta P02

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(24, "Aldair")
