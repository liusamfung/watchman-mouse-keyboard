"""Pruebas del control de sesión y de la medida de actividad."""
from collections.abc import Iterator
from pathlib import Path

import pytest

from comun.repositorio import Repositorio
from pruebas.ayudas_base import Reloj, consultar, evento_de_prueba, pulsacion
from servicio.sesion import ControlSesion


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    return tmp_path / "eventos.db"


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


@pytest.fixture
def sesion(repo: Repositorio, reloj: Reloj) -> ControlSesion:
    return ControlSesion(repo, repo.obtener_o_crear_equipo("PC-PRUEBA-01"), reloj)


def test_antes_de_abrir_no_hay_id_de_sesion(sesion: ControlSesion) -> None:
    with pytest.raises(RuntimeError, match="no se abrió"):
        _ = sesion.id_sesion


def test_abrir_guarda_el_inicio_con_la_hora_del_reloj(ruta_db: Path, sesion: ControlSesion) -> None:
    identificador = sesion.abrir()
    assert sesion.id_sesion == identificador
    assert consultar(ruta_db, "SELECT inicio, fin FROM sesion WHERE id = ?", (identificador,)) == [
        ("2026-11-02T08:00:00", None)
    ]


def test_varios_eventos_en_el_mismo_segundo_suman_un_solo_segundo(sesion: ControlSesion) -> None:
    sesion.registrar_actividad(pulsacion("A", "2026-11-02T08:00:01.100"))
    sesion.registrar_actividad(pulsacion("B", "2026-11-02T08:00:01.450"))
    sesion.registrar_actividad(pulsacion("C", "2026-11-02T08:00:01.900"))
    assert sesion.segundos_de_actividad() == (1, 0)


def test_las_pausas_no_suman_actividad(sesion: ControlSesion) -> None:
    for hora in ("2026-11-02T08:00:01.000", "2026-11-02T08:00:02.000", "2026-11-02T08:00:03.000",
                 "2026-11-02T08:10:00.000"):   # tras una pausa de casi 10 minutos
        sesion.registrar_actividad(pulsacion("A", hora))
    assert sesion.segundos_de_actividad() == (4, 0)


def test_el_teclado_y_el_mouse_se_miden_por_separado(sesion: ControlSesion) -> None:
    sesion.registrar_actividad(pulsacion("A", "2026-11-02T08:00:01.000"))
    sesion.registrar_actividad(evento_de_prueba("clic_izquierdo", "2026-11-02T08:00:01.200"))
    sesion.registrar_actividad(evento_de_prueba("mouse_movimiento", "2026-11-02T08:00:02.000", x=1, y=2))
    assert sesion.segundos_de_actividad() == (1, 2)


def test_cerrar_guarda_el_fin_el_tipo_de_cierre_y_la_actividad(ruta_db: Path, sesion: ControlSesion, reloj: Reloj) -> None:
    identificador = sesion.abrir()
    sesion.registrar_actividad(pulsacion("A", "2026-11-02T08:00:01.000"))
    sesion.registrar_actividad(evento_de_prueba("clic_izquierdo", "2026-11-02T08:00:05.000"))
    reloj.avanzar(3600)
    sesion.cerrar()
    fila = consultar(ruta_db, "SELECT fin, tipo_cierre, seg_actividad_teclado, seg_actividad_mouse FROM sesion WHERE id = ?",
                     (identificador,))
    assert fila == [("2026-11-02T09:00:00", "normal", 1, 1)]


def test_cerrar_puede_marcar_el_cierre_como_inesperado(ruta_db: Path, sesion: ControlSesion) -> None:
    identificador = sesion.abrir()
    sesion.cerrar("inesperado")
    assert consultar(ruta_db, "SELECT tipo_cierre FROM sesion WHERE id = ?", (identificador,)) == [("inesperado",)]
