"""Pruebas de la pantalla P02 · Periféricos (RF23, RF17) y del diálogo para confirmar la etiqueta (RF18).

Con qué datos: periféricos y alertas armados a mano (`ResumenPeriferico`, `FilaAlerta`) para las funciones de texto, y la base de
ejemplo (`pruebas/base_de_ejemplo.py`, fecha final fija 2026-11-12) para guardar etiquetas con el repositorio de verdad. Las
funciones que se prueban no abren ninguna ventana. Al final, si hay pantalla, se abre la ventana oculta y se revisa la tabla.

Comprueba: los textos de cada columna (modelo, etiqueta "Por confirmar", VID:PID, vida útil del teclado, del mouse y de un modelo
sin límite, estado retirado, con alerta pendiente o enviada), el filtro por tipo, el color de las filas, cuándo se puede
confirmar una etiqueta, y que una etiqueta vacía, con espacios o repetida da un aviso claro y no un error técnico.

Necesitan Tk porque la pantalla lo importa: si Python no trae Tk, se omiten (en Windows, con el Python de python.org, corren siempre).

Se relaciona con: usa `ui/pantallas/pantalla_p02.py`, `ui/pantallas/dialogo_etiqueta.py`, `comun/repositorio.py` y
`pruebas/base_de_ejemplo.py` · lo ejecuta pytest.
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
from ui.componentes import ETIQUETA_ALERTA, ETIQUETA_RETIRADO
from ui.pantallas.dialogo_etiqueta import (
    descripcion_del_periferico,
    guardar_etiqueta,
    normalizar_etiqueta,
    prefijo_sugerido,
    validar_etiqueta,
)
from ui.pantallas.pantalla_p02 import (
    POR_CONFIRMAR,
    SIN_LIMITE,
    PantallaP02,
    alerta_principal,
    etiqueta_de_color,
    filas_de_perifericos,
    filtrar_por_tipo,
    se_puede_confirmar,
    texto_estado,
    texto_etiqueta,
    texto_modelo,
    texto_vid_pid,
    texto_vida_util,
)

FIN_DE_LA_BASE = date(2026, 11, 12)
USO_DEL_MOCKUP: tuple[UsoDeConteo, ...] = (UsoDeConteo("pulsacion_tecla", 412_380, 18_200, 20_000),)  # su tecla más gastada, al 91 %


def periferico(
    id: int = 1,
    tipo: str = "teclado",
    etiqueta: str | None = "TEC-0042",
    activo: bool = True,
    fecha_retiro: str | None = None,
    fabricante: str = "Logitech",
    modelo: str = "K120",
    usos: tuple[UsoDeConteo, ...] = USO_DEL_MOCKUP,
) -> ResumenPeriferico:
    """Un periférico armado a mano. Por defecto, el teclado TEC-0042 del mockup al 91 %."""
    return ResumenPeriferico(
        id=id, id_equipo=1, id_modelo=1, etiqueta=etiqueta,
        estado_asignacion="confirmada" if etiqueta else "por_confirmar",
        activo=activo, fecha_asignacion="2026-10-01T08:00:00", fecha_retiro=fecha_retiro,
        fabricante=fabricante, modelo=modelo, tipo=tipo, vid="046d", pid="c31c", usos=usos,
    )


def alerta(id_periferico: int = 1, umbral: int = 90, estado: str = "pendiente") -> FilaAlerta:
    """Una alerta armada a mano para el periférico `id_periferico`."""
    return FilaAlerta(
        id=umbral, id_periferico=id_periferico, etiqueta=None, modelo="K120", umbral=umbral, estado=estado, detalle=None,
        fecha_creacion="2026-11-10T09:00:00", intentos=1, fecha_ultimo_intento=None, proximo_reintento=None,
        ultimo_error=None, fecha_envio=None if estado == "pendiente" else "2026-11-10T09:01:00",
    )


MOUSE = periferico(
    id=2, tipo="mouse", etiqueta="MOU-0108", modelo="B100",
    usos=(UsoDeConteo("scroll_paso", 1_800, 1_800, 15_000), UsoDeConteo("clic_boton", 4_500, 3_800, 10_000)),
)


# ---------- Textos de las columnas ----------


def test_el_modelo_lleva_el_fabricante() -> None:
    assert texto_modelo(periferico()) == "Logitech K120"


def test_un_modelo_desconocido_se_nombra_sin_repetir() -> None:
    assert texto_modelo(periferico(fabricante="desconocido", modelo="desconocido")) == "Modelo desconocido"


def test_sin_etiqueta_dice_por_confirmar() -> None:
    assert texto_etiqueta(periferico(etiqueta=None)) == POR_CONFIRMAR
    assert texto_etiqueta(periferico()) == "TEC-0042"


def test_el_vid_pid_va_en_mayusculas_y_con_dos_puntos() -> None:
    assert texto_vid_pid(periferico()) == "046D:C31C"


def test_la_vida_util_del_teclado_es_la_de_su_tecla_mas_gastada() -> None:
    # 18 200 de 20 000 por tecla: 91 %, aunque el total del teclado sea mucho mayor que el límite.
    assert texto_vida_util(periferico()) == "91 %"


def test_la_vida_util_del_mouse_muestra_clics_y_scroll_en_ese_orden() -> None:
    assert texto_vida_util(MOUSE) == "38 % clics · 12 % scroll"


def test_un_modelo_sin_limite_no_falla() -> None:
    sin_limite = periferico(usos=(UsoDeConteo("clic_boton", 48, 40, None),))
    assert texto_vida_util(sin_limite) == SIN_LIMITE
    assert texto_vida_util(periferico(usos=())) == SIN_LIMITE


def test_un_retirado_muestra_su_fecha_de_retiro_aunque_tenga_alertas() -> None:
    retirado = periferico(activo=False, fecha_retiro="2026-09-15T18:00:00")
    assert texto_estado(retirado, alerta(umbral=100, estado="enviada")) == "Retirado el 15/09/2026"


def test_el_estado_muestra_la_alerta_o_normal() -> None:
    assert texto_estado(periferico(), alerta(umbral=90)) == "Alerta 90 % pendiente"
    assert texto_estado(periferico(), alerta(umbral=100, estado="enviada")) == "Alerta 100 % enviada"
    assert texto_estado(periferico(), None) == "Normal"


def test_la_alerta_pendiente_manda_sobre_la_enviada_y_luego_el_mayor_umbral() -> None:
    alertas = [alerta(umbral=90, estado="enviada"), alerta(umbral=100, estado="pendiente"), alerta(id_periferico=9, umbral=100)]
    principal = alerta_principal(alertas, 1)
    assert principal is not None and (principal.umbral, principal.estado) == (100, "pendiente")
    enviadas = alerta_principal([alerta(umbral=90, estado="enviada"), alerta(umbral=100, estado="enviada")], 1)
    assert enviadas is not None and enviadas.umbral == 100
    assert alerta_principal(alertas, 5) is None


def test_el_color_de_la_fila() -> None:
    assert etiqueta_de_color(periferico(activo=False), alerta()) == ETIQUETA_RETIRADO
    assert etiqueta_de_color(periferico(), alerta()) == ETIQUETA_ALERTA
    assert etiqueta_de_color(periferico(), alerta(estado="enviada")) is None
    assert etiqueta_de_color(periferico(), None) is None


def test_filtrar_por_tipo() -> None:
    todos = [periferico(), MOUSE]
    assert filtrar_por_tipo(todos, "Todos") == todos
    assert filtrar_por_tipo(todos, "Teclado") == [todos[0]]
    assert filtrar_por_tipo(todos, "Mouse") == [MOUSE]


def test_las_filas_tienen_el_id_del_periferico_y_una_columna_por_dato() -> None:
    filas = filas_de_perifericos([periferico(), MOUSE], [alerta()])
    assert [fila.id for fila in filas] == ["1", "2"]
    assert filas[0].valores == ("Teclado", "Logitech K120", "TEC-0042", "046D:C31C", "91 %", "Alerta 90 % pendiente")
    assert filas[0].etiqueta == ETIQUETA_ALERTA
    assert filas[1].valores[-1] == "Normal"


def test_solo_se_confirma_un_periferico_activo_por_confirmar() -> None:
    assert se_puede_confirmar(periferico(etiqueta=None))
    assert not se_puede_confirmar(periferico())
    assert not se_puede_confirmar(periferico(etiqueta=None, activo=False))
    assert not se_puede_confirmar(None)


# ---------- Diálogo de etiqueta: funciones puras ----------


def test_la_etiqueta_se_normaliza() -> None:
    assert normalizar_etiqueta("  tec-0042 ") == "TEC-0042"


def test_validar_etiqueta() -> None:
    assert validar_etiqueta("TEC-0042") is None
    assert validar_etiqueta("") is not None
    assert validar_etiqueta("TEC 0042") is not None
    assert validar_etiqueta("T" * 21) is not None


def test_el_prefijo_sugerido_depende_del_tipo() -> None:
    assert prefijo_sugerido("teclado") == "TEC-"
    assert prefijo_sugerido("mouse") == "MOU-"
    assert prefijo_sugerido("otro") == ""


def test_la_descripcion_del_dialogo() -> None:
    assert descripcion_del_periferico(periferico()) == "Teclado · Logitech K120 · 046D:C31C"
    desconocido = periferico(fabricante="desconocido", modelo="desconocido")
    assert descripcion_del_periferico(desconocido) == "Teclado · desconocido · 046D:C31C"


# ---------- Diálogo de etiqueta: con el repositorio de verdad ----------


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repositorio]:
    """La base de ejemplo abierta con el repositorio. Trae un teclado y un mouse por confirmar, y TEC-0007 y MOU-0108 confirmados."""
    ruta = tmp_path / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, hasta=FIN_DE_LA_BASE)
    repositorio = Repositorio(ruta)
    try:
        yield repositorio
    finally:
        repositorio.cerrar()


def _por_confirmar(repo: Repositorio, tipo: str) -> ResumenPeriferico:
    """El periférico activo por confirmar de ese tipo en la base de ejemplo."""
    return next(p for p in repo.listar_perifericos() if p.tipo == tipo and se_puede_confirmar(p))


def test_confirmar_la_etiqueta_cambia_el_estado_a_confirmada(repo: Repositorio) -> None:
    teclado = _por_confirmar(repo, "teclado")
    assert guardar_etiqueta(repo, teclado.id, " tec-0042 ") is None
    guardado = repo.obtener_periferico(teclado.id)
    assert guardado is not None
    assert (guardado.etiqueta, guardado.estado_asignacion) == ("TEC-0042", "confirmada")


def test_una_etiqueta_repetida_da_un_aviso_y_no_cambia_nada(repo: Repositorio) -> None:
    teclado = _por_confirmar(repo, "teclado")
    aviso = guardar_etiqueta(repo, teclado.id, "mou-0108")  # ya la tiene el mouse confirmado de la base de ejemplo
    assert aviso is not None and "MOU-0108" in aviso and "otro periférico" in aviso
    sin_cambios = repo.obtener_periferico(teclado.id)
    assert sin_cambios is not None and sin_cambios.estado_asignacion == "por_confirmar"


def test_una_etiqueta_vacia_da_un_aviso(repo: Repositorio) -> None:
    teclado = _por_confirmar(repo, "teclado")
    assert guardar_etiqueta(repo, teclado.id, "   ") is not None


def test_un_periferico_que_no_existe_da_un_aviso(repo: Repositorio) -> None:
    aviso = guardar_etiqueta(repo, 9_999, "TEC-0099")
    assert aviso is not None and "ya no existe" in aviso


# ---------- La pantalla, con la ventana oculta ----------


def test_la_pantalla_lista_los_perifericos_y_filtra(repo: Repositorio, tmp_path: Path) -> None:
    try:
        ventana = Aplicacion(repo, tmp_path / "ejemplo.db", al_fallar=lambda _titulo, error: pytest.fail(str(error)))
    except tk.TclError:
        pytest.skip("no hay pantalla donde abrir la ventana")
    try:
        ventana.withdraw()
        ventana.mostrar("p02")
        pantalla = ventana.pantalla("p02")
        assert isinstance(pantalla, PantallaP02)
        assert pantalla.tabla.cantidad() == len(repo.listar_perifericos())
        pantalla.ver_retirados.set(False)
        pantalla.refrescar()
        assert pantalla.tabla.cantidad() == len(repo.listar_perifericos(incluir_retirados=False))
        pantalla.tipo.set("Mouse")
        pantalla.refrescar()
        assert pantalla.tabla.cantidad() == len([p for p in repo.listar_perifericos(incluir_retirados=False) if p.tipo == "mouse"])
        # Sin fila elegida, los dos botones quedan desactivados.
        assert pantalla.boton_detalle.instate(["disabled"]) and pantalla.boton_confirmar.instate(["disabled"])
    finally:
        ventana.destroy()
