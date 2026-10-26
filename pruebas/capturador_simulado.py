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
import json
import random
import sys
import time
from datetime import datetime

DISPOSITIVO_TECLADO = {"dispositivo": "teclado", "vid": "046D", "pid": "C31C", "nombre": "Logitech K120"}
DISPOSITIVO_MOUSE = {"dispositivo": "mouse", "vid": "046D", "pid": "C077", "nombre": "Logitech B100"}

TECLAS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + ["ENTER", "ESPACIO", "RETROCESO", "TAB", "F5"]
ANCHO_PANTALLA = 1920
ALTO_PANTALLA = 1080

# Código de salida cuando se simula que el capturador se cae (RF10).
CODIGO_CAIDA = 3


def hora_actual():
    """Hora local en ISO 8601 con milisegundos, como pide el contrato."""
    return datetime.now().isoformat(timespec="milliseconds")


def armar_evento(tipo, base_dispositivo, **extra):
    """Arma un evento con el orden de campos del contrato."""
    evento = {"v": 1, "tipo": tipo, "hora": hora_actual()}
    evento.update(base_dispositivo)
    evento.update(extra)
    return evento


def generar_eventos_validos(azar):
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


def linea_invalida(azar):
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
    return json.dumps(evento, ensure_ascii=False, separators=(",", ":"))


def leer_argumentos(argumentos=None):
    analizador = argparse.ArgumentParser(description="Escribe eventos JSON simulados por stdout.")
    analizador.add_argument("--cantidad", type=int, default=None,
                            help="cantidad de líneas a escribir; sin este dato, sigue hasta que lo cierren")
    analizador.add_argument("--intervalo", type=float, default=0.05,
                            help="segundos de espera entre líneas (0 para escribir lo más rápido posible)")
    analizador.add_argument("--semilla", type=int, default=None,
                            help="número para repetir la misma secuencia de eventos")
    analizador.add_argument("--proporcion-invalidos", type=float, default=0.0,
                            help="probabilidad (de 0 a 1) de que una línea sea inválida")
    analizador.add_argument("--caida-en", type=int, default=None,
                            help="termina de golpe con error después de esta cantidad de líneas (RF10)")
    return analizador.parse_args(argumentos)


def principal(argumentos=None):
    datos = leer_argumentos(argumentos)
    azar = random.Random(datos.semilla)

    # El contrato pide UTF-8 y saltos de línea \n, también en Windows.
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
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
                linea = json.dumps(next(eventos), ensure_ascii=False, separators=(",", ":"))
            sys.stdout.write(linea + "\n")
            sys.stdout.flush()
            escritas += 1
            if datos.intervalo > 0:
                time.sleep(datos.intervalo)
    except BrokenPipeError:
        # El servicio cerró la lectura: terminar sin ruido.
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(principal())
