"""Pruebas de las funciones de formato de la interfaz (`ui/formato.py`).

Con qué datos: números y fechas inventados (noviembre de 2026) con una hora "de ahora" fija, para que el resultado no dependa del
reloj ni del idioma del sistema. No usa Tk, así que corre igual en Windows, macOS y Linux.

Se relaciona con: usa `ui/formato.py` · lo ejecuta pytest.
"""
from datetime import datetime

import pytest

from ui.formato import SIN_DATO, duracion, fecha_hora_legible, fecha_legible, hora_legible, porcentaje

AHORA = datetime(2026, 11, 12, 15, 0, 0)


@pytest.mark.parametrize(("valor", "esperado"), [
    (91.0, "91 %"), (0.0, "0 %"), (100.0, "100 %"), (125.0, "125 %"),
    (91.4, "91 %"), (91.5, "92 %"), (92.5, "93 %"),   # los .5 suben siempre (el redondeo de Python iría al par)
    (None, SIN_DATO),
])
def test_porcentaje_es_entero_con_espacio_antes_del_signo(valor: float | None, esperado: str) -> None:
    assert porcentaje(valor) == esperado


@pytest.mark.parametrize(("segundos", "esperado"), [
    (0, "0 s"), (45, "45 s"), (59, "59 s"), (60, "1 min"), (47 * 60, "47 min"),
    (3600, "1 h"), (3 * 3600 + 12 * 60, "3 h 12 min"), (5 * 3600, "5 h"), (5 * 3600 + 59, "5 h"),
    (-10, "0 s"),
])
def test_duracion_usa_horas_y_minutos_sin_ceros_de_mas(segundos: int, esperado: str) -> None:
    assert duracion(segundos) == esperado


def test_fecha_legible_es_dia_mes_anio() -> None:
    assert fecha_legible("2026-11-05T08:02:00") == "05/11/2026"
    assert fecha_legible("2026-11-05") == "05/11/2026"
    assert fecha_legible(None) == SIN_DATO and fecha_legible("") == SIN_DATO


@pytest.mark.parametrize(("texto", "esperado"), [
    ("2026-11-12T08:02:00", "08:02 a. m."), ("2026-11-12T00:30:00", "12:30 a. m."),
    ("2026-11-12T12:00:00", "12:00 p. m."), ("2026-11-12T17:10:00", "05:10 p. m."),
    ("2026-11-12T23:59:59.900", "11:59 p. m."),
])
def test_hora_legible_es_de_doce_horas_con_a_m_y_p_m(texto: str, esperado: str) -> None:
    assert hora_legible(texto) == esperado


def test_hora_legible_sin_dato() -> None:
    assert hora_legible(None) == SIN_DATO and hora_legible("") == SIN_DATO


@pytest.mark.parametrize(("texto", "esperado"), [
    ("2026-11-12T08:02:00", "hoy a las 08:02 a. m."),
    ("2026-11-11T17:10:00", "ayer a las 05:10 p. m."),
    ("2026-11-05T08:02:00", "el 05/11/2026 a las 08:02 a. m."),
    ("2026-11-13T09:00:00", "el 13/11/2026 a las 09:00 a. m."),   # el futuro no es ni hoy ni ayer
])
def test_fecha_hora_legible_dice_hoy_ayer_o_la_fecha(texto: str, esperado: str) -> None:
    assert fecha_hora_legible(texto, AHORA) == esperado


def test_fecha_hora_legible_sin_dato_y_con_texto_invalido() -> None:
    assert fecha_hora_legible(None, AHORA) == SIN_DATO
    with pytest.raises(ValueError):
        _ = fecha_hora_legible("no es una fecha", AHORA)
