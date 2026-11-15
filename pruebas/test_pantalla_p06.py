
"""Pruebas de P06: fechas, consultas y exportación de CSV.

Usa una base SQLite de ejemplo y archivos temporales.
Comprueba los cuatro reportes y que no se creen CSV vacíos.

Se relaciona con: usa ui/pantallas/pantalla_p06.py,
comun/repositorio.py y pruebas/base_de_ejemplo.py;
lo ejecuta pytest.
"""

import csv
from datetime import date
from pathlib import Path

import pytest

from comun.repositorio import Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.pantallas.pantalla_p06 import (
    COLUMNAS,
    consultar_reporte,
    guardar_csv,
    validar_fechas,
)


@pytest.fixture(scope="module")
def ruta_ejemplo(
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    """Genera una base temporal con registros ficticios."""
    ruta = tmp_path_factory.mktemp("p06") / "ejemplo.db"

    _ = crear_base_de_ejemplo(
        ruta,
        date(2026, 11, 12),
        21,
        1,
    )

    return ruta


def test_validar_fechas_incluye_el_ultimo_dia() -> None:
    """Comprueba el rango semiabierto que usa SQLite."""
    inicio, fin = validar_fechas(
        "01/11/2026",
        "12/11/2026",
    )

    assert inicio == "2026-11-01"
    assert fin == "2026-11-13"


def test_validar_fechas_acepta_mismo_dia() -> None:
    inicio, fin = validar_fechas(
        "12/11/2026",
        "12/11/2026",
    )

    assert inicio == "2026-11-12"
    assert fin == "2026-11-13"


@pytest.mark.parametrize(
    ("desde", "hasta"),
    [
        ("fecha incorrecta", "12/11/2026"),
        ("31/02/2026", "12/11/2026"),
        ("15/11/2026", "01/11/2026"),
    ],
)
def test_rechaza_fechas_invalidas(
    desde: str,
    hasta: str,
) -> None:
    with pytest.raises(ValueError):
        _ = validar_fechas(desde, hasta)


@pytest.mark.parametrize(
    "tipo",
    ["eventos", "totales", "contadores", "alertas"],
)
def test_exportar_los_cuatro_reportes(
    ruta_ejemplo: Path,
    tmp_path: Path,
    tipo: str,
) -> None:
    """Compara registros de SQLite con los del CSV generado."""

    with Repositorio(ruta_ejemplo) as repo:
        filas = consultar_reporte(
            repo,
            tipo,
            "2026-10-20",
            "2026-11-13",
        )

    assert len(filas) > 0

    # La estructura del reporte debe coincidir
    # con las columnas de la vista previa.
    assert all(
        len(fila) == len(COLUMNAS[tipo])
        for fila in filas
    )

    destino = tmp_path / f"reporte_{tipo}.csv"

    cantidad = guardar_csv(
        tipo,
        destino,
        filas,
    )

    assert destino.is_file()
    assert cantidad == len(filas)

    with destino.open(
        encoding="utf-8-sig",
        newline="",
    ) as archivo:
        contenido = list(csv.reader(archivo))

    # Una fila de encabezado y las filas exportadas.
    assert len(contenido) == cantidad + 1
    assert len(contenido[0]) == len(COLUMNAS[tipo])


def test_sin_registros_no_crea_csv(
    tmp_path: Path,
) -> None:
    """Impide crear un archivo que solo tenga encabezados."""

    destino = tmp_path / "vacio.csv"

    with pytest.raises(ValueError, match="No hay registros"):
        _ = guardar_csv(
            "totales",
            destino,
            [],
        )

    assert not destino.exists()


def test_base_sin_datos_en_el_rango(
    ruta_ejemplo: Path,
) -> None:
    """Una consulta de fechas sin registros devuelve una lista vacía."""

    with Repositorio(ruta_ejemplo) as repo:
        filas = consultar_reporte(
            repo,
            "totales",
            "2025-01-01",
            "2025-01-03",
        )

    assert filas == []


def test_tipo_de_reporte_invalido(
    ruta_ejemplo: Path,
) -> None:
    """Rechaza tipos de reporte que no existen."""

    with Repositorio(ruta_ejemplo) as repo:
        with pytest.raises(ValueError):
            _ = consultar_reporte(
                repo,
                "desconocido",
                "2026-11-01",
                "2026-11-13",
            )
