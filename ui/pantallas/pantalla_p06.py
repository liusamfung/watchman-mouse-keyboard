"""Pantalla P06 · Reportes (RF14, RF23). PANTALLA DE RELLENO: la implementa el issue #28 (Marcos).

Mientras tanto solo muestra un aviso. Para implementarla: reemplaza `construir` (dibuja los widgets, una sola vez) y `al_mostrar`
(pide los datos al repositorio y los refresca, cada vez que se muestra la pantalla), y borra la llamada a `mostrar_en_construccion`.
Mockup: `docs/mockups/P06_Reportes.png`. Guía para programar una pantalla: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py` (`Pantalla` y `Contexto`) y, por ella, el repositorio · la registra `ui/registro.py`.
"""
from typing import ClassVar, override

from ui.pantalla_base import Pantalla


class PantallaP06(Pantalla):
    """Reportes: opciones del reporte, vista previa y botón para generar el CSV."""

    TITULO: ClassVar[str] = "Reportes"
    SUBTITULO: ClassVar[str] = "Genera archivos CSV con los eventos y las métricas registradas."

    @override
    def construir(self) -> None:
        """Dibuja la pantalla. De momento solo pone el aviso de "en construcción"."""
        self.mostrar_en_construccion(28, "Marcos")
