"""Servicio de monitoreo: el programa que se instala en cada PC. `python -m servicio.principal` (o `pythonw`, sin ventana).

Qué hace: junta las piezas del servicio y las mantiene en marcha hasta que se le pide cerrar:

    capturador (C++) ──JSON──▶ GestorSubproceso ──▶ Guardador ──▶ SQLite ◀── interfaz
                                      ▲
                          Controlador (lee `orden_captura` de la base y lo inicia o detiene)

Cómo funciona: `ejecutar` abre el repositorio, crea el guardador (que cierra como "inesperada" cualquier sesión que haya quedado
abierta y abre la nueva, RNF12), el gestor del subproceso y el controlador, y espera una señal de parada. Para cerrar lo hace en
el orden contrario: primero el controlador, luego el gestor (ya no entran eventos) y al final el guardador, que hace un último
guardado y cierra la sesión como "normal". El orden de arranque importa: el guardador debe estar listo antes de que el gestor
entregue el primer evento.

Con `pythonw` (la tarea de inicio de Windows, RF21) no hay consola ni teclado: nadie puede pulsar Ctrl+C, así que el servicio
se cierra al terminar la sesión de Windows y la sesión queda abierta; la siguiente vez se cierra como "inesperada" y queda un
incidente. Con consola, Ctrl+C y Ctrl+Pausa (en Windows) cierran de forma normal.

Transparencia (RNF11): el trabajador no ve ventanas ni mensajes. Si el servicio falla, lo registra en `incidente` y termina con
código 1; nunca muestra el error en pantalla ni copia su mensaje (podría tener datos). Privacidad (RNF4): aquí no se lee, guarda
ni imprime ninguna tecla.

Opciones: `--base` (otro archivo de base de datos), `--capturador` (programa del capturador; por defecto `captura.exe`),
`--simulado` (el capturador escribe eventos inventados: sirve en macOS y Linux), `--intervalo-ms` (espera entre eventos
simulados) y `--equipo` (nombre del equipo; por defecto el de la PC).

Se relaciona con: usa `comun/repositorio.py`, `servicio/guardador.py`, `servicio/gestor_subproceso.py`, `servicio/control.py` y el
capturador de `capturador/` · lo lanzará el instalador (issue #35), lo comprueba `servicio/resumen.py` y lo prueba
`pruebas/test_principal.py`.
"""
import argparse
import signal
import socket
import sqlite3
import sys
import threading
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import FrameType

from comun.repositorio import Repositorio, ruta_por_defecto
from servicio.control import INTERVALO_DE_LECTURA, Controlador
from servicio.gestor_subproceso import GestorSubproceso
from servicio.guardador import INTERVALO_DE_GUARDADO, Guardador

CAPTURADOR_POR_DEFECTO = "captura.exe"
INTERVALO_SIMULADO_MS = 100  # un evento cada 100 ms: lo bastante lento para ver crecer los contadores en la interfaz


class Opciones(argparse.Namespace):
    """Opciones de la línea de comandos, con sus tipos."""

    base: str | None = None
    capturador: str = CAPTURADOR_POR_DEFECTO
    simulado: bool = False
    intervalo_ms: int = INTERVALO_SIMULADO_MS
    equipo: str | None = None


def comando_del_capturador(capturador: str, simulado: bool, intervalo_ms: int) -> list[str]:
    """El comando que lanza el gestor: el programa y, si es simulado, sus opciones (`--simulado --intervalo-ms N`)."""
    if simulado:
        return [capturador, "--simulado", "--intervalo-ms", str(intervalo_ms)]
    return [capturador]


