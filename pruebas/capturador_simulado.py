#!/usr/bin/env python3
"""Capturador simulado.

Escribe por stdout eventos de teclado y mouse inventados, uno por línea, con el
formato de docs/arquitectura/contrato-json.md. Sirve para desarrollar y probar
el servicio de Python en cualquier sistema operativo, sin Raw Input ni Windows.

Ejemplos:
    python pruebas/capturador_simulado.py --cantidad 20
    python pruebas/capturador_simulado.py --cantidad 1000 --intervalo 0 --semilla 7
    python pruebas/capturador_simulado.py --cantidad 50 --proporcion-invalidos 0.2
    python pruebas/capturador_simulado.py --caida-en 10

Privacidad (RNF4): el nombre de la tecla solo viaja por stdout, como pide el
contrato. Este script nunca lo escribe en stderr ni en ningún archivo.
"""
import argparse
import io
import json
import random
import sys
import time
from collections.abc import Iterator
from datetime import datetime
from typing import TextIO

type Evento = dict[str, str | int]

DISPOSITIVO_TECLADO: dict[str, str] = {"dispositivo": "teclado", "vid": "046D", "pid": "C31C", "nombre": "Logitech K120"}
DISPOSITIVO_MOUSE: dict[str, str] = {"dispositivo": "mouse", "vid": "046D", "pid": "C077", "nombre": "Logitech B100"}

TECLAS: list[str] = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + ["ENTER", "ESPACIO", "RETROCESO", "TAB", "F5"]
ANCHO_PANTALLA = 1920
ALTO_PANTALLA = 1080

# Código de salida cuando se simula que el capturador se cae (RF10).
CODIGO_CAIDA = 3


class Opciones(argparse.Namespace):
    """Opciones de la línea de comandos, con sus tipos para que el editor las compruebe."""

    # Los valores por defecto viven aquí: argparse no los pisa si el atributo ya existe.
    cantidad: int | None = None
    intervalo: float = 0.05
    semilla: int | None = None
    proporcion_invalidos: float = 0.0
    caida_en: int | None = None


def hora_actual() -> str:
    """Hora local en ISO 8601 con milisegundos, como pide el contrato."""
    return datetime.now().isoformat(timespec="milliseconds")


def armar_evento(tipo: str, base_dispositivo: dict[str, str], **extra: str | int) -> Evento:
    """Arma un evento con el orden de campos del contrato."""
    evento: Evento = {"v": 1, "tipo": tipo, "hora": hora_actual()}
    evento.update(base_dispositivo)
    evento.update(extra)
    return evento


def generar_eventos_validos(azar: random.Random) -> Iterator[Evento]:
    """Genera eventos válidos sin fin. Una pulsación produce dos eventos: presionada y liberada."""
    while True:
        suerte = azar.random()
        if suerte < 0.50:
            tecla = azar.choice(TECLAS)
            yield armar_evento("tecla_presionada", DISPOSITIVO_TECLADO, tecla=tecla)
            yield armar_evento("tecla_liberada", DISPOSITIVO_TECLADO)
        elif suerte < 0.80:
            yield armar_evento(
                "mouse_movimiento", DISPOSITIVO_MOUSE,
                x=azar.randint(0, ANCHO_PANTALLA - 1), y=azar.randint(0, ALTO_PANTALLA - 1),
            )
        elif suerte < 0.92:
            yield armar_evento(azar.choice(["clic_izquierdo", "clic_derecho"]), DISPOSITIVO_MOUSE)
        else:
            pasos = azar.choice([-3, -2, -1, 1, 2, 3])
            yield armar_evento("scroll", DISPOSITIVO_MOUSE, pasos=pasos)


def a_linea(evento: Evento) -> str:
    """Convierte un evento en una línea JSON compacta."""
    return json.dumps(evento, ensure_ascii=False, separators=(",", ":"))


def linea_invalida(azar: random.Random) -> str:
    """Devuelve una línea que el validador debe rechazar (RF9)."""
    caso = azar.choice(["no_json", "sin_hora", "tipo_desconocido", "campo_prohibido"])
    if caso == "no_json":
        return "esto no es un json"
    if caso == "sin_hora":
        evento = armar_evento("clic_izquierdo", DISPOSITIVO_MOUSE)
        del evento["hora"]
    elif caso == "tipo_desconocido":
        evento = armar_evento("mouse_arrastre", DISPOSITIVO_MOUSE)
    else:
        # Una tecla liberada no puede traer la tecla (RNF4).
        evento = armar_evento("tecla_liberada", DISPOSITIVO_TECLADO, tecla="E")
    return a_linea(evento)


def leer_argumentos(argumentos: list[str] | None = None) -> Opciones:
    analizador = argparse.ArgumentParser(description="Escribe eventos JSON simulados por stdout.")
    _ = analizador.add_argument("--cantidad", type=int,
                                help="cantidad de líneas a escribir; sin este dato, sigue hasta que lo cierren")
    _ = analizador.add_argument("--intervalo", type=float,
                                help="segundos de espera entre líneas (0 para escribir lo más rápido posible; por defecto 0.05)")
    _ = analizador.add_argument("--semilla", type=int,
                                help="número para repetir la misma secuencia de eventos")
    _ = analizador.add_argument("--proporcion-invalidos", type=float,
                                help="probabilidad (de 0 a 1) de que una línea sea inválida")
    _ = analizador.add_argument("--caida-en", type=int,
                                help="termina de golpe con error después de esta cantidad de líneas (RF10)")
    return analizador.parse_args(argumentos, namespace=Opciones())


def principal(argumentos: list[str] | None = None) -> int:
    datos = leer_argumentos(argumentos)
    azar = random.Random(datos.semilla)

    # El contrato pide UTF-8 y saltos de línea \n, también en Windows.
    salida: TextIO = sys.stdout
    if isinstance(salida, io.TextIOWrapper):
        salida.reconfigure(encoding="utf-8", newline="\n")
    print("Capturador simulado iniciado", file=sys.stderr, flush=True)

    escritas = 0
    eventos = generar_eventos_validos(azar)
    try:
        while datos.cantidad is None or escritas < datos.cantidad:
            if datos.caida_en is not None and escritas >= datos.caida_en:
                print("Capturador simulado: caída simulada", file=sys.stderr, flush=True)
                return CODIGO_CAIDA
            if azar.random() < datos.proporcion_invalidos:
                linea = linea_invalida(azar)
            else:
                linea = a_linea(next(eventos))
            _ = salida.write(linea + "\n")
            salida.flush()
            escritas += 1
            if datos.intervalo > 0:
                time.sleep(datos.intervalo)
    except BrokenPipeError:
        # El servicio cerró la lectura: terminar sin ruido.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(principal())
