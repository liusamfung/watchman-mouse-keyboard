"""Pruebas del controlador de captura (RF11): la orden de la interfaz llega al servicio por la base de datos.

Con qué datos: una base SQLite nueva en una carpeta temporal, un gestor falso que solo cuenta cuántas veces lo iniciaron o
detuvieron (no lanza ningún capturador) y un `Reloj` falso con la hora fija 2026-11-02 08:00:00. La interfaz se imita con una
segunda conexión (otro `Repositorio` sobre el mismo archivo), igual que en el sistema real, donde son dos procesos. Comprueba:
que `detener` e `iniciar` se apliquen, que no se repita una orden que ya se cumplió, que una orden ausente valga "iniciar" y una
desconocida no cambie nada, que una falla de la base no detenga al servicio (RNF11), que el hilo reaccione solo, y que
`leer_estado` distinga un servicio vivo, uno caído y uno que nunca arrancó.

Se relaciona con: usa `servicio/control.py`, `comun/repositorio.py` y `pruebas/ayudas_base.py` · lo ejecuta pytest.
"""
import sqlite3
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import override

import pytest

from comun.repositorio import Repositorio
from pruebas.ayudas_base import Reloj
from servicio.control import (
    CLAVE_ESTADO,
    CLAVE_LATIDO,
    CLAVE_ORDEN,
    ESTADO_CAPTURANDO,
    ESTADO_CERRADO,
    ESTADO_DETENIDA,
    INTERVALO_DE_LECTURA,
    LATIDOS_PERDIDOS,
    Controlador,
    leer_estado,
)

TIEMPO_MAXIMO = 10.0


class GestorFalso:
    """Un gestor que no lanza nada: solo recuerda si está activo y cuántas veces lo iniciaron y lo detuvieron."""

    def __init__(self) -> None:
        """Empieza detenido y sin llamadas."""
        self.activo: bool = False
        self.inicios: int = 0
        self.paradas: int = 0

    def iniciar(self) -> None:
        """Lo deja activo y cuenta la llamada."""
        self.activo = True
        self.inicios += 1

    def detener(self) -> None:
        """Lo deja detenido y cuenta la llamada."""
        self.activo = False
        self.paradas += 1

    def esta_activo(self) -> bool:
        """True si lo iniciaron y no lo detuvieron."""
        return self.activo


