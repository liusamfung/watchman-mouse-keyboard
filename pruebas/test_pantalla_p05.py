
"""Pruebas de P05: filtros, colores, patrones y datos de ejemplo.

Utiliza fechas y registros ficticios para comprobar el mapa de calor.
No almacena secuencias de teclas ni modifica archivos compartidos.

Se relaciona con: usa ui/pantallas/pantalla_p05.py,
comun/repositorio.py y pruebas/base_de_ejemplo.py;
lo ejecuta pytest.
"""

from datetime import date
from pathlib import Path

import pytest

from analisis.mapa_de_calor import calcular_matriz, valor_maximo
from analisis.patrones import Tramo
from comun.repositorio import Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.pantallas.pantalla_p05 import (
    COLORES_CALOR,
    color_de_actividad,
    describir_patrones,
    validar_periodo,
)


@pytest.fixture(scope="module")
def ruta_ejemplo(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """Genera una base SQLite temporal con eventos simulados."""
    ruta = tmp_path_factory.mktemp("p05") / "ejemplo.db"

    _ = crear_base_de_ejemplo(
        ruta,
        date(2026, 11, 14),
        21,
        1,
    )

    return ruta


def test_validar_periodo_incluye_fecha_final() -> None:
    """La fecha Hasta se incluye mediante un límite exclusivo."""
    inicio, fin = validar_periodo(
        "01/11/2026",
        "14/11/2026",
    )

    assert inicio == "2026-11-01"
    assert fin == "2026-11-15"


def test_validar_periodo_acepta_mismo_dia() -> None:
    inicio, fin = validar_periodo(
        "02/11/2026",
        "02/11/2026",
    )

    assert inicio == "2026-11-02"
    assert fin == "2026-11-03"


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("fecha incorrecta", "14/11/2026"),
        ("31/02/2026", "14/11/2026"),
        ("15/11/2026", "01/11/2026"),
    ],
)
def test_rechaza_periodos_invalidos(
    desde: str,
    hasta: str,
) -> None:
    """Rechaza fechas imposibles, textos y rangos invertidos."""
    with pytest.raises(ValueError):
        _ = validar_periodo(desde, hasta)


def test_matriz_sin_datos_usa_color_minimo() -> None:
    """Una matriz sin eventos no provoca divisiones entre cero."""
    assert color_de_actividad(0, 0) == COLORES_CALOR[0]
    assert color_de_actividad(0, 100) == COLORES_CALOR[0]
    assert color_de_actividad(10, 0) == COLORES_CALOR[0]


def test_colores_reflejan_la_intensidad() -> None:
    """La actividad máxima recibe el color más intenso."""
    bajo = color_de_actividad(1, 100)
    medio = color_de_actividad(50, 100)
    alto = color_de_actividad(100, 100)

    assert COLORES_CALOR.index(bajo) < COLORES_CALOR.index(medio)
    assert COLORES_CALOR.index(medio) < COLORES_CALOR.index(alto)
    assert alto == COLORES_CALOR[-1]


def test_matriz_vacia_no_muestra_patrones() -> None:
    """No inventa horas ni días de actividad cuando no hay datos."""
    matriz = calcular_matriz([])

    assert len(matriz) == 7
    assert all(len(fila) == 24 for fila in matriz)
    assert valor_maximo(matriz) == 0

    texto = describir_patrones(matriz, [])

    assert "No se detectaron patrones" in texto


def test_patrones_identifican_hora_y_dia() -> None:
    """Comprueba la interpretación de una matriz conocida."""
    matriz = [[0] * 24 for _ in range(7)]

    # Martes: nueve eventos a las 15 h.
    matriz[1][15] = 9

    # Lunes: tres eventos a las 8 h.
    matriz[0][8] = 3

    texto = describir_patrones(matriz, [])

    assert "15:00 h" in texto
    assert "martes" in texto
    assert "No se detectaron tramos" in texto


def test_patrones_muestran_tramos_prolongados() -> None:
    """Resume la cantidad y duración de los períodos largos."""
    matriz = [[0] * 24 for _ in range(7)]
    matriz[1][15] = 10

    tramos = [
        Tramo(
            "2026-11-03T12:00:00",
            "2026-11-03T14:30:00",
            150,
        ),
    ]

    texto = describir_patrones(matriz, tramos)

    assert "1 detectados" in texto
    assert "150 minutos" in texto


def test_mapa_consulta_datos_de_sqlite(
    ruta_ejemplo: Path,
) -> None:
    """La matriz cuenta exactamente los eventos consultados."""
    with Repositorio(ruta_ejemplo) as repo:
        horas = repo.horas_de_eventos(
            desde="2026-11-01",
            hasta="2026-11-15",
        )

    assert len(horas) > 0

    matriz = calcular_matriz(horas)

    assert len(matriz) == 7
    assert all(len(fila) == 24 for fila in matriz)
    assert sum(sum(fila) for fila in matriz) == len(horas)
    assert valor_maximo(matriz) > 0


def test_rango_sin_eventos_muestra_ceros(
    ruta_ejemplo: Path,
) -> None:
    """El repositorio devuelve una matriz vacía para 2025."""
    with Repositorio(ruta_ejemplo) as repo:
        horas = repo.horas_de_eventos(
            desde="2025-01-01",
            hasta="2025-01-03",
        )

    assert horas == []

    matriz = calcular_matriz(horas)

    assert matriz == [[0] * 24 for _ in range(7)]
    assert valor_maximo(matriz) == 0


def test_filtros_de_teclado_y_mouse(
    ruta_ejemplo: Path,
) -> None:
    """Comprueba que el repositorio permite filtrar dispositivos."""
    with Repositorio(ruta_ejemplo) as repo:
        todos = repo.horas_de_eventos(
            desde="2026-11-01",
            hasta="2026-11-15",
        )

        teclado = repo.horas_de_eventos(
            desde="2026-11-01",
            hasta="2026-11-15",
            tipo_dispositivo="teclado",
        )

        mouse = repo.horas_de_eventos(
            desde="2026-11-01",
            hasta="2026-11-15",
            tipo_dispositivo="mouse",
        )

    assert len(todos) > 0
    assert len(teclado) > 0
    assert len(mouse) > 0

    assert len(teclado) <= len(todos)
    assert len(mouse) <= len(todos)
