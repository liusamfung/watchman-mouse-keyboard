"""Pruebas de la pantalla P04 · Sesiones (RF12, RF23).

Con qué datos: sesiones armadas a mano (`FilaSesion`) para las funciones puras, y la base de ejemplo (`pruebas/base_de_ejemplo.py`,
fecha final fija 2026-11-12), que trae una sesión en curso y un día con un apagado inesperado, para abrir
la pantalla con la ventana oculta.

Comprueba: que las fechas se leen como dd/mm/aaaa (y una mal escrita da un mensaje claro), el rango por defecto, que el rango
incluye sus dos extremos, que una sesión en curso se muestra "En curso" con el cierre "—" sin fallar, el fin de una sesión que pasó
la medianoche, los nombres del cierre, el título y la nota del total del día, y que en la pantalla el total del día es la suma de
sus sesiones y que el subtítulo ya no dice "se enciende el equipo".

Necesitan Tk porque la pantalla lo importa: si Python no trae Tk, se omiten (en Windows, con el Python de python.org, corren siempre).

Se relaciona con: usa `ui/pantallas/pantalla_p04.py`, `comun/repositorio.py` y `pruebas/base_de_ejemplo.py` · lo ejecuta pytest.
"""
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

try:
    import tkinter as tk
except ImportError:  # un Python compilado sin Tk (por ejemplo, el de Homebrew sin `python-tk`): se omite todo el archivo
    pytest.skip("este Python no trae Tk", allow_module_level=True)

from comun.repositorio import FilaSesion, Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.aplicacion import Aplicacion
from ui.formato import duracion
from ui.pantallas.pantalla_p04 import (
    EN_CURSO,
    NOTA_GENERAL,
    NOTA_INESPERADO,
    PantallaP04,
    dia_de,
    filas_de_sesiones,
    leer_fecha,
    nota_del_dia,
    rango_por_defecto,
    sesiones_del_rango,
    texto_cierre,
    texto_fin,
    titulo_del_total,
)

FIN_DE_LA_BASE = date(2026, 11, 12)


def sesion(id: int, inicio: str, fin: str | None = None, cierre: str | None = None,
           teclado: int = 3_600, mouse: int = 1_800) -> FilaSesion:
    """Una sesión armada a mano. Sin `fin`, está en curso."""
    return FilaSesion(id=id, id_equipo=1, inicio=inicio, fin=fin, tipo_cierre=cierre,
                      seg_actividad_teclado=teclado, seg_actividad_mouse=mouse)


EN_CURSO_HOY = sesion(3, "2026-10-09T08:02:00", teclado=11_520, mouse=10_020)
INESPERADA = sesion(2, "2026-10-06T08:00:00", "2026-10-06T10:42:00", "inesperado")
NORMAL = sesion(1, "2026-10-05T08:03:00", "2026-10-05T17:28:00", "normal")


# ---------- Fechas y rango ----------


def test_leer_fecha_acepta_dd_mm_aaaa_y_iso() -> None:
    assert leer_fecha(" 05/10/2026 ") == date(2026, 10, 5)
    assert leer_fecha("2026-10-05") == date(2026, 10, 5)


def test_una_fecha_mal_escrita_da_un_mensaje_claro() -> None:
    with pytest.raises(ValueError, match="dd/mm/aaaa"):
        _ = leer_fecha("31/02/2026")
    with pytest.raises(ValueError, match="dd/mm/aaaa"):
        _ = leer_fecha("ayer")


def test_el_rango_por_defecto_termina_en_la_sesion_mas_reciente() -> None:
    assert rango_por_defecto([NORMAL, EN_CURSO_HOY], hoy=date(2026, 11, 1), dias=5) == (date(2026, 10, 5), date(2026, 10, 9))


def test_sin_sesiones_el_rango_termina_hoy() -> None:
    assert rango_por_defecto([], hoy=date(2026, 11, 1), dias=14) == (date(2026, 10, 19), date(2026, 11, 1))


def test_el_rango_incluye_sus_dos_extremos() -> None:
    todas = [EN_CURSO_HOY, INESPERADA, NORMAL]
    assert sesiones_del_rango(todas, date(2026, 10, 5), date(2026, 10, 6)) == [INESPERADA, NORMAL]
    assert sesiones_del_rango(todas, date(2026, 10, 7), date(2026, 10, 8)) == []


# ---------- Textos de la tabla ----------


