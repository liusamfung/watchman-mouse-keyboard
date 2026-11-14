"""Matriz del mapa de calor por día de la semana y hora del día (RF22).

La pantalla P05 dibuja un mapa de calor del uso. Este módulo solo calcula los números: recibe las fechas
de los eventos como texto ISO 8601 y devuelve una tabla de conteos. Marcos la dibuja después en un Canvas.

Formato de la tabla: 7 filas (0 = lunes ... 6 = domingo) por 24 columnas (0 ... 23 horas). Cada celda
cuenta cuántos eventos cayeron en ese día de la semana y a esa hora.

Las fechas pueden venir con o sin milisegundos (`2026-11-02T08:15:30` o `2026-11-02T08:15:30.482`).
`datetime.fromisoformat` acepta las dos formas y lanza ValueError si el texto no es una fecha válida;
ese error se deja pasar tal cual para que quien llame sepa qué dato estaba mal.

Privacidad (RNF4): solo se usan fechas y conteos. Ningún dato de teclas entra en este módulo.

Se relaciona con: usa la biblioteca estándar (`datetime`, `collections.abc`) · lo usará la pantalla P05
(cuando exista) y lo prueba `pruebas/test_mapa_de_calor.py`.
"""

from collections.abc import Iterable
from datetime import datetime

DIAS = 7
HORAS = 24


def calcular_matriz(horas: Iterable[str]) -> list[list[int]]:
    """Cuenta los eventos por día de la semana y hora. Devuelve una matriz de 7 filas × 24 columnas.

    horas: fechas ISO 8601 de cada evento, con o sin milisegundos.
    Lanza ValueError si alguna fecha no es válida.
    """
    matriz: list[list[int]] = [[0] * HORAS for _ in range(DIAS)]
    for texto in horas:
        momento = datetime.fromisoformat(texto)
        # weekday() cuenta desde el lunes (0) hasta el domingo (6), igual que las filas de la matriz.
        matriz[momento.weekday()][momento.hour] += 1
    return matriz


def valor_maximo(matriz: list[list[int]]) -> int:
    """El mayor conteo de la matriz, o 0 si está vacía. Sirve para escalar los colores del mapa."""
    return max((valor for fila in matriz for valor in fila), default=0)