def ejecutar(
    ruta: Path,
    comando: Sequence[str],
    nombre_equipo: str,
    parar: threading.Event,
    intervalo_de_lectura: float = INTERVALO_DE_LECTURA,
    intervalo_de_guardado: float = INTERVALO_DE_GUARDADO,
) -> None:
    """Arranca el servicio y lo mantiene en marcha hasta que `parar` se activa; entonces lo cierra en orden.

    ruta: la base de datos (se crea si no existe). comando: el capturador. nombre_equipo: nombre de esta PC (RF18).
    parar: el evento que activa quien quiere cerrar el servicio (una señal, o una prueba).
    intervalo_de_lectura: segundos entre lecturas de la orden de la interfaz; las pruebas usan un valor pequeño.
    intervalo_de_guardado: segundos entre guardados de eventos y contadores (RNF12); las pruebas usan un valor pequeño.
    """
    with Repositorio(ruta) as repo:
        guardador = Guardador(repo, nombre_equipo, intervalo=intervalo_de_guardado)
        gestor = GestorSubproceso(comando, guardador.al_evento, guardador.al_incidente)
        control = Controlador(repo, gestor, intervalo_de_lectura)
        guardador.iniciar()  # antes que el gestor: `al_evento` necesita la sesión ya abierta
        try:
            control.iniciar()  # lee `orden_captura` y arranca el gestor si corresponde
            while not parar.wait(0.5):  # con un tiempo y no sin él: en Windows un `wait()` sin límite no deja pasar Ctrl+C
                pass
        finally:
            control.detener()
            gestor.detener()
            guardador.detener()


def _registrar_fallo(ruta: Path, error: Exception) -> None:
    """Anota en `incidente` que el servicio terminó por un error. Solo el tipo: el mensaje podría traer datos (RNF4, RNF11)."""
    try:
        with Repositorio(ruta) as repo:
            repo.guardar_incidente(
                "caida_proceso", datetime.now().isoformat(timespec="seconds"),
                f"el servicio terminó por un error ({type(error).__name__})", "servicio detenido",
            )
    except (sqlite3.Error, OSError):
        pass  # si ni la base se puede abrir no hay dónde registrar nada; el servicio igual termina sin mostrar nada


def _pedir_cierre_con(parar: threading.Event) -> None:
    """Hace que Ctrl+C, la orden de terminar y (en Windows) Ctrl+Pausa activen `parar` en lugar de matar el programa de golpe."""
    def alertar(_numero: int, _marco: FrameType | None) -> None:
        """Manejador de señal: solo activa el evento; el cierre ordenado lo hace `ejecutar`."""
        parar.set()

    senales = [signal.SIGINT, signal.SIGTERM]
    if sys.platform == "win32":
        senales.append(signal.SIGBREAK)
    for senal in senales:
        _ = signal.signal(senal, alertar)


def principal(argumentos: Sequence[str] | None = None) -> int:
    """Lee las opciones, arranca el servicio y devuelve 0 al cerrarse bien, o 1 si falló y lo registró."""
    analizador = argparse.ArgumentParser(prog="python -m servicio.principal", description="Servicio de monitoreo de teclado y mouse.")
    _ = analizador.add_argument("--base", help="archivo de la base de datos (por defecto, la del sistema o CAPTURADOR_RUTA_DB)")
    _ = analizador.add_argument("--capturador", default=CAPTURADOR_POR_DEFECTO, help=f"programa del capturador (por defecto {CAPTURADOR_POR_DEFECTO})")
    _ = analizador.add_argument("--simulado", action="store_true", help="el capturador escribe eventos inventados (para probar sin Windows)")
    _ = analizador.add_argument("--intervalo-ms", type=int, default=INTERVALO_SIMULADO_MS, help="con --simulado, espera entre eventos")
    _ = analizador.add_argument("--equipo", help="nombre del equipo (por defecto, el de la PC)")
    opciones = analizador.parse_args(argumentos, namespace=Opciones())

    ruta = Path(opciones.base) if opciones.base else ruta_por_defecto()
    comando = comando_del_capturador(opciones.capturador, opciones.simulado, opciones.intervalo_ms)
    parar = threading.Event()
    _pedir_cierre_con(parar)
    try:
        ejecutar(ruta, comando, opciones.equipo or socket.gethostname(), parar)
    except Exception as error:  # el servicio no debe mostrar nada al trabajador: se registra y se termina (RNF11)
        _registrar_fallo(ruta, error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(principal())