def test_una_sesion_en_curso_no_rompe_la_fila() -> None:
    assert texto_fin(EN_CURSO_HOY) == EN_CURSO
    assert texto_cierre(EN_CURSO_HOY) == "—"
    assert filas_de_sesiones([EN_CURSO_HOY])[0].valores == (
        "09/10/2026", "08:02 a. m.", "En curso", "—", "3 h 12 min", "2 h 47 min",
    )


def test_los_cierres_y_el_fin() -> None:
    assert texto_cierre(INESPERADA) == "Apagado inesperado"
    assert texto_cierre(NORMAL) == "Normal"
    assert texto_fin(INESPERADA) == "10:42 a. m."


def test_una_sesion_que_paso_la_medianoche_muestra_la_fecha_del_fin() -> None:
    nocturna = sesion(9, "2026-10-06T22:00:00", "2026-10-07T01:15:00", "normal")
    assert texto_fin(nocturna) == "07/10/2026 01:15 a. m."
    assert dia_de(nocturna) == date(2026, 10, 6)  # se suma al día en que empezó


def test_las_filas_llevan_el_id_de_la_sesion() -> None:
    assert [fila.id for fila in filas_de_sesiones([INESPERADA, NORMAL])] == ["2", "1"]


def test_titulo_y_nota_del_total() -> None:
    assert titulo_del_total(date(2026, 10, 6), 2) == "Total del día seleccionado (06/10/2026 · 2 sesiones)"
    assert titulo_del_total(date(2026, 10, 5), 1) == "Total del día seleccionado (05/10/2026 · 1 sesión)"
    assert nota_del_dia([INESPERADA]) == NOTA_INESPERADO
    assert nota_del_dia([NORMAL]) == NOTA_GENERAL


# ---------- La pantalla, con la ventana oculta ----------


@pytest.fixture
def ventana(tmp_path: Path) -> Iterator[tuple[Aplicacion, Repositorio]]:
    """La ventana oculta con la base de ejemplo. Un fallo de una pantalla hace fallar la prueba en vez de abrir un aviso."""
    ruta = tmp_path / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, hasta=FIN_DE_LA_BASE)
    repo = Repositorio(ruta)
    try:
        aplicacion = Aplicacion(repo, ruta, al_fallar=lambda _titulo, error: pytest.fail(str(error)))
    except tk.TclError:
        repo.cerrar()
        pytest.skip("no hay pantalla donde abrir la ventana")
    aplicacion.withdraw()
    try:
        yield aplicacion, repo
    finally:
        aplicacion.destroy()
        repo.cerrar()


def test_el_subtitulo_dice_que_la_sesion_empieza_al_iniciar_sesion_en_windows() -> None:
    assert "se inicia sesión en Windows" in PantallaP04.SUBTITULO
    assert "se enciende" not in PantallaP04.SUBTITULO


def test_la_pantalla_muestra_las_sesiones_y_el_total_es_la_suma_del_dia(ventana: tuple[Aplicacion, Repositorio]) -> None:
    aplicacion, repo = ventana
    aplicacion.mostrar("p04")
    pantalla = aplicacion.pantalla("p04")
    assert isinstance(pantalla, PantallaP04)
    assert pantalla.tabla.cantidad() > 0
    assert EN_CURSO in pantalla.tabla.arbol.item(pantalla.tabla.arbol.get_children()[0], "values")  # la sesión en curso va primera

    # El día con el apagado inesperado: su total debe ser la suma de todas las sesiones que empezaron ese día.
    todas = repo.listar_sesiones()
    dia = next(dia_de(s) for s in todas if s.tipo_cierre == "inesperado")
    del_dia = [s for s in todas if dia_de(s) == dia]
    pantalla.mostrar_total(dia)
    assert pantalla.total_teclado.cget("text") == duracion(sum(s.seg_actividad_teclado for s in del_dia))
    assert pantalla.total_mouse.cget("text") == duracion(sum(s.seg_actividad_mouse for s in del_dia))
    assert pantalla.nota.cget("text") == NOTA_INESPERADO


def test_un_rango_sin_sesiones_muestra_un_aviso(ventana: tuple[Aplicacion, Repositorio]) -> None:
    aplicacion, _repo = ventana
    aplicacion.mostrar("p04")
    pantalla = aplicacion.pantalla("p04")
    assert isinstance(pantalla, PantallaP04)
    pantalla.desde.set("01/01/2020")
    pantalla.hasta.set("02/01/2020")
    pantalla.filtrar()
    assert pantalla.tabla.cantidad() == 0
    assert "No hay sesiones" in pantalla.vacia.cget("text")
