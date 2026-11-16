"""Pruebas del servicio completo (`servicio/principal.py`): del botón de la interfaz al capturador, pasando por la base de datos.

Con qué datos: el capturador simulado de Python (`pruebas/capturador_simulado.py`, con teclas inventadas), una base SQLite nueva en
una carpeta temporal y una segunda conexión que hace de interfaz, como en el sistema real donde son dos procesos. El servicio
corre en un hilo con lecturas y guardados muy frecuentes para que las pruebas no tarden. Comprueba el recorrido completo
(capturar → guardar → `detener` desde la interfaz → no entran eventos → `iniciar` → entran de nuevo → cierre normal de la
sesión), que al arrancar se cierre como "inesperada" la sesión que quedó abierta (RNF12), que un capturador que no existe se
registre como incidente sin detener al servicio (RF10) y que un fallo del servicio se registre sin copiar su mensaje (RNF11).

Se relaciona con: usa `servicio/principal.py`, `servicio/control.py`, `comun/repositorio.py`, `pruebas/ayudas_base.py` y
`pruebas/capturador_simulado.py` · lo ejecuta pytest.
"""
import signal
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from comun.repositorio import Repositorio
from pruebas.ayudas_base import consultar
from servicio import principal as servicio_principal
from servicio.control import CLAVE_ESTADO, CLAVE_ORDEN, ESTADO_CAPTURANDO, ESTADO_CERRADO, ESTADO_DETENIDA
from servicio.guardador import Guardador
from servicio.principal import comando_del_capturador, ejecutar

SIMULADOR = str(Path(__file__).parent / "capturador_simulado.py")
COMANDO_SIMULADO = [sys.executable, SIMULADOR, "--intervalo", "0.005", "--semilla", "3"]
TIEMPO_MAXIMO = 20.0


def esperar(condicion: Callable[[], bool], tiempo: float = TIEMPO_MAXIMO) -> bool:
    """Revisa `condicion` cada 20 ms hasta `tiempo` segundos. Devuelve True apenas se cumple, False si se acaba el tiempo."""
    limite = time.monotonic() + tiempo
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return False


def cantidad_de_eventos(ruta: Path) -> int:
    """Cuántos eventos hay guardados en la base."""
    return int(str(consultar(ruta, "SELECT COUNT(*) FROM evento")[0][0]))


def arrancar(ruta: Path, comando: list[str]) -> tuple[threading.Thread, threading.Event]:
    """Pone el servicio a correr en un hilo, con lecturas y guardados cada 50 ms. Devuelve el hilo y el evento para cerrarlo."""
    parar = threading.Event()
    hilo = threading.Thread(
        target=ejecutar, args=(ruta, comando, "PC-PRUEBA-01", parar, 0.05, 0.05), name="servicio-de-prueba", daemon=True,
    )
    hilo.start()
    return hilo, parar


def cerrar(hilo: threading.Thread, parar: threading.Event) -> None:
    """Pide el cierre y espera a que el servicio termine."""
    parar.set()
    hilo.join(TIEMPO_MAXIMO)
    assert not hilo.is_alive(), "el servicio no cerró a tiempo"


