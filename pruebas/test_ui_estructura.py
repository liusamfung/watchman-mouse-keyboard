"""Pruebas de la estructura de la interfaz: lo que debe cumplirse sin abrir ninguna ventana.

Con qué datos: los propios archivos de `ui/`, leídos como texto y analizados con `ast` (sin importarlos). Por eso corre igual en
Windows, macOS y Linux, incluso donde Tk no está instalado. Comprueba que hay una pantalla por archivo (`pantalla_p01.py` …
`pantalla_p08.py`) con el nombre de clase acordado, que todas están registradas, que cada una declara su título y subtítulo, y
que NINGÚN archivo de la interfaz importa `sqlite3` ni ejecuta SQL: los datos se piden siempre al repositorio.

Se relaciona con: lee `ui/pantallas/*.py`, `ui/registro.py` y el resto de `ui/` · lo ejecuta pytest.
"""
import ast
from pathlib import Path
from typing import cast

import pytest

UI = Path(__file__).parent.parent / "ui"
CLAVES = [f"p{n:02d}" for n in range(1, 9)]
METODOS_DE_SQL = {"execute", "executemany", "executescript", "cursor"}


def _arbol(ruta: Path) -> ast.Module:
    """El árbol de sintaxis de un archivo de la interfaz."""
    return ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))


def _clases(arbol: ast.Module) -> list[ast.ClassDef]:
    """Las clases definidas al nivel del módulo."""
    return [nodo for nodo in arbol.body if isinstance(nodo, ast.ClassDef)]


def _asignaciones_de_clase(clase: ast.ClassDef) -> set[str]:
    """Los nombres que la clase asigna directamente (`TITULO: ClassVar[str] = "…"` o `TITULO = "…"`)."""
    nombres: set[str] = set()
    for nodo in clase.body:
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name):
            nombres.add(nodo.target.id)
        elif isinstance(nodo, ast.Assign):
            nombres.update(destino.id for destino in nodo.targets if isinstance(destino, ast.Name))
    return nombres


@pytest.mark.parametrize("clave", CLAVES)
def test_cada_pantalla_tiene_su_archivo_con_una_clase_que_hereda_de_pantalla(clave: str) -> None:
    ruta = UI / "pantallas" / f"pantalla_{clave}.py"

    assert ruta.is_file(), f"falta {ruta.name}"
    clases = _clases(_arbol(ruta))
    assert [c.name for c in clases] == [f"Pantalla{clave.upper()}"]
    assert [ast.unparse(base) for base in clases[0].bases] == ["Pantalla"]


@pytest.mark.parametrize("clave", CLAVES)
def test_cada_pantalla_declara_su_titulo_y_su_subtitulo(clave: str) -> None:
    clase = _clases(_arbol(UI / "pantallas" / f"pantalla_{clave}.py"))[0]

    assert {"TITULO", "SUBTITULO"} <= _asignaciones_de_clase(clase)


def test_todas_las_pantallas_estan_registradas_con_su_clase() -> None:
    texto = (UI / "registro.py").read_text(encoding="utf-8")

    for clave in CLAVES:
        assert f'"{clave}": Pantalla{clave.upper()}' in texto, clave
        assert f"from ui.pantallas.pantalla_{clave} import Pantalla{clave.upper()}" in texto, clave


def test_el_menu_tiene_siete_botones_y_no_incluye_el_detalle_del_periferico() -> None:
    registro = _arbol(UI / "registro.py")
    orden = cast(tuple[str, ...], next(
        ast.literal_eval(nodo.value) for nodo in registro.body
        if isinstance(nodo, ast.AnnAssign) and isinstance(nodo.target, ast.Name) and nodo.target.id == "ORDEN_DEL_MENU" and nodo.value
    ))

    assert orden == ("p01", "p02", "p04", "p05", "p06", "p07", "p08")   # el orden de los mockups: Sesiones va tercera
    assert "p03" not in orden


def test_el_detalle_del_periferico_resalta_perifericos_en_el_menu() -> None:
    clase = _clases(_arbol(UI / "pantallas" / "pantalla_p03.py"))[0]

    assert "MENU_PADRE" in _asignaciones_de_clase(clase)
    assert 'MENU_PADRE: ClassVar[str | None] = "p02"' in (UI / "pantallas" / "pantalla_p03.py").read_text(encoding="utf-8")


def test_ningun_archivo_de_la_interfaz_importa_sqlite_ni_ejecuta_sql() -> None:
    for ruta in sorted(UI.rglob("*.py")):
        for nodo in ast.walk(_arbol(ruta)):
            if isinstance(nodo, ast.Import):
                assert all(alias.name.split(".")[0] != "sqlite3" for alias in nodo.names), f"{ruta.name} importa sqlite3"
            elif isinstance(nodo, ast.ImportFrom):
                assert (nodo.module or "").split(".")[0] != "sqlite3", f"{ruta.name} importa sqlite3"
            elif isinstance(nodo, ast.Attribute):
                assert nodo.attr not in METODOS_DE_SQL, f"{ruta.name} llama a .{nodo.attr}(): pida los datos al repositorio"


def test_todos_los_archivos_de_la_interfaz_tienen_cabecera_con_su_relacion() -> None:
    sin_relacion = [
        ruta.relative_to(UI.parent).as_posix()
        for ruta in sorted(UI.rglob("*.py"))
        if ruta.name != "__init__.py" and "Se relaciona con:" not in (ast.get_docstring(_arbol(ruta)) or "")
    ]

    assert sin_relacion == []
