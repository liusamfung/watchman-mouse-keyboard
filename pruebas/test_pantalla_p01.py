"""Pruebas de la pantalla P01 · Panel principal (RF11, RF23).

Con qué datos: estados del servicio, periféricos y alertas armados a mano (`EstadoDelServicio`, `ResumenPeriferico`, `FilaAlerta`) para las
funciones de texto, y la base de ejemplo (`pruebas/base_de_ejemplo.py`, fecha final fija 2026-11-12) con una hora falsa para la pantalla
de verdad, abierta oculta. Las funciones no abren ninguna ventana.

Comprueba: lo que dice el estado de la captura en cada combinación de orden, estado y servicio vivo o apagado (incluida la transición
"Deteniendo…" entre que se pulsa el botón y el servicio responde), qué botones se pueden pulsar, las filas de periféricos (una por tipo de
conteo, sin retirados, sin teclas), el tiempo que falta para un reintento, las filas de alertas sin el texto del error, que los botones
escriban la orden en la base, que los datos del día coincidan con el repositorio, que el temporizador se cancele al cerrar y que una base
ocupada no abra cuadros de mensaje.

Necesitan Tk porque la pantalla lo importa: si Python no trae Tk, se omiten (en Windows, con el Python de python.org, corren siempre).

Se relaciona con: usa `ui/pantallas/pantalla_p01.py`, `servicio/control.py`, `comun/repositorio.py` y `pruebas/base_de_ejemplo.py` ·
lo ejecuta pytest.
"""
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pytest

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # un Python compilado sin Tk (por ejemplo, el de Homebrew sin `python-tk`): se omite todo el archivo
    pytest.skip("este Python no trae Tk", allow_module_level=True)

from comun.repositorio import FilaAlerta, Repositorio, ResumenPeriferico, UsoDeConteo
from pruebas.base_de_ejemplo import crear_base_de_ejemplo
from servicio.control import CLAVE_ESTADO, CLAVE_LATIDO, CLAVE_ORDEN, EstadoDelServicio
from ui.aplicacion import Aplicacion
from ui.componentes import ETIQUETA_ALERTA
from ui.pantallas.pantalla_p03 import miles
from ui.pantallas.pantalla_p01 import (
    AVISO_SERVICIO_APAGADO,
    FALLA_DE_LECTURA,
    PantallaP01,
    botones_activos,
    estado_visible,
    filas_de_alertas_pendientes,
    filas_de_perifericos_del_panel,
    texto_de_actividad,
    texto_de_destinatarios,
    texto_del_proceso,
    tiempo_hasta,
)

FIN_DE_LA_BASE = date(2026, 11, 12)
AHORA = datetime(2026, 11, 12, 10, 0, 0)
USO_DEL_MOCKUP: tuple[UsoDeConteo, ...] = (UsoDeConteo("pulsacion_tecla", 412_380, 18_200, 20_000),)  # su tecla más gastada, al 91 %


def texto_de(widget: ttk.Label, opcion: str = "text") -> str:
    """El valor de una opción de un widget (`text`, `style`) como texto. Tk lo devuelve sin tipo, y así queda tipado."""
    return str(cast(object, widget.cget(opcion)))


def servicio(orden: str = "iniciar", estado: str = "capturando", en_marcha: bool = True) -> EstadoDelServicio:
    """Un estado del servicio armado a mano. Por defecto, vivo y capturando con la orden "iniciar"."""
    return EstadoDelServicio(orden, estado, "2026-11-12T09:59:58" if en_marcha else None, en_marcha)


def periferico(
    id: int = 1, tipo: str = "teclado", etiqueta: str | None = "TEC-0042", activo: bool = True, modelo: str = "K120",
    usos: tuple[UsoDeConteo, ...] = USO_DEL_MOCKUP,
) -> ResumenPeriferico:
    """Un periférico armado a mano. Por defecto, el teclado TEC-0042 del mockup al 91 %."""
    return ResumenPeriferico(
        id=id, id_equipo=1, id_modelo=1, etiqueta=etiqueta, estado_asignacion="confirmada" if etiqueta else "por_confirmar",
        activo=activo, fecha_asignacion="2026-10-01T08:00:00", fecha_retiro=None if activo else "2026-09-15T10:00:00",
        fabricante="Logitech", modelo=modelo, tipo=tipo, vid="046D", pid="C31C", usos=usos,
    )


