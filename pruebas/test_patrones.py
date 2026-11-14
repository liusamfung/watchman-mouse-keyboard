"""Pruebas de los patrones de uso (RF15).

Con qué datos: matrices y fechas inventadas de noviembre de 2026. Comprueban: hora pico y día más activo con
la suma correcta, empates (se devuelve el primero), matriz vacía (None), tramos de tres horas, una pausa que
parte un tramo en dos, una pausa de exactamente 5 minutos que no corta, rachas cortas que se descartan,
fechas desordenadas, lista vacía y fecha inválida. No usan la base de datos ni el reloj real.

Se relaciona con: usa analisis/patrones.py · lo ejecuta pytest.
"""

from datetime import datetime, timedelta

import pytest

from analisis.patrones import Tramo, dia_mas_activo, hora_pico, tramos_sin_pausa


def matriz_vacia() -> list[list[int]]:
    """Una matriz de 7 × 24 de ceros."""
    return [[0] * 24 for _ in range(7)]


def serie(inicio: datetime, cada_min: int, cantidad: int) -> list[str]:
    """Fechas ISO a intervalos fijos, para armar rachas de prueba."""
    return [(inicio + timedelta(minutes=cada_min * i)).isoformat(timespec="seconds") for i in range(cantidad)]


def test_matriz_vacia_no_tiene_hora_pico_ni_dia() -> None:
    assert hora_pico(matriz_vacia()) is None
    assert dia_mas_activo(matriz_vacia()) is None


def test_hora_pico_suma_todos_los_dias() -> None:
    matriz = matriz_vacia()
    matriz[0][9] = 5   # lunes, 9 h
    matriz[3][9] = 4   # jueves, 9 h → total de las 9 h: 9
    matriz[1][14] = 8  # martes, 14 h → total de las 14 h: 8
    assert hora_pico(matriz) == 9


def test_hora_pico_empate_devuelve_la_mas_temprana() -> None:
    matriz = matriz_vacia()
    matriz[0][3] = 6
    matriz[0][10] = 6
    assert hora_pico(matriz) == 3


def test_dia_mas_activo_suma_todas_las_horas() -> None:
    matriz = matriz_vacia()
    matriz[2][8] = 3
    matriz[2][17] = 4   # miércoles: 7 en total
    matriz[5][12] = 6   # sábado: 6
    assert dia_mas_activo(matriz) == 2


def test_dia_empate_devuelve_el_mas_cercano_al_lunes() -> None:
    matriz = matriz_vacia()
    matriz[2][0] = 5
    matriz[5][0] = 5
    assert dia_mas_activo(matriz) == 2


def test_tramo_de_tres_horas() -> None:
    # Eventos cada 5 minutos desde las 08:00 hasta las 11:00 (37 eventos seguidos, sin huecos mayores de 5 min).
    horas = serie(datetime(2026, 11, 2, 8, 0), cada_min=5, cantidad=37)
    assert tramos_sin_pausa(horas) == [Tramo("2026-11-02T08:00:00", "2026-11-02T11:00:00", 180)]


def test_pausa_parte_el_tramo_en_dos() -> None:
    # Dos bloques de dos horas separados por una pausa de 40 minutos.
    primero = serie(datetime(2026, 11, 2, 8, 0), cada_min=5, cantidad=25)    # 08:00 a 10:00
    segundo = serie(datetime(2026, 11, 2, 10, 40), cada_min=5, cantidad=25)  # 10:40 a 12:40
    tramos = tramos_sin_pausa(primero + segundo)
    assert len(tramos) == 2
    assert tramos[0].minutos == 120
    assert tramos[1].minutos == 120


def test_hueco_de_exactamente_cinco_minutos_no_corta() -> None:
    # Eventos cada 5 minutos: el hueco es igual a la pausa máxima, así que sigue dentro del tramo.
    horas = serie(datetime(2026, 11, 2, 8, 0), cada_min=5, cantidad=25)  # 08:00 a 10:00
    assert tramos_sin_pausa(horas) == [Tramo("2026-11-02T08:00:00", "2026-11-02T10:00:00", 120)]


def test_racha_corta_se_descarta() -> None:
    horas = serie(datetime(2026, 11, 2, 8, 0), cada_min=5, cantidad=7)  # solo 30 minutos
    assert tramos_sin_pausa(horas) == []


def test_horas_desordenadas_dan_el_mismo_resultado() -> None:
    horas = serie(datetime(2026, 11, 2, 8, 0), cada_min=5, cantidad=37)
    desordenadas = list(reversed(horas))
    assert tramos_sin_pausa(desordenadas) == tramos_sin_pausa(horas)


def test_lista_vacia_no_da_tramos() -> None:
    assert tramos_sin_pausa([]) == []


def test_fecha_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        _ = tramos_sin_pausa(["2026-11-02T25:00:00"])  # la hora 25 no existe
