
"""Pruebas de P07: alertas, incidentes y estados sin registros.

Usa datos ficticios y una base SQLite temporal.
Comprueba las filas y el funcionamiento de las tablas de Tkinter.

Se relaciona con: usa ui/pantallas/pantalla_p07.py,
comun/repositorio.py y pruebas/base_de_ejemplo.py;
lo ejecuta pytest.
"""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import tkinter as tk
except ImportError:
    pytest.skip("Tkinter no disponible", allow_module_level=True)

from comun.repositorio import Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.aplicacion import Aplicacion
from ui.componentes import ETIQUETA_ALERTA
from ui.pantallas.pantalla_p07 import (
    PantallaP07,
    fila_de_alerta,
    fila_de_incidente,
    mostrar_fecha_hora,
    nombre_de_incidente,
)


@pytest.fixture(scope="module")
def ruta_ejemplo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Crea datos inventados con una fecha fija."""
    ruta = tmp_path_factory.mktemp("p07") / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, date(2026, 11, 12), 21, 1)
    return ruta


def abrir_ventana(repo: Repositorio, ruta: Path) -> Aplicacion:
    """Abre una ventana oculta o salta si no hay entorno gráfico."""
    try:
        ventana = Aplicacion(repo, ruta)
    except tk.TclError as error:
        pytest.skip(f"No se pudo abrir Tkinter: {error}")

    _ = ventana.withdraw()
    return ventana


def test_nombres_y_fechas_son_legibles() -> None:
    assert nombre_de_incidente("error_envio") == "Error de envío"
    assert nombre_de_incidente("caida_proceso") == "Caída del proceso C++"
    assert nombre_de_incidente("evento_invalido") == "Evento inválido"
    assert mostrar_fecha_hora(None) == "—"
    assert mostrar_fecha_hora(
        "2026-11-12T08:02:00"
    ) == "12/11/2026 08:02 a. m."


def test_alertas_muestran_sus_estados(ruta_ejemplo: Path) -> None:
    with Repositorio(ruta_ejemplo) as repo:
        alertas = repo.listar_alertas()

        assert len(alertas) == 3

        pendientes = [a for a in alertas if a.estado == "pendiente"]
        enviadas = [a for a in alertas if a.estado == "enviada"]

        assert len(pendientes) == 1
        assert len(enviadas) == 2

        fila = fila_de_alerta(pendientes[0])

        assert len(fila.valores) == 7
        assert fila.valores[3] == "Pendiente"
        assert fila.valores[4] == "2"
        assert fila.etiqueta == ETIQUETA_ALERTA

        fila_enviada = fila_de_alerta(enviadas[0])
        assert fila_enviada.valores[3] == "Enviada"
        assert fila_enviada.etiqueta is None


def test_incidentes_tienen_cuatro_columnas(
    ruta_ejemplo: Path,
) -> None:
    with Repositorio(ruta_ejemplo) as repo:
        incidentes = repo.incidentes_recientes()
        assert len(incidentes) > 0

        for incidente in incidentes:
            fila = fila_de_incidente(incidente)
            assert len(fila.valores) == 4
            assert fila.id == f"incidente-{incidente.id}"



def test_p07_muestra_datos_y_estado_vacio(
    ruta_ejemplo: Path,
) -> None:
    """Comprueba P07 con registros y con respuestas vacías."""

    with Repositorio(ruta_ejemplo) as repo:
        ventana = abrir_ventana(repo, ruta_ejemplo)

        try:
            # Primer escenario: base con registros.
            ventana.mostrar("p07")
            pantalla = ventana.pantalla("p07")

            assert isinstance(pantalla, PantallaP07)
            assert pantalla.tabla_alertas.cantidad() == 3
            assert pantalla.tabla_incidentes.cantidad() == len(
                repo.incidentes_recientes()
            )

            # Segundo escenario: el repositorio devuelve
            # listas vacías, sin crear otra ventana Tkinter.
            with (
                patch.object(repo, "listar_alertas", return_value=[]),
                patch.object(repo, "incidentes_recientes", return_value=[]),
            ):
                ventana.mostrar("p01")
                ventana.mostrar("p07")

                assert pantalla.tabla_alertas.cantidad() == 0
                assert pantalla.tabla_incidentes.cantidad() == 0

                assert pantalla.aviso_alertas.cget(
                    "text"
                ) == "No hay alertas registradas."

                assert pantalla.aviso_incidentes.cget(
                    "text"
                ) == "No hay incidentes registrados."

            # Tercer escenario: al regresar, los datos
            # originales deben aparecer nuevamente.
            ventana.mostrar("p01")
            ventana.mostrar("p07")

            assert pantalla.tabla_alertas.cantidad() == 3
            assert pantalla.tabla_incidentes.cantidad() == len(
                repo.incidentes_recientes()
            )

        finally:
            ventana.destroy()