def alerta(id: int = 1, intentos: int = 0, proximo: str | None = None, etiqueta: str | None = "TEC-0042", id_periferico: int = 1) -> FilaAlerta:
    """Una alerta pendiente del 90 % armada a mano."""
    return FilaAlerta(
        id=id, id_periferico=id_periferico, etiqueta=etiqueta, modelo="K120", umbral=90, estado="pendiente",
        detalle="TECLA_INVENTADA 91 %", fecha_creacion="2026-11-12T08:00:00", intentos=intentos,
        fecha_ultimo_intento=None, proximo_reintento=proximo, ultimo_error="sin conexión", fecha_envio=None,
    )


# ---------- El estado de la captura ----------


def test_el_estado_dice_activa_cuando_todo_coincide() -> None:
    assert estado_visible(servicio()) == ("● Captura ACTIVA", "Exito.TLabel")


def test_el_estado_dice_detenida_cuando_se_pidio_y_se_cumplio() -> None:
    assert estado_visible(servicio("detener", "detenida")) == ("● Captura DETENIDA", "Peligro.TLabel")


def test_entre_pulsar_un_boton_y_la_respuesta_del_servicio_se_muestra_la_transicion() -> None:
    assert estado_visible(servicio("detener", "capturando")) == ("● Deteniendo captura…", "Suave.TLabel")
    assert estado_visible(servicio("iniciar", "detenida")) == ("● Iniciando captura…", "Suave.TLabel")


def test_con_el_servicio_apagado_no_se_afirma_nada_sobre_la_captura() -> None:
    # Aunque lo último que dijo fue "capturando", si no hay latido la pantalla no debe mostrar "Captura ACTIVA".
    assert estado_visible(servicio("iniciar", "capturando", en_marcha=False)) == ("● Servicio detenido", "Peligro.TLabel")
    assert texto_del_proceso(servicio(en_marcha=False)) == "servicio apagado"


def test_el_texto_del_proceso() -> None:
    assert texto_del_proceso(servicio()) == "en ejecución"
    assert texto_del_proceso(servicio("detener", "detenida")) == "detenido"


def test_los_botones_se_deciden_por_la_orden_y_no_esperan_al_servicio() -> None:
    assert botones_activos(servicio("iniciar")) == (False, True)  # (iniciar, detener): ya se pidió iniciar, solo tiene sentido detener
    assert botones_activos(servicio("detener")) == (True, False)
    assert botones_activos(servicio("detener", "capturando")) == (True, False)  # no hay que esperar a que el servicio cumpla la orden
    assert botones_activos(servicio("iniciar", en_marcha=False)) == (False, True)  # con el servicio apagado la orden igual se puede dar


def test_el_tiempo_de_actividad_se_escribe_como_en_el_mockup() -> None:
    assert texto_de_actividad(3 * 3600 + 12 * 60, 2 * 3600 + 47 * 60) == "Teclado 3 h 12 min · Mouse 2 h 47 min"
    assert texto_de_actividad(0, 45) == "Teclado 0 s · Mouse 45 s"


# ---------- Periféricos ----------


def test_el_teclado_tiene_una_fila_y_el_mouse_una_por_tipo_de_conteo() -> None:
    mouse = periferico(2, "mouse", "MOU-0108", modelo="B100", usos=(
        UsoDeConteo("scroll_paso", 9_000, 1_800, 15_000),  # llega desordenado a propósito
        UsoDeConteo("clic_boton", 40_000, 3_800, 10_000),
    ))
    filas = filas_de_perifericos_del_panel([periferico(), mouse], [])
    assert [f.valores for f in filas] == [
        ("Teclado", "Logitech K120", "TEC-0042", "91 %", "Normal"),
        ("Mouse · clics", "Logitech B100", "MOU-0108", "38 %", "Normal"),
        ("Mouse · scroll", "Logitech B100", "MOU-0108", "12 %", "Normal"),
    ]
    assert len({f.id for f in filas}) == 3  # cada fila tiene su propio identificador


def test_un_periferico_con_alerta_pendiente_va_en_rojo() -> None:
    (fila,) = filas_de_perifericos_del_panel([periferico()], [alerta()])
    assert fila.valores[4] == "Alerta 90 % pendiente" and fila.etiqueta == ETIQUETA_ALERTA


def test_un_modelo_sin_limite_dice_sin_limite_y_no_falla() -> None:
    (fila,) = filas_de_perifericos_del_panel([periferico(2, "mouse", None, modelo="desconocido", usos=())], [])
    assert fila.valores == ("Mouse", "Modelo desconocido", "Por confirmar", "Sin límite", "Normal")


def test_los_retirados_no_salen_en_el_panel() -> None:
    assert filas_de_perifericos_del_panel([periferico(activo=False)], []) == []


