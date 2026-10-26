"""Pruebas del gestor del subproceso, usando el capturador simulado como proceso real."""
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from servicio.gestor_subproceso import GestorSubproceso, Incidente
from servicio.validador import EventoValido

SIMULADOR = str(Path(__file__).parent / "capturador_simulado.py")
TIEMPO_MAXIMO = 15.0  # segundos que una prueba espera antes de darse por fallida


class Recolector:
    """Guarda lo que entrega el gestor y permite esperar a que llegue algo."""

    def __init__(self) -> None:
        self.eventos: list[EventoValido] = []
        self.incidentes: list[Incidente] = []
        self._cambio: threading.Condition = threading.Condition()

    def al_evento(self, evento: EventoValido) -> None:
        with self._cambio:
            self.eventos.append(evento)
            self._cambio.notify_all()

    def al_incidente(self, incidente: Incidente) -> None:
        with self._cambio:
            self.incidentes.append(incidente)
            self._cambio.notify_all()

    def esperar(self, condicion: Callable[[], bool]) -> bool:
        with self._cambio:
            return self._cambio.wait_for(condicion, timeout=TIEMPO_MAXIMO)

    def esperar_eventos(self, cantidad: int) -> bool:
        return self.esperar(lambda: len(self.eventos) >= cantidad)

    def esperar_incidentes(self, cantidad: int) -> bool:
        return self.esperar(lambda: len(self.incidentes) >= cantidad)


@pytest.fixture
def gestores() -> Iterator[list[GestorSubproceso]]:
    """Garantiza que ningún gestor ni proceso quede vivo al terminar la prueba."""
    creados: list[GestorSubproceso] = []
    yield creados
    for gestor in creados:
        gestor.detener()


def crear(
    gestores: list[GestorSubproceso],
    recolector: Recolector,
    comando: list[str],
    esperas: tuple[float, ...] = (0.01,),
    max_relanzamientos: int | None = None,
) -> GestorSubproceso:
    gestor = GestorSubproceso(comando, recolector.al_evento, recolector.al_incidente, esperas, max_relanzamientos)
    gestores.append(gestor)
    return gestor


def simulador(*argumentos: str) -> list[str]:
    return [sys.executable, SIMULADOR, "--intervalo", "0", *argumentos]


def programa(codigo: str) -> list[str]:
    """Un capturador falso de una sola línea de Python."""
    return [sys.executable, "-c", codigo]


# ---------- RF2 y RF3: lanzar y leer en tiempo real ----------

def test_lee_y_entrega_los_eventos_validos(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, simulador("--cantidad", "100000", "--semilla", "1"))
    gestor.iniciar()
    assert recolector.esperar_eventos(100)
    gestor.detener()
    assert all(isinstance(evento, EventoValido) for evento in recolector.eventos)
    assert {evento.dispositivo for evento in recolector.eventos} == {"teclado", "mouse"}


def test_el_primer_evento_llega_sin_esperar_a_que_termine_el_capturador(gestores: list[GestorSubproceso]) -> None:
    # Una línea cada 0,2 s y sin fin: si el gestor esperara a un búfer lleno, nunca llegaría nada.
    recolector = Recolector()
    comando = [sys.executable, SIMULADOR, "--intervalo", "0.2", "--semilla", "2"]
    gestor = crear(gestores, recolector, comando)
    inicio = time.monotonic()
    gestor.iniciar()
    assert recolector.esperar_eventos(1)
    assert time.monotonic() - inicio < TIEMPO_MAXIMO
    assert gestor.esta_activo()
    gestor.detener()


# ---------- RF11: parar el capturador ----------

def test_detener_no_se_registra_como_caida(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, simulador("--semilla", "3"))
    gestor.iniciar()
    assert recolector.esperar_eventos(10)
    gestor.detener()
    assert not gestor.esta_activo()
    assert recolector.incidentes == []


def test_detener_sin_haber_iniciado_o_dos_veces_no_falla(gestores: list[GestorSubproceso]) -> None:
    gestor = crear(gestores, Recolector(), simulador("--cantidad", "5"))
    gestor.detener()
    gestor.iniciar()
    gestor.detener()
    gestor.detener()
    assert not gestor.esta_activo()


def test_no_se_puede_iniciar_dos_veces(gestores: list[GestorSubproceso]) -> None:
    gestor = crear(gestores, Recolector(), simulador("--semilla", "4"))
    gestor.iniciar()
    with pytest.raises(RuntimeError):
        gestor.iniciar()
    gestor.detener()


