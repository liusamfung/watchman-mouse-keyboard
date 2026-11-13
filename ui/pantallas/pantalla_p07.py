"""Pantalla P07 · Alertas e incidentes (RF19, RF20, RF9, RF10, RF23). PANTALLA DE RELLENO: la implementa el issue #26 (Marcos).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P07_AlertasIncidentes.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP07(Pantalla):
    """Alertas e incidentes: alertas de desgaste (enviadas o pendientes) e incidentes recientes."""

    TITULO: ClassVar[str] = "Alertas e incidentes"
    SUBTITULO: ClassVar[str] = "Alertas de desgaste enviadas o pendientes, e incidentes recientes."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(26, "Marcos")
