"""Pruebas del generador de reportes CSV (RF14).

Con qué datos: filas inventadas escritas en una carpeta temporal (`tmp_path`). No usan la base de datos ni
el repositorio. Comprueban encabezados, filas, tildes, comas y comillas dentro de un valor, valores `None`,
carpetas que no existen, y que el reporte de eventos no tenga columna de tecla (RNF4).

Se relaciona con: usa `reportes/generador.py` · lo ejecuta pytest.
"""

import csv
from pathlib import Path

from reportes.generador import (
    escribir_csv,
    reporte_alertas,
    reporte_contadores,
    reporte_eventos,
    reporte_totales_diarios,
)


def leer(ruta: Path) -> list[list[str]]:
    """Lee el CSV como lo haría Excel: con BOM (utf-8-sig) y separador coma."""
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.reader(archivo))


def test_escribe_encabezado_y_filas(tmp_path: Path) -> None:
    ruta = tmp_path / "prueba.csv"
    cantidad = escribir_csv(ruta, ["a", "b"], [[1, "uno"], [2, "dos"]])
    assert cantidad == 2
    assert leer(ruta) == [["a", "b"], ["1", "uno"], ["2", "dos"]]


def test_conserva_tildes_y_enie(tmp_path: Path) -> None:
    ruta = tmp_path / "tildes.csv"
    _ = escribir_csv(ruta, ["periférico"], [["Teclado de la sesión niño"]])
    assert leer(ruta)[1] == ["Teclado de la sesión niño"]


def test_escribe_el_bom_para_excel(tmp_path: Path) -> None:
    """Sin el BOM, Excel muestra las tildes mal; por eso el archivo empieza con esos tres bytes."""
    ruta = tmp_path / "bom.csv"
    _ = escribir_csv(ruta, ["x"], [])
    assert ruta.read_bytes().startswith(b"\xef\xbb\xbf")


def test_comas_y_comillas_dentro_de_un_valor(tmp_path: Path) -> None:
    ruta = tmp_path / "comas.csv"
    valor = 'Teclado "K120", fila 2'
    _ = escribir_csv(ruta, ["detalle"], [[valor]])
    assert leer(ruta)[1] == [valor]


def test_none_sale_como_celda_vacia(tmp_path: Path) -> None:
    ruta = tmp_path / "vacios.csv"
    _ = escribir_csv(ruta, ["a", "b", "c"], [[1, None, 3]])
    assert leer(ruta)[1] == ["1", "", "3"]


def test_crea_la_carpeta_si_no_existe(tmp_path: Path) -> None:
    ruta = tmp_path / "carpeta" / "nueva" / "reporte.csv"
    _ = escribir_csv(ruta, ["a"], [[1]])
    assert ruta.is_file()


def test_sin_filas_solo_escribe_el_encabezado(tmp_path: Path) -> None:
    ruta = tmp_path / "vacio.csv"
    assert escribir_csv(ruta, ["a", "b"], []) == 0
    assert leer(ruta) == [["a", "b"]]


def test_reporte_eventos_no_tiene_columna_de_tecla(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos.csv"
    filas = [[1, 10, "ID 3", "tecla_presionada", "2026-11-12T08:15:30.120", None, None]]
    assert reporte_eventos(ruta, filas) == 1
    encabezado = leer(ruta)[0]
    assert encabezado == ["id", "sesión", "periférico", "tipo de evento", "fecha y hora", "x", "y"]
    assert "tecla" not in [columna.lower() for columna in encabezado]


def test_reporte_totales_diarios(tmp_path: Path) -> None:
    ruta = tmp_path / "totales.csv"
    filas = [["2026-11-12", "TEC-0007", "pulsacion_tecla", 540]]
    assert reporte_totales_diarios(ruta, filas) == 1
    assert leer(ruta) == [
        ["fecha", "periférico", "tipo de conteo", "total"],
        ["2026-11-12", "TEC-0007", "pulsacion_tecla", "540"],
    ]


def test_reporte_contadores_trae_el_elemento(tmp_path: Path) -> None:
    ruta = tmp_path / "contadores.csv"
    filas = [["2026-11-12", "MOU-0108", "clic_boton", "izquierdo", 230]]
    assert reporte_contadores(ruta, filas) == 1
    assert leer(ruta) == [
        ["fecha", "periférico", "tipo de conteo", "elemento", "cantidad"],
        ["2026-11-12", "MOU-0108", "clic_boton", "izquierdo", "230"],
    ]


def test_reporte_alertas_con_envio_pendiente(tmp_path: Path) -> None:
    ruta = tmp_path / "alertas.csv"
    filas = [["ID 2", 90, "pendiente", 2, "2026-11-10T09:00:00", None]]
    assert reporte_alertas(ruta, filas) == 1
    assert leer(ruta) == [
        ["periférico", "umbral", "estado", "intentos", "creada", "enviada"],
        ["ID 2", "90", "pendiente", "2", "2026-11-10T09:00:00", ""],
    ]