# ---------- RF10 y RF21: caída y relanzamiento ----------

def test_registra_la_caida_y_relanza_el_capturador(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, simulador("--cantidad", "100", "--caida-en", "3", "--semilla", "5"))
    gestor.iniciar()
    assert recolector.esperar_eventos(6)  # 3 eventos de la primera ejecución y 3 de la relanzada
    assert recolector.esperar_incidentes(1)
    gestor.detener()
    primero = recolector.incidentes[0]
    assert primero.tipo == "caida_proceso"
    assert "código 3" in primero.detalle
    assert primero.accion is not None
    assert "relanzado" in primero.accion


def test_se_rinde_despues_de_los_fallos_seguidos_permitidos(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, programa("import sys; sys.exit(5)"), max_relanzamientos=2)
    gestor.iniciar()
    gestor.esperar(TIEMPO_MAXIMO)
    assert not gestor.esta_activo()
    assert recolector.eventos == []
    assert [incidente.tipo for incidente in recolector.incidentes] == ["caida_proceso"] * 3
    assert all("código 5" in incidente.detalle for incidente in recolector.incidentes)
    ultimo = recolector.incidentes[-1]
    assert ultimo.accion == "se agotaron los relanzamientos"


def test_un_capturador_que_no_existe_se_registra_y_no_rompe_el_servicio(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, ["/ruta/que/no/existe/capturador"], max_relanzamientos=1)
    gestor.iniciar()
    gestor.esperar(TIEMPO_MAXIMO)
    assert not gestor.esta_activo()
    assert recolector.incidentes
    assert all(incidente.tipo == "caida_proceso" for incidente in recolector.incidentes)
    assert "no se pudo iniciar" in recolector.incidentes[0].detalle


def test_la_espera_entre_relanzamientos_crece_y_se_puede_interrumpir(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    gestor = crear(gestores, recolector, programa("import sys; sys.exit(1)"), esperas=(30.0,))
    gestor.iniciar()
    assert recolector.esperar_incidentes(1)
    assert recolector.incidentes[0].accion == "relanzado en 30 s"
    inicio = time.monotonic()
    gestor.detener()  # el gestor está esperando 30 s: debe despertar enseguida
    assert time.monotonic() - inicio < 5.0
    assert not gestor.esta_activo()


def test_un_capturador_estable_reinicia_la_cuenta_de_fallos(gestores: list[GestorSubproceso]) -> None:
    # Cada ejecución entrega eventos y luego cae: nunca se acumulan fallos seguidos, así que no se rinde.
    recolector = Recolector()
    gestor = crear(gestores, recolector, simulador("--cantidad", "100", "--caida-en", "2", "--semilla", "6"),
                   max_relanzamientos=0)
    gestor.iniciar()
    assert recolector.esperar_incidentes(4)
    assert gestor.esta_activo()
    gestor.detener()


# ---------- RF9: líneas inválidas sin interrumpir la captura ----------

def test_las_lineas_invalidas_se_registran_y_la_lectura_continua(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    comando = simulador("--cantidad", "60", "--proporcion-invalidos", "0.5", "--semilla", "7")
    gestor = crear(gestores, recolector, comando, max_relanzamientos=0)
    gestor.iniciar()
    assert recolector.esperar_eventos(5)
    gestor.detener()
    descartadas = [i for i in recolector.incidentes if i.tipo != "caida_proceso"]
    assert descartadas
    assert {i.tipo for i in descartadas} <= {"error_comunicacion", "evento_invalido"}
    assert all(i.accion == "línea descartada" for i in descartadas)


# ---------- RNF4: privacidad ----------

def test_un_incidente_nunca_contiene_la_tecla_que_llego_en_la_linea(gestores: list[GestorSubproceso]) -> None:
    recolector = Recolector()
    linea_mala = (
        '{"v":1,"tipo":"tecla_liberada","hora":"2026-10-25T21:14:03.560","dispositivo":"teclado",'
        '"vid":"046D","pid":"C31C","tecla":"CLAVEULTRASECRETA"}'
    )
    gestor = crear(gestores, recolector, programa(f"print({linea_mala!r})"), max_relanzamientos=0)
    gestor.iniciar()
    gestor.esperar(TIEMPO_MAXIMO)
    assert len(recolector.incidentes) >= 2  # la línea descartada y la caída
    for incidente in recolector.incidentes:
        assert "CLAVEULTRASECRETA" not in incidente.detalle.upper()
        assert incidente.accion is None or "CLAVEULTRASECRETA" not in incidente.accion.upper()