class RepositorioConBaseCaida(Repositorio):
    """Un repositorio cuyas lecturas y escrituras de configuración fallan, como si la base estuviera bloqueada."""

    @override
    def leer_configuracion(self, clave: str) -> str | None:
        """Falla siempre, como una base bloqueada."""
        raise sqlite3.OperationalError("database is locked")

    @override
    def escribir_configuracion(self, clave: str, valor: str) -> None:
        """Falla siempre, como una base bloqueada."""
        raise sqlite3.OperationalError("database is locked")


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta de una base que todavía no existe, dentro de la carpeta temporal de la prueba."""
    return tmp_path / "eventos.db"


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """La conexión del servicio. Al crearla se crea la base, con la orden por defecto `iniciar`."""
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


@pytest.fixture
def interfaz(ruta_db: Path) -> Iterator[Repositorio]:
    """La conexión de la interfaz: otro `Repositorio` sobre el mismo archivo, como el otro proceso del sistema real."""
    with Repositorio(ruta_db) as conexion:
        yield conexion


@pytest.fixture
def gestor() -> GestorFalso:
    """Un gestor falso nuevo."""
    return GestorFalso()


@pytest.fixture
def reloj() -> Reloj:
    """Un reloj falso que parte el 2026-11-02 a las 08:00:00."""
    return Reloj()


def esperar(condicion: Callable[[], bool], tiempo: float = TIEMPO_MAXIMO) -> bool:
    """Revisa `condicion` cada 20 ms hasta `tiempo` segundos. Devuelve True apenas se cumple, False si se acaba el tiempo."""
    limite = time.monotonic() + tiempo
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return False


# ---------- Aplicar la orden ----------

def test_con_la_orden_por_defecto_la_captura_arranca(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()
    assert gestor.activo
    assert repo.leer_configuracion(CLAVE_ESTADO) == ESTADO_CAPTURANDO


def test_detener_y_volver_a_iniciar(repo: Repositorio, interfaz: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()

    interfaz.escribir_configuracion(CLAVE_ORDEN, "detener")  # lo que hará el botón Detener de P01
    control.aplicar_orden()
    assert not gestor.activo
    assert repo.leer_configuracion(CLAVE_ESTADO) == ESTADO_DETENIDA

    interfaz.escribir_configuracion(CLAVE_ORDEN, "iniciar")
    control.aplicar_orden()
    assert gestor.activo
    assert repo.leer_configuracion(CLAVE_ESTADO) == ESTADO_CAPTURANDO
    assert (gestor.inicios, gestor.paradas) == (2, 1)


def test_una_orden_que_ya_se_cumplio_no_se_repite(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    for _ in range(3):
        control.aplicar_orden()
    assert (gestor.inicios, gestor.paradas) == (1, 0)  # iniciar un gestor activo lanzaría un error


def test_la_orden_se_entiende_con_mayusculas_y_espacios(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()
    repo.escribir_configuracion(CLAVE_ORDEN, "  DETENER ")
    control.aplicar_orden()
    assert not gestor.activo


def test_una_orden_desconocida_no_cambia_nada(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()
    repo.escribir_configuracion(CLAVE_ORDEN, "pausar")  # un valor que nadie debería escribir
    control.aplicar_orden()
    assert gestor.activo  # no se apagó el monitoreo por un dato mal escrito
    assert gestor.paradas == 0


def test_sin_la_clave_de_orden_se_inicia(ruta_db: Path, repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    conexion = sqlite3.connect(ruta_db)
    try:
        with conexion:
            _ = conexion.execute("DELETE FROM configuracion WHERE clave = ?", (CLAVE_ORDEN,))
    finally:
        conexion.close()
    assert repo.leer_configuracion(CLAVE_ORDEN) is None
    Controlador(repo, gestor, reloj=reloj).aplicar_orden()
    assert gestor.activo


def test_una_falla_de_la_base_no_detiene_al_servicio(ruta_db: Path, gestor: GestorFalso, reloj: Reloj) -> None:
    with RepositorioConBaseCaida(ruta_db) as repo_caido:
        gestor.activo = True  # la captura ya estaba en marcha cuando la base empezó a fallar
        control = Controlador(repo_caido, gestor, reloj=reloj)
        control.aplicar_orden()  # no debe lanzar el error (RNF11)
        control.aplicar_orden()
        assert gestor.activo  # sin poder leer la orden, se deja todo como estaba
        assert control.errores_de_base >= 2


# ---------- El estado que ve la interfaz ----------

def test_publica_el_latido_en_cada_lectura(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()
    assert repo.leer_configuracion(CLAVE_LATIDO) == "2026-11-02T08:00:00"
    reloj.avanzar(2)
    control.aplicar_orden()
    assert repo.leer_configuracion(CLAVE_LATIDO) == "2026-11-02T08:00:02"


def test_el_estado_dice_capturando_mientras_el_latido_es_reciente(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    Controlador(repo, gestor, reloj=reloj).aplicar_orden()
    estado = leer_estado(repo, reloj())
    assert (estado.orden, estado.estado, estado.en_marcha, estado.capturando) == ("iniciar", ESTADO_CAPTURANDO, True, True)


def test_un_servicio_sin_latido_reciente_no_se_muestra_como_capturando(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    Controlador(repo, gestor, reloj=reloj).aplicar_orden()
    reloj.avanzar(INTERVALO_DE_LECTURA * LATIDOS_PERDIDOS + 1)  # el servicio se cayó: nadie renueva el latido
    estado = leer_estado(repo, reloj())
    assert estado.estado == ESTADO_CAPTURANDO  # lo último que dijo antes de caerse
    assert not estado.en_marcha
    assert not estado.capturando  # pero la interfaz no debe creerlo


def test_un_servicio_que_nunca_arranco(repo: Repositorio, reloj: Reloj) -> None:
    estado = leer_estado(repo, reloj())
    assert estado.ultimo_latido is None
    assert not estado.en_marcha and not estado.capturando


def test_un_latido_ilegible_cuenta_como_servicio_caido(repo: Repositorio, reloj: Reloj) -> None:
    repo.escribir_configuracion(CLAVE_LATIDO, "no es una fecha")
    assert not leer_estado(repo, reloj()).en_marcha


# ---------- El hilo ----------

def test_el_hilo_aplica_la_orden_sin_que_nadie_la_pida(repo: Repositorio, interfaz: Repositorio, gestor: GestorFalso) -> None:
    control = Controlador(repo, gestor, intervalo=0.02)
    control.iniciar()
    try:
        assert gestor.activo  # `iniciar` aplica la orden de inmediato, sin esperar el primer intervalo

        interfaz.escribir_configuracion(CLAVE_ORDEN, "detener")
        assert esperar(lambda: not gestor.activo), "el hilo no aplicó la orden de detener"

        interfaz.escribir_configuracion(CLAVE_ORDEN, "iniciar")
        assert esperar(lambda: gestor.activo), "el hilo no aplicó la orden de iniciar"
    finally:
        control.detener()


def test_detener_publica_cerrado_y_se_puede_repetir(repo: Repositorio, gestor: GestorFalso) -> None:
    control = Controlador(repo, gestor, intervalo=0.02)
    control.iniciar()
    control.detener()
    control.detener()  # llamarlo otra vez no falla
    assert repo.leer_configuracion(CLAVE_ESTADO) == ESTADO_CERRADO


def test_un_servicio_cerrado_de_forma_ordenada_no_espera_a_que_venza_el_latido(repo: Repositorio, gestor: GestorFalso, reloj: Reloj) -> None:
    control = Controlador(repo, gestor, reloj=reloj)
    control.aplicar_orden()
    control.detener()  # el latido es de este mismo instante, pero el servicio ya no está
    estado = leer_estado(repo, reloj())
    assert estado.estado == ESTADO_CERRADO
    assert not estado.en_marcha and not estado.capturando


def test_no_se_puede_iniciar_dos_veces(repo: Repositorio, gestor: GestorFalso) -> None:
    control = Controlador(repo, gestor, intervalo=0.02)
    control.iniciar()
    try:
        with pytest.raises(RuntimeError):
            control.iniciar()
    finally:
        control.detener()
