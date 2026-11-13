"""Pruebas de la ventana principal de la interfaz, abriendo Tk de verdad (sin que la ventana llegue a verse).

Con qué datos: la base de ejemplo (`pruebas/base_de_ejemplo.py`, fecha final fija 2026-11-12), una base vacía y unas pantallas falsas
que anotan cuándo se las crea y se las muestra. Comprueba: que la ventana abre en el panel principal con el equipo y la sesión en
el encabezado, que se puede ir a las 8 pantallas, el menú de 7 botones con el resaltado de la pantalla actual (y de su "padre"
en el detalle del periférico), que los parámetros de `ir_a` llegan a la pantalla de destino, que una pantalla que falla no tumba la
ventana, y la tabla compartida (`Tabla`).

Estas pruebas necesitan Tk y una pantalla donde abrir la ventana: si Python no trae Tk (por ejemplo, el Python de Homebrew sin
`python-tk`) o no hay pantalla (un servidor sin escritorio), se omiten en vez de fallar. En Windows, con el Python de python.org,
corren siempre.

Se relaciona con: usa `ui/aplicacion.py`, `ui/pantalla_base.py`, `ui/componentes.py`, `ui/registro.py` y
`pruebas/base_de_ejemplo.py` · lo ejecuta pytest.
"""
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import ClassVar, override

import pytest

try:
    import tkinter as tk
except ImportError:  # un Python compilado sin Tk (por ejemplo, el de Homebrew sin `python-tk`): se omite todo el archivo
    pytest.skip("este Python no trae Tk", allow_module_level=True)

from comun.repositorio import Repositorio
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from ui.aplicacion import Aplicacion
from ui.componentes import Columna, FilaDeTabla, Tabla
from ui.pantalla_base import Pantalla
from ui.registro import PANTALLAS

# Lo que hicieron las pantallas falsas: (qué pasó, clave de la pantalla, parámetros).
BITACORA: list[tuple[str, str, dict[str, object]]] = []
FALLOS: list[tuple[str, Exception]] = []


class PantallaFalsaA(Pantalla):
    """Una pantalla de prueba que anota cuándo se la construye y cuándo se la muestra."""

    TITULO: ClassVar[str] = "Pantalla A"
    SUBTITULO: ClassVar[str] = "La primera"

    @override
    def construir(self) -> None:
        BITACORA.append(("construir", "a", {}))

    @override
    def al_mostrar(self, **parametros: object) -> None:
        BITACORA.append(("mostrar", "a", parametros))


class PantallaFalsaB(Pantalla):
    """Una pantalla de prueba sin botón en el menú: resalta a la A, como el detalle de un periférico."""

    TITULO: ClassVar[str] = "Pantalla B"
    SUBTITULO: ClassVar[str] = "La segunda"
    MENU_PADRE: ClassVar[str | None] = "a"

    @override
    def construir(self) -> None:
        BITACORA.append(("construir", "b", {}))

    @override
    def al_mostrar(self, **parametros: object) -> None:
        BITACORA.append(("mostrar", "b", parametros))


class PantallaQueFallaAlConstruir(Pantalla):
    """Una pantalla de prueba rota: lanza un error al dibujarse."""

    TITULO: ClassVar[str] = "Rota"

    @override
    def construir(self) -> None:
        raise RuntimeError("no se pudo dibujar")


class PantallaQueFallaAlMostrar(Pantalla):
    """Una pantalla de prueba que se dibuja bien pero lanza un error al pedir sus datos."""

    TITULO: ClassVar[str] = "Sin datos"

    @override
    def al_mostrar(self, **parametros: object) -> None:
        _ = parametros
        raise RuntimeError("no se pudieron leer los datos")


