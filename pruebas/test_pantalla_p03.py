"""Pruebas de la pantalla P03 · Detalle del periférico (RF23, RF16, RF17).

Con qué datos: periféricos, alertas y totales por tecla armados a mano, con teclas INVENTADAS (RNF4), para las funciones de texto;
y la base de ejemplo (`pruebas/base_de_ejemplo.py`, fecha final fija 2026-11-12) para abrir la pantalla con la ventana oculta.

Comprueba: el separador de miles, el límite y el total de un teclado, de un mouse y de un modelo sin límite (que no debe fallar),
el estado de las alertas del 90 % y del 100 %, los nombres de teclas y botones, el orden de las teclas por desgaste (y no por el
orden en que se pulsaron), el corte en las 10 más gastadas, el resaltado desde el 90 %, y que la pantalla abre con cada periférico
de la base de ejemplo, sin periférico y con uno que no existe.

Necesitan Tk porque la pantalla lo importa: si Python no trae Tk, se omiten (en Windows, con el Python de python.org, corren siempre).

Se relaciona con: usa `ui/pantallas/pantalla_p03.py`, `comun/repositorio.py` y `pruebas/base_de_ejemplo.py` · lo ejecuta pytest.
"""
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest

try:
    import tkinter as tk
except ImportError:  # un Python compilado sin Tk (por ejemplo, el de Homebrew sin `python-tk`): se omite todo el archivo
    pytest.skip("este Python no trae Tk", allow_module_level=True)

from comun.repositorio import FilaAlerta, Repositorio, ResumenPeriferico, UsoDeConteo
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.aplicacion import Aplicacion
from ui.componentes import ETIQUETA_ALERTA
from ui.formato import SIN_DATO
from ui.pantallas.pantalla_p03 import (
    SIN_PERIFERICO,
    PantallaP03,
    alerta_de,
    datos_del_periferico,
    desgaste_por_elemento,
    filas_de_desgaste,
    id_de_parametro,
    miles,
    nombre_del_elemento,
    resumen,
    texto_alerta,
    texto_limite,
    texto_total,
)

FIN_DE_LA_BASE = date(2026, 11, 12)
USO_DEL_TECLADO: tuple[UsoDeConteo, ...] = (UsoDeConteo("pulsacion_tecla", 412_380, 18_200, 20_000),)
USO_DEL_MOUSE: tuple[UsoDeConteo, ...] = (
    UsoDeConteo("scroll_paso", 4_500, 4_500, 15_000),
    UsoDeConteo("clic_boton", 6_600, 5_500, 10_000),
)


def periferico(
    tipo: str = "teclado", etiqueta: str | None = "TEC-0042", usos: tuple[UsoDeConteo, ...] = USO_DEL_TECLADO,
    activo: bool = True,
) -> ResumenPeriferico:
    """Un periférico armado a mano. Por defecto, el teclado TEC-0042 del mockup."""
    return ResumenPeriferico(
        id=7, id_equipo=1, id_modelo=1, etiqueta=etiqueta, estado_asignacion="confirmada" if etiqueta else "por_confirmar",
        activo=activo, fecha_asignacion="2026-10-01T08:00:00", fecha_retiro=None if activo else "2026-11-04T18:00:00",
        fabricante="Logitech", modelo="K120" if tipo == "teclado" else "B100", tipo=tipo, vid="046D", pid="C31C", usos=usos,
    )


def alerta(umbral: int, estado: str, id_periferico: int = 7) -> FilaAlerta:
    """Una alerta armada a mano."""
    return FilaAlerta(
        id=umbral, id_periferico=id_periferico, etiqueta="TEC-0042", modelo="K120", umbral=umbral, estado=estado, detalle=None,
        fecha_creacion="2026-11-05T09:00:00", intentos=1, fecha_ultimo_intento=None, proximo_reintento=None,
        ultimo_error=None, fecha_envio="2026-11-05T09:01:00" if estado == "enviada" else None,
    )


# ---------- Textos ----------


def test_miles_usa_espacio() -> None:
    assert miles(412_380) == "412 380"
    assert miles(20_000) == "20 000"
    assert miles(48) == "48"


def test_limite_y_total_de_un_teclado() -> None:
    assert texto_limite(periferico()) == "20 000 pulsaciones por tecla"
    assert texto_total(periferico()) == "412 380 pulsaciones"


def test_limite_y_total_de_un_mouse_van_en_orden_clics_y_rueda() -> None:
    mouse = periferico(tipo="mouse", usos=USO_DEL_MOUSE)
    assert texto_limite(mouse) == "10 000 clics por botón\n15 000 pasos de la rueda"
    assert texto_total(mouse) == "6 600 clics\n4 500 pasos de la rueda"


def test_un_modelo_sin_limite_no_falla() -> None:
    desconocido = periferico(tipo="mouse", usos=(UsoDeConteo("clic_boton", 48, 40, None),))
    assert texto_limite(desconocido) == "Sin límite configurado"
    assert texto_total(desconocido) == "48 clics"
    assert texto_total(periferico(usos=())) == "Sin uso registrado"


