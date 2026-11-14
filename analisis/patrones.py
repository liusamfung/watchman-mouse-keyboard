"""Patrones de uso (RF15): hora pico, día más activo y tramos largos sin pausa.

Todas las funciones reciben los datos ya calculados (la matriz del mapa de calor de `analisis/mapa_de_calor.py`
o la lista de fechas de los eventos) y devuelven el resultado. No leen la base de datos ni el reloj, así que
se pueden probar con datos inventados.

Decisiones:
- Empates: si dos horas (o dos días) tienen el mismo total, se devuelve la primera (la hora más temprana o el
  día más cercano al lunes). Así el resultado es siempre el mismo para los mismos datos.
- Matriz sin eventos: la hora pico y el día más activo devuelven None, porque no hay nada que destacar.
- Tramo: empieza en el primer evento de una racha y termina en el último. Un hueco de exactamente
  `pausa_maxima_min` minutos sigue dentro del tramo; uno mayor lo corta. Solo se devuelven los tramos que
  duran al menos `duracion_minima_min` minutos. Las horas pueden llegar desordenadas: se ordenan antes.

Privacidad (RNF4): solo trabaja con fechas y conteos. Ningún dato de teclas entra en este módulo.

Se relaciona con: usa la biblioteca estándar (dataclasses, datetime) · lo usará la pantalla P05 
(cuando exista) y lo prueba pruebas/test_patrones.py.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class Tramo:
    """Una racha de uso continuo: primera y última fecha (ISO 8601, como llegaron) y su duración en minutos."""

    inicio: str
    fin: str
    minutos: int


def hora_pico(matriz: list[list[int]]) -> int | None:
    """La hora del día (0 … 23) con más eventos, sumando todos los días. None si no hay eventos.

    matriz: 7 filas (días) × 24 columnas (horas), como la que devuelve `calcular_matriz`.
    En un empate devuelve la hora más temprana.
    """
    # zip(*matriz) recorre las columnas: cada columna suma todos los días de esa hora.
    totales = [sum(columna) for columna in zip(*matriz)]
    maximo = max(totales, default=0)
    if maximo == 0:
        return None
    return totales.index(maximo)


def dia_mas_activo(matriz: list[list[int]]) -> int | None:
    """El día de la semana (0 = lunes ... 6 = domingo) con más eventos. None si no hay eventos.

    En un empate devuelve el día más cercano al lunes.
    """
    totales = [sum(fila) for fila in matriz]
    maximo = max(totales, default=0)
    if maximo == 0:
        return None
    return totales.index(maximo)


def tramos_sin_pausa(
    horas: Iterable[str],
    pausa_maxima_min: int = 5,
    duracion_minima_min: int = 120,
) -> list[Tramo]:
    """Rachas de uso continuo: eventos seguidos sin un hueco mayor de `pausa_maxima_min` minutos.

    Devuelve solo las rachas que duran al menos `duracion_minima_min` minutos, en orden cronológico.
    Lanza ValueError si alguna fecha no es válida.
    """
    # Se ordenan por la fecha ya convertida; el texto original se conserva para devolverlo tal cual.
    momentos = sorted(((datetime.fromisoformat(texto), texto) for texto in horas), key=lambda par: par[0])
    if not momentos:
        return []

    pausa = timedelta(minutes=pausa_maxima_min)
    # Primero se separan los eventos en grupos: un hueco mayor que la pausa abre un grupo nuevo.
    grupos: list[list[tuple[datetime, str]]] = [[momentos[0]]]
    for par in momentos[1:]:
        if par[0] - grupos[-1][-1][0] > pausa:
            grupos.append([par])
        else:
            grupos[-1].append(par)

    tramos: list[Tramo] = []
    for grupo in grupos:
        # Se usan segundos enteros de diferencia para que los minutos se redondeen hacia abajo.
        minutos = int((grupo[-1][0] - grupo[0][0]).total_seconds() // 60)
        if minutos >= duracion_minima_min:
            tramos.append(Tramo(inicio=grupo[0][1], fin=grupo[-1][1], minutos=minutos))
    return tramos