def test_del_boton_de_la_interfaz_al_capturador(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos.db"
    hilo, parar = arrancar(ruta, COMANDO_SIMULADO)
    try:
        assert esperar(lambda: ruta.exists() and cantidad_de_eventos(ruta) > 20), "no llegaron eventos a la base"
        with Repositorio(ruta) as interfaz:
            assert interfaz.leer_configuracion(CLAVE_ESTADO) == ESTADO_CAPTURANDO

            interfaz.escribir_configuracion(CLAVE_ORDEN, "detener")  # el botón Detener de P01
            assert esperar(lambda: interfaz.leer_configuracion(CLAVE_ESTADO) == ESTADO_DETENIDA), "el servicio no se detuvo"
            time.sleep(0.3)  # deja que se guarde lo que ya venía en camino
            con_la_captura_detenida = cantidad_de_eventos(ruta)
            time.sleep(0.5)
            assert cantidad_de_eventos(ruta) == con_la_captura_detenida, "entraron eventos con la captura detenida"

            interfaz.escribir_configuracion(CLAVE_ORDEN, "iniciar")  # el botón Iniciar
            assert esperar(lambda: cantidad_de_eventos(ruta) > con_la_captura_detenida), "la captura no se reanudó"
    finally:
        cerrar(hilo, parar)

    # La sesión es una sola (detener la captura no cierra la sesión) y se cerró de forma normal al cerrar el servicio.
    sesiones = consultar(ruta, "SELECT fin, tipo_cierre FROM sesion")
    assert len(sesiones) == 1
    assert sesiones[0][1] == "normal" and sesiones[0][0] is not None
    # El simulador manda teclas, y el desgaste quedó contado por día (RF16).
    assert consultar(ruta, "SELECT COUNT(*) FROM contador_diario")[0][0] != 0
    with Repositorio(ruta) as repo:
        assert repo.leer_configuracion(CLAVE_ESTADO) == ESTADO_CERRADO  # al cerrar, la interfaz ve que el servicio ya no está


def test_al_arrancar_cierra_como_inesperada_la_sesion_que_quedo_abierta(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos.db"
    with Repositorio(ruta) as repo:
        vieja = repo.abrir_sesion(repo.obtener_o_crear_equipo("PC-PRUEBA-01"), "2026-11-01T08:00:00")  # un apagado brusco

    hilo, parar = arrancar(ruta, COMANDO_SIMULADO)
    try:
        assert esperar(lambda: len(consultar(ruta, "SELECT id FROM sesion")) == 2), "no se abrió la sesión nueva"
    finally:
        cerrar(hilo, parar)

    assert consultar(ruta, "SELECT tipo_cierre FROM sesion WHERE id = ?", (vieja,))[0][0] == "inesperado"
    assert consultar(ruta, "SELECT COUNT(*) FROM incidente WHERE tipo = 'apagado_inesperado'")[0][0] == 1


def test_un_capturador_que_no_existe_se_registra_y_el_servicio_sigue(tmp_path: Path) -> None:
    ruta = tmp_path / "eventos.db"
    hilo, parar = arrancar(ruta, [str(tmp_path / "no-existe-captura")])
    try:
        assert esperar(lambda: ruta.exists() and len(consultar(ruta, "SELECT id FROM incidente WHERE tipo = 'caida_proceso'")) >= 1)
        assert hilo.is_alive()  # el servicio no se cae: espera y reintenta (RF10)
    finally:
        cerrar(hilo, parar)


def test_el_guardador_esta_listo_antes_de_que_llegue_el_primer_evento(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruta = tmp_path / "eventos.db"
    iniciar_original = Guardador.iniciar
    errores: list[BaseException] = []

    def iniciar_lento(self: Guardador) -> None:
        """Hace que el guardador tarde en abrir la sesión: si el capturador ya estuviera corriendo, sus eventos llegarían antes."""
        time.sleep(0.6)
        iniciar_original(self)

    def recolectar(argumentos: threading.ExceptHookArgs) -> None:
        """Guarda el error de un hilo (por ejemplo, el que lee al capturador) en lugar de imprimirlo."""
        if argumentos.exc_value is not None:
            errores.append(argumentos.exc_value)

    monkeypatch.setattr(Guardador, "iniciar", iniciar_lento)
    monkeypatch.setattr(threading, "excepthook", recolectar)
    hilo, parar = arrancar(ruta, COMANDO_SIMULADO)
    try:
        assert esperar(lambda: ruta.exists() and cantidad_de_eventos(ruta) > 5), "no llegaron eventos a la base"
    finally:
        cerrar(hilo, parar)
    assert errores == [], "llegó un evento antes de que la sesión estuviera abierta"


def test_el_comando_simulado_lleva_sus_opciones() -> None:
    assert comando_del_capturador("captura.exe", False, 100) == ["captura.exe"]
    assert comando_del_capturador("./captura", True, 250) == ["./captura", "--simulado", "--intervalo-ms", "250"]


def test_un_fallo_del_servicio_se_registra_sin_copiar_su_mensaje(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ruta = tmp_path / "eventos.db"
    mensaje_con_datos = "texto que no debe copiarse"

    def fallar(*_argumentos: object, **_opciones: object) -> None:
        """Hace como si el servicio hubiera fallado por dentro."""
        raise RuntimeError(mensaje_con_datos)

    monkeypatch.setattr(servicio_principal, "ejecutar", fallar)

    def no_tocar_las_senales(*_argumentos: object) -> None:
        """Reemplaza a `signal.signal` para no cambiar cómo el proceso de pytest atiende Ctrl+C."""

    monkeypatch.setattr(signal, "signal", no_tocar_las_senales)

    assert servicio_principal.principal(["--base", str(ruta)]) == 1
    detalles = consultar(ruta, "SELECT detalle FROM incidente WHERE tipo = 'caida_proceso'")
    assert len(detalles) == 1
    assert "RuntimeError" in str(detalles[0][0])
    assert mensaje_con_datos not in str(detalles[0][0])
