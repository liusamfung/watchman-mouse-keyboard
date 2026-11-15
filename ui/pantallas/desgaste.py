"""El desgaste de una tecla, un botón o la rueda, tal como lo muestra la pantalla P03 (RF16, RF17).

Va en un archivo propio porque cada archivo de pantalla tiene una sola clase, la de la pantalla (lo comprueba
`pruebas/test_ui_estructura.py`).

Privacidad (RNF4): guarda el total de un elemento, nunca el orden ni la secuencia en que se pulsó. No se imprime ni se escribe en
un log: por eso `elemento` va con `repr=False`, igual que el detalle de una alerta en el repositorio.

Se relaciona con: usa solo la biblioteca estándar · lo usan `ui/pantallas/pantalla_p03.py` (`desgaste_por_elemento` y
`filas_de_desgaste`) y `pruebas/test_pantalla_p03.py`.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Desgaste:
    """El total de una tecla, botón o rueda y su porcentaje frente al límite POR ELEMENTO de su modelo (None si no hay límite)."""

    tipo_conteo: str  # pulsacion_tecla, clic_boton o scroll_paso
    elemento: str = field(repr=False)  # el nombre de la tecla, "izquierdo", "derecho" o "rueda"; repr=False por RNF4
    cantidad: int
    porcentaje: float | None
