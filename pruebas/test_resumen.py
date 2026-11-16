"""Pruebas del resumen de la corrida del servicio (`servicio/resumen.py`).

Con qué datos: la base de ejemplo que genera `pruebas/base_de_ejemplo.py` (fecha final fija, 21 días, semilla 1; cuatro
periféricos, una sesión en curso, alertas e incidentes), un `Reloj` falso con la hora fija 2026-11-12 10:00:00 y, para el servicio,
las claves de `servicio/control.py` escritas a mano. Comprueba que el resumen diga si el servicio está en marcha, caído o nunca
arrancó, que muestre el desgaste de cada periférico, que NO muestre el nombre de ninguna tecla (RNF4) y que el programa de la
terminal avise cuando la base no existe.

Se relaciona con: usa `servicio/resumen.py`, `servicio/control.py`, `pruebas/base_de_ejemplo.py` y `comun/repositorio.py` · lo
ejecuta pytest.
"""
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

from comun.repositorio import Conteo, Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from servicio.control import CLAVE_ESTADO, CLAVE_LATIDO, CLAVE_ORDEN
from servicio.resumen import principal, resumir

AHORA = datetime(2026, 11, 12, 10, 0, 0)
TECLA_INVENTADA = "TECLA_QUE_NO_DEBE_SALIR"


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta de la base de ejemplo, ya creada."""
    ruta = tmp_path / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, date(2026, 11, 12), 21, 1)
    return ruta


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """La base de ejemplo abierta con un repositorio que se cierra al terminar la prueba."""
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


def test_un_servicio_que_nunca_arranco(repo: Repositorio) -> None:
    assert "Servicio: nunca se ha iniciado" in resumir(repo, AHORA)


def test_un_servicio_en_marcha_y_capturando(repo: Repositorio) -> None:
    repo.escribir_configuracion(CLAVE_LATIDO, "2026-11-12T09:59:58")
    repo.escribir_configuracion(CLAVE_ESTADO, "capturando")
    texto = resumir(repo, AHORA)
    assert "Servicio: en marcha · último latido hace 2 s" in texto
    assert "Captura: capturando · orden de la interfaz: iniciar" in texto


def test_un_servicio_cerrado_de_forma_ordenada(repo: Repositorio) -> None:
    repo.escribir_configuracion(CLAVE_LATIDO, "2026-11-12T09:59:58")  # el latido es reciente, pero el servicio ya dijo que se cerró
    repo.escribir_configuracion(CLAVE_ESTADO, "cerrado")
    texto = resumir(repo, AHORA)
    assert "Servicio: cerrado de forma ordenada" in texto
    assert "Captura: detenida" in texto


def test_un_servicio_sin_latido_reciente_se_muestra_detenido(repo: Repositorio) -> None:
    repo.escribir_configuracion(CLAVE_LATIDO, "2026-11-12T09:30:00")
    repo.escribir_configuracion(CLAVE_ESTADO, "capturando")
    repo.escribir_configuracion(CLAVE_ORDEN, "detener")
    texto = resumir(repo, AHORA)
    assert "Servicio: DETENIDO (sin latido reciente) · último latido hace 30 min" in texto
    assert "orden de la interfaz: detener" in texto


def test_muestra_la_sesion_los_perifericos_las_alertas_y_los_incidentes(repo: Repositorio) -> None:
    texto = resumir(repo, AHORA)
    assert "Sesión #" in texto and "en curso" in texto
    assert "Periféricos: 4" in texto
    assert "TEC-0007" in texto and "(retirado)" in texto
    assert "por confirmar" in texto  # un periférico que Soporte TI todavía no etiquetó
    assert "por elemento =" in texto  # el límite es por tecla o botón, no por el total
    assert "Alertas:" in texto and "pendientes" in texto
    assert "Incidentes recientes:" in texto


def test_el_resumen_nunca_nombra_una_tecla(repo: Repositorio) -> None:
    periferico = next(p for p in repo.listar_perifericos() if p.tipo == "teclado" and p.activo)
    repo.sumar_a_contadores([Conteo(periferico.id, "2026-11-12", "pulsacion_tecla", TECLA_INVENTADA, 5)])
    assert TECLA_INVENTADA not in resumir(repo, AHORA)


def test_el_programa_imprime_el_resumen(ruta_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert principal(["--base", str(ruta_db)]) == 0
    assert "Periféricos: 4" in capsys.readouterr().out


def test_el_programa_avisa_si_la_base_no_existe(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    inexistente = tmp_path / "no-existe.db"
    assert principal(["--base", str(inexistente)]) == 2
    assert "No existe la base de datos" in capsys.readouterr().err
    assert not inexistente.exists()  # no se crea una base vacía por error