# ---------- Alertas pendientes ----------


@pytest.mark.parametrize(("texto", "esperado"), [
    (None, "—"),
    ("2026-11-12T09:59:00", "ahora"),  # ya pasó
    ("2026-11-12T10:00:30", "en menos de 1 min"),
    ("2026-11-12T10:14:00", "en 14 min"),
    ("2026-11-12T12:05:00", "en 2 h"),
])
def test_cuanto_falta_para_el_reintento(texto: str | None, esperado: str) -> None:
    assert tiempo_hasta(texto, AHORA) == esperado


def test_mas_de_un_dia_se_muestra_como_fecha() -> None:
    assert tiempo_hasta("2026-11-15T10:00:00", AHORA) == "el 15/11/2026 a las 10:00 a. m."


def test_las_filas_de_alertas_no_muestran_el_error_ni_el_detalle() -> None:
    filas = filas_de_alertas_pendientes([alerta(intentos=2, proximo="2026-11-12T10:14:00"), alerta(2, 0, None, None)], AHORA)
    assert [f.valores for f in filas] == [
        ("90 %", "TEC-0042 · K120", "Pendiente (reintentando)", "2", "en 14 min"),
        ("90 %", "Sin etiqueta · K120", "Pendiente", "0", "—"),
    ]
    texto = " ".join(" ".join(f.valores) for f in filas)
    assert "sin conexión" not in texto and "TECLA_INVENTADA" not in texto  # el error y el detalle (puede nombrar una tecla) se ven en P07


def test_el_texto_de_los_destinatarios() -> None:
    assert texto_de_destinatarios(" soporte@ejemplo.invalid ") == "Destinatarios: soporte@ejemplo.invalid"
    assert "sin configurar" in texto_de_destinatarios("")
    assert "sin configurar" in texto_de_destinatarios(None)


# ---------- La pantalla, con la ventana oculta ----------


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Repositorio]:
    """La base de ejemplo abierta con el repositorio (el servicio nunca arrancó en ella)."""
    ruta = tmp_path / "ejemplo.db"
    _ = crear_base_de_ejemplo(ruta, hasta=FIN_DE_LA_BASE)
    repositorio = Repositorio(ruta)
    try:
        yield repositorio
    finally:
        repositorio.cerrar()


@pytest.fixture
def pantalla(repo: Repositorio, tmp_path: Path) -> Iterator[PantallaP01]:
    """P01 dentro de la ventana oculta, con el reloj fijo en 2026-11-12 10:00:00. Se omite si no hay pantalla donde abrirla."""
    try:
        ventana = Aplicacion(repo, tmp_path / "ejemplo.db", al_fallar=lambda _titulo, error: pytest.fail(str(error)))
    except tk.TclError:
        pytest.skip("no hay pantalla donde abrir la ventana")
    try:
        ventana.withdraw()
        ventana.mostrar("p01")
        pantalla_p01_abierta = ventana.pantalla("p01")
        assert isinstance(pantalla_p01_abierta, PantallaP01)
        pantalla_p01_abierta._reloj = lambda: AHORA  # pyright: ignore[reportPrivateUsage]
        yield pantalla_p01_abierta
    finally:
        ventana.destroy()


def fingir_servicio_vivo(repo: Repositorio, estado: str) -> None:
    """Escribe en la base lo que escribiría un servicio que late ahora mismo (según el reloj falso) y dice `estado`."""
    repo.escribir_configuracion(CLAVE_LATIDO, AHORA.isoformat(timespec="seconds"))
    repo.escribir_configuracion(CLAVE_ESTADO, estado)


def test_sin_servicio_la_pantalla_lo_dice_y_avisa_que_la_orden_se_guarda(pantalla: PantallaP01) -> None:
    pantalla.refrescar()
    assert texto_de(pantalla.estado) == "● Servicio detenido"
    assert texto_de(pantalla.aviso) == AVISO_SERVICIO_APAGADO and pantalla.aviso.winfo_manager() != ""
    assert pantalla.boton_detener.instate(["!disabled"]) and pantalla.boton_iniciar.instate(["disabled"])  # la orden por defecto es iniciar