def test_estado_de_las_alertas() -> None:
    alertas = [alerta(90, "pendiente"), alerta(100, "enviada"), alerta(90, "enviada", id_periferico=8)]
    assert texto_alerta(alerta_de(alertas, 7, 90)) == "pendiente de envío"
    assert texto_alerta(alerta_de(alertas, 7, 100)) == "enviada el 05/11/2026"
    assert texto_alerta(alerta_de(alertas, 9, 90)) == "no generada"


def test_nombres_de_teclas_y_botones() -> None:
    assert nombre_del_elemento("pulsacion_tecla", "Q") == "Q"
    assert nombre_del_elemento("pulsacion_tecla", "ESPACIO") == "Espacio"
    assert nombre_del_elemento("pulsacion_tecla", "F5") == "F5"
    assert nombre_del_elemento("clic_boton", "izquierdo") == "Botón izquierdo"
    assert nombre_del_elemento("scroll_paso", "rueda") == "Rueda"


def test_resumen_y_datos_del_mockup() -> None:
    teclado = periferico()
    assert resumen(teclado) == "Teclado · TEC-0042 · Logitech K120"
    datos = datos_del_periferico(teclado, [alerta(90, "pendiente")], "PC-CONTAB-014")
    assert datos["asignacion"] == "Confirmada" and datos["estado"] == "Activo" and datos["equipo"] == "PC-CONTAB-014"
    assert (datos["alerta_90"], datos["alerta_100"]) == ("pendiente de envío", "no generada")
    assert datos_del_periferico(periferico(etiqueta=None), [], None)["equipo"] == SIN_DATO


# ---------- Teclas con mayor desgaste (teclas inventadas, RNF4) ----------


def test_las_teclas_van_de_la_mas_gastada_a_la_menos_gastada() -> None:
    totales = {"pulsacion_tecla": {"Q": 100, "W": 18_200, "ESPACIO": 14_120}}
    desgastes = desgaste_por_elemento(periferico(), totales)
    assert [d.elemento for d in desgastes] == ["W", "ESPACIO", "Q"]
    assert desgastes[0].porcentaje == pytest.approx(91.0)


def test_solo_se_listan_las_diez_mas_gastadas() -> None:
    totales = {"pulsacion_tecla": {f"F{n}": n * 100 for n in range(1, 13)}}
    desgastes = desgaste_por_elemento(periferico(), totales)
    assert len(desgastes) == 10
    assert desgastes[0].elemento == "F12" and desgastes[-1].elemento == "F3"


def test_en_un_mouse_se_mezclan_botones_y_rueda_por_porcentaje() -> None:
    mouse = periferico(tipo="mouse", usos=USO_DEL_MOUSE)
    totales = {"clic_boton": {"izquierdo": 5_500, "derecho": 1_100}, "scroll_paso": {"rueda": 4_500}}
    # 55 % el izquierdo, 30 % la rueda (4 500 de 15 000) y 11 % el derecho.
    assert [d.elemento for d in desgaste_por_elemento(mouse, totales)] == ["izquierdo", "rueda", "derecho"]


def test_sin_limite_ordena_por_cantidad_y_va_al_final() -> None:
    sin_limite = periferico(tipo="mouse", usos=(UsoDeConteo("clic_boton", 48, 40, None),))
    desgastes = desgaste_por_elemento(sin_limite, {"clic_boton": {"derecho": 8, "izquierdo": 40}})
    assert [d.elemento for d in desgastes] == ["izquierdo", "derecho"]
    assert all(d.porcentaje is None for d in desgastes)


def test_las_filas_resaltan_desde_el_90_por_ciento_y_no_llevan_la_tecla_como_id() -> None:
    totales = {"pulsacion_tecla": {"W": 18_000, "Q": 17_999}}
    filas = filas_de_desgaste(desgaste_por_elemento(periferico(), totales))
    assert filas[0].valores == ("W", "18 000", "90 %") and filas[0].etiqueta == ETIQUETA_ALERTA
    assert filas[1].etiqueta is None
    assert all(fila.id is None for fila in filas)


def test_el_id_del_periferico_que_llega_por_parametro() -> None:
    assert id_de_parametro(5) == 5
    assert id_de_parametro("5") == 5
    assert id_de_parametro(None) is None
    assert id_de_parametro(True) is None
    assert id_de_parametro("cinco") is None


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


def test_la_pantalla_abre_con_cada_periferico_de_la_base_de_ejemplo(ventana: tuple[Aplicacion, Repositorio]) -> None:
    aplicacion, repo = ventana
    for resumen_periferico in repo.listar_perifericos():
        aplicacion.mostrar("p03", id_periferico=resumen_periferico.id)
        pantalla = aplicacion.pantalla("p03")
        assert isinstance(pantalla, PantallaP03)
        assert pantalla.linea.cget("text") == resumen(resumen_periferico)
        assert pantalla.tabla.cantidad() > 0


def test_sin_periferico_o_con_uno_que_no_existe_muestra_un_aviso(ventana: tuple[Aplicacion, Repositorio]) -> None:
    aplicacion, _repo = ventana
    aplicacion.mostrar("p03")
    pantalla = aplicacion.pantalla("p03")
    assert isinstance(pantalla, PantallaP03)
    assert pantalla.linea.cget("text") == SIN_PERIFERICO
    aplicacion.mostrar("p03", id_periferico=9_999)
    assert pantalla.linea.cget("text") == SIN_PERIFERICO and pantalla.tabla.cantidad() == 0
