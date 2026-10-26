#!/usr/bin/env python3
"""Prueba manual del capturador real, pensada para un PC con Windows.

Lanza el capturador con el gestor del subproceso durante unos segundos, mientras la persona
escribe, mueve el mouse, hace clic y gira la rueda. Al final muestra un resumen: cuántos eventos
llegaron, de qué dispositivos, si hubo líneas descartadas o caídas, y cuánto tardó cada evento en
llegar a Python (RNF1: menos de 1 segundo).

Privacidad (RNF4): el resumen solo cuenta tipos de evento y dispositivos. Nunca muestra qué tecla se pulsó.

Se ejecuta desde la carpeta raíz del repositorio, con `-m`, para que encuentre el paquete `servicio`:
    python -m pruebas.manual_windows --capturador captura.exe --segundos 30
    python -m pruebas.manual_windows --capturador captura.exe --simulado   (prueba del script, sin teclado ni mouse)
"""
import argparse
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from servicio.gestor_subproceso import ESPERAS_POR_DEFECTO, GestorSubproceso, Incidente
from servicio.validador import EventoValido

LIMITE_RETRASO_MS = 1000.0  # RNF1: el evento debe llegar en menos de 1 segundo
SEGUNDOS_ENTRE_AVISOS = 5.0


@dataclass(frozen=True, slots=True)
class Resumen:
    """Lo que se vio durante la prueba. No guarda teclas."""

    total: int = 0
    por_tipo: dict[str, int] = field(default_factory=dict[str, int])
    dispositivos: dict[str, int] = field(default_factory=dict[str, int])
    retrasos_ms: tuple[float, ...] = ()
    descartadas: int = 0
    caidas: int = 0


class Recolector:
    """Recibe lo que entrega el gestor desde su hilo y lo cuenta."""

    def __init__(self) -> None:
        self._candado: threading.Lock = threading.Lock()
        self._por_tipo: Counter[str] = Counter()
        self._dispositivos: Counter[str] = Counter()
        self._retrasos: list[float] = []
        self._descartadas: int = 0
        self._caidas: int = 0

    def al_evento(self, evento: EventoValido) -> None:
        retraso_ms = (datetime.now() - datetime.fromisoformat(evento.hora)).total_seconds() * 1000
        with self._candado:
            self._por_tipo[evento.tipo] += 1
            self._dispositivos[f"{evento.dispositivo} {evento.vid}:{evento.pid}"] += 1
            self._retrasos.append(max(0.0, retraso_ms))

    def al_incidente(self, incidente: Incidente) -> None:
        with self._candado:
            if incidente.tipo == "caida_proceso":
                self._caidas += 1
            else:
                self._descartadas += 1

    def instantanea(self) -> Resumen:
        with self._candado:
            return Resumen(
                total=len(self._retrasos),
                por_tipo=dict(self._por_tipo),
                dispositivos=dict(self._dispositivos),
                retrasos_ms=tuple(self._retrasos),
                descartadas=self._descartadas,
                caidas=self._caidas,
            )


def calcular_estadisticas(retrasos_ms: Sequence[float]) -> tuple[float, float, float]:
    """Devuelve (promedio, percentil 95, máximo) de los retrasos. Con una lista vacía, ceros."""
    if not retrasos_ms:
        return 0.0, 0.0, 0.0
    ordenados = sorted(retrasos_ms)
    promedio = sum(ordenados) / len(ordenados)
    percentil_95 = ordenados[int(0.95 * (len(ordenados) - 1))]
    return promedio, percentil_95, ordenados[-1]


def cumple(resumen: Resumen) -> bool:
    """La prueba pasa si llegaron eventos, no hubo caídas y el retraso máximo fue menor a 1 s."""
    _, _, maximo = calcular_estadisticas(resumen.retrasos_ms)
    return resumen.total > 0 and resumen.caidas == 0 and maximo < LIMITE_RETRASO_MS


def dar_formato(resumen: Resumen, segundos: float) -> str:
    promedio, percentil_95, maximo = calcular_estadisticas(resumen.retrasos_ms)
    tipos = ", ".join(f"{tipo} {cantidad}" for tipo, cantidad in sorted(resumen.por_tipo.items())) or "ninguno"
    dispositivos = ", ".join(sorted(resumen.dispositivos)) or "ninguno"
    veredicto = "CUMPLE" if cumple(resumen) else "NO CUMPLE"
    return "\n".join([
        f"Resultado de la prueba ({segundos:g} s)",
        f"  Eventos válidos recibidos : {resumen.total}",
        f"  Por tipo                  : {tipos}",
        f"  Dispositivos vistos       : {dispositivos}",
        f"  Líneas descartadas        : {resumen.descartadas}",
        f"  Caídas del capturador     : {resumen.caidas}",
        f"  Retraso hasta Python      : promedio {promedio:.1f} ms, percentil 95 {percentil_95:.1f} ms, máximo {maximo:.1f} ms",
        f"  Veredicto (RNF1 < {LIMITE_RETRASO_MS:g} ms, sin caídas): {veredicto}",
    ])


def ejecutar_prueba(
    comando: Sequence[str],
    segundos: float,
    al_progreso: Callable[[Resumen], None] | None = None,
    esperas: Sequence[float] = ESPERAS_POR_DEFECTO,
) -> Resumen:
    """Corre el capturador con el gestor durante `segundos` y devuelve lo que se vio."""
    recolector = Recolector()
    gestor = GestorSubproceso(comando, recolector.al_evento, recolector.al_incidente, esperas)
    gestor.iniciar()
    inicio = time.monotonic()
    ultimo_aviso = inicio
    try:
        while time.monotonic() - inicio < segundos:
            time.sleep(0.1)
            if al_progreso is not None and time.monotonic() - ultimo_aviso >= SEGUNDOS_ENTRE_AVISOS:
                ultimo_aviso = time.monotonic()
                al_progreso(recolector.instantanea())
    finally:
        gestor.detener()
    return recolector.instantanea()


class Opciones(argparse.Namespace):
    capturador: str = "captura.exe"
    segundos: float = 30.0
    simulado: bool = False


def leer_argumentos(argumentos: Sequence[str] | None = None) -> Opciones:
    analizador = argparse.ArgumentParser(description="Prueba manual del capturador.")
    _ = analizador.add_argument("--capturador", help="ruta del capturador (por defecto captura.exe)")
    _ = analizador.add_argument("--segundos", type=float, help="duración de la prueba (por defecto 30)")
    _ = analizador.add_argument("--simulado", action="store_true",
                                help="pasa --simulado al capturador, para probar este script sin teclado ni mouse")
    return analizador.parse_args(argumentos, namespace=Opciones())


def principal(argumentos: Sequence[str] | None = None) -> int:
    opciones = leer_argumentos(argumentos)
    comando = [opciones.capturador, *(["--simulado", "--intervalo-ms", "20"] if opciones.simulado else [])]

    print(f"Durante {opciones.segundos:g} segundos: escribe, mueve el mouse, haz clic y gira la rueda.")
    print("No escribas contraseñas ni datos personales. Para parar antes, pulsa Ctrl+C.")
    try:
        resumen = ejecutar_prueba(
            comando, opciones.segundos,
            al_progreso=lambda parcial: print(f"  ... {parcial.total} eventos hasta ahora"),
        )
    except KeyboardInterrupt:
        print("Prueba interrumpida.")
        return 1
    print()
    print(dar_formato(resumen, opciones.segundos))
    return 0 if cumple(resumen) else 1


if __name__ == "__main__":
    sys.exit(principal())