def test_el_boton_detener_escribe_la_orden_y_la_pantalla_espera_la_respuesta_del_servicio(repo: Repositorio, pantalla: PantallaP01) -> None:
    fingir_servicio_vivo(repo, "capturando")
    pantalla.refrescar()
    assert texto_de(pantalla.estado) == "● Captura ACTIVA"
    assert pantalla.aviso.winfo_manager() == ""  # con el servicio vivo no hay aviso

    pantalla.detener_captura()
    assert repo.leer_configuracion(CLAVE_ORDEN) == "detener"
    assert texto_de(pantalla.estado) == "● Deteniendo captura…"  # el servicio todavía no respondió
    assert pantalla.boton_iniciar.instate(["!disabled"]) and pantalla.boton_detener.instate(["disabled"])

    fingir_servicio_vivo(repo, "detenida")  # ahora responde el servicio
    pantalla.refrescar()
    assert texto_de(pantalla.estado) == "● Captura DETENIDA"
    assert texto_de(pantalla.estado, "style") == "Peligro.TLabel"

    pantalla.iniciar_captura()
    assert repo.leer_configuracion(CLAVE_ORDEN) == "iniciar"
    assert texto_de(pantalla.estado) == "● Iniciando captura…"


def test_los_datos_del_dia_coinciden_con_el_repositorio(repo: Repositorio, pantalla: PantallaP01) -> None:
    pantalla.refrescar()
    hoy, manana = "2026-11-12", "2026-11-13"
    segundos_teclado, segundos_mouse = repo.actividad_del_dia(hoy)
    datos = pantalla._datos  # pyright: ignore[reportPrivateUsage]
    assert texto_de(datos["eventos"]) == miles(repo.contar_eventos(hoy, manana))
    assert texto_de(datos["actividad"]) == texto_de_actividad(segundos_teclado, segundos_mouse)
    assert texto_de(datos["reinicios"]) == str(repo.contar_incidentes("caida_proceso", hoy, manana))


def test_las_tablas_traen_los_periferico_y_las_alertas_pendientes_de_la_base(repo: Repositorio, pantalla: PantallaP01) -> None:
    pantalla.refrescar()
    activos = [p for p in repo.listar_perifericos(incluir_retirados=False)]
    assert pantalla.tabla_perifericos.cantidad() >= len(activos)  # el mouse ocupa dos filas
    assert pantalla.tabla_alertas.cantidad() == len(repo.alertas_pendientes())
    assert "soporte" in texto_de(pantalla.nota_alertas).lower() or "Destinatarios" in texto_de(pantalla.nota_alertas)


def test_el_temporizador_empieza_al_mostrar_y_se_cancela_al_cerrar(pantalla: PantallaP01) -> None:
    assert pantalla._temporizador is not None  # pyright: ignore[reportPrivateUsage]
    pantalla.destroy()
    assert pantalla._temporizador is None  # pyright: ignore[reportPrivateUsage]


def test_una_base_ocupada_se_avisa_en_el_estado_y_no_abre_cuadros_de_mensaje(
    repo: Repositorio, pantalla: PantallaP01, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def base_ocupada(*_argumentos: object) -> str | None:
        """Hace como si la base estuviera bloqueada por el servicio."""
        raise sqlite3.OperationalError("database is locked")

    cuadros: list[str] = []

    def registrar_cuadro(titulo: str, *_resto: object, **_opciones: object) -> None:
        """Reemplaza al cuadro de mensaje: anota su título en lugar de abrirlo."""
        cuadros.append(titulo)

    monkeypatch.setattr(messagebox, "showwarning", registrar_cuadro)
    monkeypatch.setattr(repo, "leer_configuracion", base_ocupada)
    pantalla._actualizar_sola()  # pyright: ignore[reportPrivateUsage]
    assert FALLA_DE_LECTURA in texto_de(pantalla.estado)
    assert cuadros == []  # una lectura automática que falla no interrumpe a la persona
    assert pantalla._temporizador is not None  # pyright: ignore[reportPrivateUsage]  # y sigue intentándolo


def test_si_no_se_puede_escribir_la_orden_se_le_dice_a_la_persona(
    repo: Repositorio, pantalla: PantallaP01, monkeypatch: pytest.MonkeyPatch,
) -> None:
    def base_ocupada(*_argumentos: object) -> None:
        """Hace como si la base estuviera bloqueada por el servicio."""
        raise sqlite3.OperationalError("database is locked")

    cuadros: list[str] = []

    def registrar_cuadro(titulo: str, *_resto: object, **_opciones: object) -> None:
        """Reemplaza al cuadro de mensaje: anota su título en lugar de abrirlo."""
        cuadros.append(titulo)

    monkeypatch.setattr(messagebox, "showwarning", registrar_cuadro)
    monkeypatch.setattr(repo, "escribir_configuracion", base_ocupada)
    pantalla.detener_captura()
    assert cuadros == ["No se pudo enviar la orden"]  # pulsó un botón: aquí sí corresponde avisarle