@pytest.fixture(scope="module")
def ruta_ejemplo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Una base de ejemplo creada una sola vez para todas las pruebas del archivo (solo se lee)."""
    ruta = tmp_path_factory.mktemp("interfaz") / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, date(2026, 11, 12), 21, 1)
    return ruta


def _abrir(repo: Repositorio, ruta: Path, **opciones: object) -> Aplicacion:
    """Crea la ventana y la oculta enseguida. Si no se puede abrir Tk (sin pantalla), omite la prueba."""
    BITACORA.clear()
    FALLOS.clear()
    try:
        ventana = Aplicacion(repo, ruta, al_fallar=lambda titulo, error: FALLOS.append((titulo, error)), **opciones)  # pyright: ignore[reportArgumentType]
    except tk.TclError as error:
        pytest.skip(f"no se pudo abrir una ventana de Tk: {error}")
    _ = ventana.withdraw()
    return ventana


@pytest.fixture
def ventana(ruta_ejemplo: Path) -> Iterator[Aplicacion]:
    """La ventana real sobre la base de ejemplo, oculta, que se destruye al terminar la prueba."""
    with Repositorio(ruta_ejemplo) as repo:
        aplicacion = _abrir(repo, ruta_ejemplo)
        yield aplicacion
        aplicacion.destroy()


@pytest.fixture
def ventana_falsa(tmp_path: Path) -> Iterator[Aplicacion]:
    """Una ventana con las pantallas falsas A y B sobre una base vacía."""
    ruta = tmp_path / "vacia.db"
    with Repositorio(ruta) as repo:
        aplicacion = _abrir(repo, ruta, pantallas={"a": PantallaFalsaA, "b": PantallaFalsaB}, orden_del_menu=("a",))
        yield aplicacion
        aplicacion.destroy()


def test_abre_en_el_panel_principal_con_el_equipo_y_la_sesion_en_el_encabezado(ventana: Aplicacion) -> None:
    equipo, sesion = ventana.encabezado

    assert ventana.clave_actual == "p01" and ventana.titulo_mostrado == "Panel principal"
    assert equipo == "Equipo: PC-EJEMPLO-01"
    assert sesion.startswith("Sesión iniciada ") and sesion.endswith(" a. m.")   # la última sesión del ejemplo está en curso


def test_con_una_base_vacia_el_encabezado_lo_dice_sin_fallar(tmp_path: Path) -> None:
    with Repositorio(tmp_path / "vacia.db") as repo:
        aplicacion = _abrir(repo, tmp_path / "vacia.db")
        try:
            assert aplicacion.encabezado == ("Equipo: sin registrar", "Todavía no hay sesiones")
        finally:
            aplicacion.destroy()


def test_se_puede_ir_a_las_ocho_pantallas_y_el_titulo_cambia(ventana: Aplicacion) -> None:
    for clave, clase in PANTALLAS.items():
        ventana.mostrar(clave)
        ventana.update_idletasks()

        assert ventana.clave_actual == clave
        assert ventana.titulo_mostrado == clase.TITULO
        assert ventana.pantalla(clave) is not None
    assert FALLOS == []


def test_el_menu_tiene_siete_botones_en_el_orden_de_los_mockups(ventana: Aplicacion) -> None:
    assert [(clave, texto) for clave, texto, _ in ventana.menu] == [
        ("p01", "Panel principal"), ("p02", "Periféricos"), ("p04", "Sesiones"), ("p05", "Análisis de uso"),
        ("p06", "Reportes"), ("p07", "Alertas e incidentes"), ("p08", "Configuración"),
    ]


def test_el_menu_sigue_el_orden_que_se_le_da_y_no_el_alfabetico(tmp_path: Path) -> None:
    ruta = tmp_path / "vacia.db"
    with Repositorio(ruta) as repo:
        aplicacion = _abrir(repo, ruta, pantallas={"a": PantallaFalsaA, "b": PantallaFalsaB}, orden_del_menu=("b", "a"))
        try:
            assert [clave for clave, _, _ in aplicacion.menu] == ["b", "a"]
        finally:
            aplicacion.destroy()


def test_el_menu_resalta_la_pantalla_actual_y_el_detalle_resalta_a_su_padre(ventana: Aplicacion) -> None:
    def resaltado() -> list[str]:
        return [clave for clave, _, activo in ventana.menu if activo]

    assert resaltado() == ["p01"]
    ventana.mostrar("p04")
    assert resaltado() == ["p04"]
    ventana.mostrar("p03", id_periferico=1)   # el detalle no tiene botón: se resalta Periféricos
    assert ventana.clave_actual == "p03" and resaltado() == ["p02"]


def test_una_pantalla_que_no_existe_lanza_keyerror(ventana: Aplicacion) -> None:
    with pytest.raises(KeyError, match="p99"):
        ventana.mostrar("p99")


def test_la_pantalla_se_construye_una_vez_y_se_refresca_cada_vez_que_se_muestra(ventana_falsa: Aplicacion) -> None:
    ventana_falsa.mostrar("b")
    ventana_falsa.mostrar("a")
    ventana_falsa.mostrar("b")

    assert [(que, clave) for que, clave, _ in BITACORA].count(("construir", "b")) == 1
    assert [(que, clave) for que, clave, _ in BITACORA if que == "mostrar" and clave == "b"] == [("mostrar", "b")] * 2


def test_los_parametros_de_ir_a_llegan_a_la_pantalla_de_destino(ventana_falsa: Aplicacion) -> None:
    pantalla_a = ventana_falsa.pantalla("a")
    assert pantalla_a is not None

    pantalla_a.contexto.ir_a("b", id_periferico=7, modo="detalle")

    assert ventana_falsa.clave_actual == "b"
    assert BITACORA[-1] == ("mostrar", "b", {"id_periferico": 7, "modo": "detalle"})


def test_entrar_por_el_menu_no_manda_parametros(ventana_falsa: Aplicacion) -> None:
    ventana_falsa.mostrar("b")

    assert BITACORA[-1] == ("mostrar", "b", {})


def test_una_pantalla_que_falla_al_mostrarse_se_avisa_y_la_ventana_sigue(tmp_path: Path) -> None:
    ruta = tmp_path / "vacia.db"
    with Repositorio(ruta) as repo:
        aplicacion = _abrir(repo, ruta, pantallas={"a": PantallaFalsaA, "x": PantallaQueFallaAlMostrar}, orden_del_menu=("a", "x"))
        try:
            aplicacion.mostrar("x")

            assert [(titulo, str(error)) for titulo, error in FALLOS] == [("Sin datos", "no se pudieron leer los datos")]
            assert aplicacion.clave_actual == "x"   # la pantalla se ve, aunque sus datos no cargaron
            aplicacion.mostrar("a")                  # y se puede seguir navegando
            assert aplicacion.clave_actual == "a"
        finally:
            aplicacion.destroy()


def test_una_pantalla_que_falla_al_construirse_se_avisa_y_no_cambia_la_pantalla_actual(tmp_path: Path) -> None:
    ruta = tmp_path / "vacia.db"
    with Repositorio(ruta) as repo:
        aplicacion = _abrir(repo, ruta, pantallas={"a": PantallaFalsaA, "r": PantallaQueFallaAlConstruir}, orden_del_menu=("a", "r"))
        try:
            aplicacion.mostrar("r")

            assert [(titulo, str(error)) for titulo, error in FALLOS] == [("Rota", "no se pudo dibujar")]
            assert aplicacion.clave_actual == "a" and aplicacion.pantalla("r") is None
        finally:
            aplicacion.destroy()


def test_la_barra_de_estado_muestra_el_texto_que_se_le_pone(ventana: Aplicacion) -> None:
    assert ventana.estado == ""

    ventana.establecer_estado("Correo: sin conexión")

    assert ventana.estado == "Correo: sin conexión"


# ---------- La tabla compartida ----------


def _tabla(ventana: Aplicacion, elegidas: list[str | None] | None = None) -> Tabla:
    """Una tabla de dos columnas dentro de la ventana; si se pasa `elegidas`, ahí se anota cada elección."""
    return Tabla(
        ventana, [Columna("tipo", "Tipo", 80), Columna("modelo", "Modelo", 120)], alto=4,
        al_elegir=(lambda iid: elegidas.append(iid)) if elegidas is not None else None,
    )


def test_la_tabla_se_llena_se_limpia_y_cuenta_sus_filas(ventana: Aplicacion) -> None:
    tabla = _tabla(ventana)

    tabla.llenar([FilaDeTabla(("Teclado", "K120"), id="1"), FilaDeTabla(("Mouse", "B100"), id="2", etiqueta="retirado")])
    assert tabla.cantidad() == 2

    tabla.llenar([FilaDeTabla(("Mouse", "B100"))])   # llenar reemplaza lo anterior, no lo acumula
    assert tabla.cantidad() == 1

    tabla.limpiar()
    assert tabla.cantidad() == 0 and tabla.elegida() is None


def test_la_tabla_avisa_cual_fila_se_eligio(ventana: Aplicacion) -> None:
    elegidas: list[str | None] = []
    tabla = _tabla(ventana, elegidas)
    tabla.llenar([FilaDeTabla(("Teclado", "K120"), id="7"), FilaDeTabla(("Mouse", "B100"), id="9")])

    tabla.arbol.selection_set("9")
    ventana.update()   # entrega el evento de selección

    assert tabla.elegida() == "9" and elegidas == ["9"]


def test_una_fila_con_otro_numero_de_valores_que_columnas_se_rechaza(ventana: Aplicacion) -> None:
    tabla = _tabla(ventana)

    with pytest.raises(ValueError, match="columnas"):
        tabla.llenar([FilaDeTabla(("solo uno",))])
