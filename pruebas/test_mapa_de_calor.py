"""Pruebas de la matriz del mapa de calor (RF22).

Con qué datos: fechas inventadas de noviembre de 2026. El 2 de noviembre es lunes, así que las fechas
se ubican en días conocidos. Comprueban: un evento, varios en la misma celda, días distintos, lista vacía
(7 × 24 de ceros), fechas con y sin milisegundos, fecha inválida (ValueError), y que la matriz siempre sea
de 7 × 24. No usan la base de datos.

Se relaciona con: usa `analisis/mapa_de_calor.py` · lo ejecuta pytest.
"""

import pytest

from analisis.mapa_de_calor import calcular_matriz, valor_maximo


def test_un_evento_cae_en_su_celda() -> None:
    matriz = calcular_matriz(["2026-11-02T08:15:30"])  # lunes, 8 h
    assert matriz[0][8] == 1
    assert valor_maximo(matriz) == 1


def test_varios_eventos_en_la_misma_celda_se_suman() -> None:
    matriz = calcular_matriz([
        "2026-11-02T08:00:00",
        "2026-11-02T08:30:00",
        "2026-11-02T08:59:59.999",
    ])
    assert matriz[0][8] == 3
    assert valor_maximo(matriz) == 3


def test_dias_distintos_van_en_filas_distintas() -> None:
    matriz = calcular_matriz([
        "2026-11-02T10:00:00",  # lunes
        "2026-11-08T10:00:00",  # domingo
    ])
    assert matriz[0][10] == 1
    assert matriz[6][10] == 1
    assert sum(sum(fila) for fila in matriz) == 2


def test_horas_extremas_caen_en_la_columna_correcta() -> None:
    matriz = calcular_matriz(["2026-11-03T00:00:00", "2026-11-03T23:59:59"])  # martes
    assert matriz[1][0] == 1
    assert matriz[1][23] == 1


def test_acepta_fechas_con_y_sin_milisegundos() -> None:
    matriz = calcular_matriz(["2026-11-02T08:15:30", "2026-11-02T08:15:30.482"])
    assert matriz[0][8] == 2


def test_lista_vacia_da_una_matriz_de_ceros() -> None:
    matriz = calcular_matriz([])
    assert matriz == [[0] * 24 for _ in range(7)]
    assert valor_maximo(matriz) == 0


def test_la_matriz_siempre_es_de_7_por_24() -> None:
    matriz = calcular_matriz(["2026-11-04T12:00:00"])
    assert len(matriz) == 7
    assert all(len(fila) == 24 for fila in matriz)


def test_fecha_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        _ = calcular_matriz(["2026-13-02T08:15:30"])  # mes 13 no existe


def test_texto_que_no_es_fecha_lanza_value_error() -> None:
    with pytest.raises(ValueError):
        _ = calcular_matriz(["hola"])
