"""El registro de pantallas: qué clase es cada pantalla y en qué orden salen en el menú.

Cómo funciona: `PANTALLAS` asocia la clave de cada pantalla (`"p01"` … `"p08"`) con su clase, y `ORDEN_DEL_MENU` dice cuáles tienen
botón en el menú y en qué orden. P03 (detalle del periférico) no está en el menú: se llega a ella desde P02 con
`contexto.ir_a("p03", id_periferico=...)`. El orden del menú sigue los mockups: Sesiones (P04) va tercera.

Quien programa una pantalla NO toca este archivo: cada pantalla ya está registrada con el nombre de su clase (`PantallaP01` …
`PantallaP08`), así que basta con reemplazar el contenido de su propio archivo en `ui/pantallas/`.

Se relaciona con: usa las 8 pantallas de `ui/pantallas/` y `ui/pantalla_base.py` · lo usa `ui/aplicacion.py` y lo revisa
`pruebas/test_ui_estructura.py`.
"""
from ui.pantalla_base import Pantalla
from ui.pantallas.pantalla_p01 import PantallaP01
from ui.pantallas.pantalla_p02 import PantallaP02
from ui.pantallas.pantalla_p03 import PantallaP03
from ui.pantallas.pantalla_p04 import PantallaP04
from ui.pantallas.pantalla_p05 import PantallaP05
from ui.pantallas.pantalla_p06 import PantallaP06
from ui.pantallas.pantalla_p07 import PantallaP07
from ui.pantallas.pantalla_p08 import PantallaP08

PANTALLAS: dict[str, type[Pantalla]] = {
    "p01": PantallaP01,
    "p02": PantallaP02,
    "p03": PantallaP03,
    "p04": PantallaP04,
    "p05": PantallaP05,
    "p06": PantallaP06,
    "p07": PantallaP07,
    "p08": PantallaP08,
}

# Las pantallas con botón en el menú, de arriba hacia abajo. Falta p03 a propósito (ver el docstring del módulo).
ORDEN_DEL_MENU: tuple[str, ...] = ("p01", "p02", "p04", "p05", "p06", "p07", "p08")

PANTALLA_INICIAL = "p01"
