"""Pruebas del capturador simulado. Las reglas del contrato las aplica el validador real."""
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

from servicio.validador import EventoValido, LineaRechazada, validar_linea

SCRIPT = Path(__file__).parent / "capturador_simulado.py"

TIPOS = {"tecla_presionada", "tecla_liberada", "mouse_movimiento", "clic_izquierdo", "clic_derecho", "scroll"}

type Evento = dict[str, object]


def ejecutar(*argumentos: str) -> subprocess.CompletedProcess[bytes]:
    """Ejecuta el capturador simulado y devuelve el resultado con la salida en bytes."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--intervalo", "0", *argumentos],
        capture_output=True, timeout=30, check=False,
    )


def lineas_de(resultado: subprocess.CompletedProcess[bytes]) -> list[str]:
    return resultado.stdout.decode("utf-8").splitlines()


def cargar(linea: str) -> Evento:
    """Convierte una línea JSON en un diccionario."""
    return cast(Evento, json.loads(linea))


def test_escribe_la_cantidad_pedida_de_lineas_que_el_validador_acepta() -> None:
    resultado = ejecutar("--cantidad", "200", "--semilla", "1")
    assert resultado.returncode == 0
    lineas = lineas_de(resultado)
    assert len(lineas) == 200
    for linea in lineas:
        assert isinstance(validar_linea(linea), EventoValido), linea


def test_usa_todos_los_tipos_de_evento() -> None:
    resultado = ejecutar("--cantidad", "500", "--semilla", "2")
    tipos = {cargar(linea)["tipo"] for linea in lineas_de(resultado)}
    assert tipos == TIPOS


def test_la_tecla_liberada_no_trae_la_tecla() -> None:
    resultado = ejecutar("--cantidad", "300", "--semilla", "3")
    for linea in lineas_de(resultado):
        evento = cargar(linea)
        if evento["tipo"] == "tecla_liberada":
            assert "tecla" not in evento


def test_la_misma_semilla_repite_la_secuencia() -> None:
    def sin_hora(resultado: subprocess.CompletedProcess[bytes]) -> list[Evento]:
        eventos = [cargar(linea) for linea in lineas_de(resultado)]
        for evento in eventos:
            del evento["hora"]
        return eventos

    primera = sin_hora(ejecutar("--cantidad", "100", "--semilla", "5"))
    segunda = sin_hora(ejecutar("--cantidad", "100", "--semilla", "5"))
    assert primera == segunda


def test_usa_saltos_de_linea_n_y_utf8() -> None:
    resultado = ejecutar("--cantidad", "50", "--semilla", "6")
    assert b"\r" not in resultado.stdout
    assert resultado.stdout.endswith(b"\n")
    _ = resultado.stdout.decode("utf-8")


def test_con_proporcion_total_de_invalidos_el_validador_rechaza_todas_las_lineas() -> None:
    resultado = ejecutar("--cantidad", "100", "--semilla", "8", "--proporcion-invalidos", "1")
    tipos_de_incidente: set[str] = set()
    for linea in lineas_de(resultado):
        rechazo = validar_linea(linea)
        assert isinstance(rechazo, LineaRechazada), linea
        tipos_de_incidente.add(rechazo.tipo_incidente)
    # Las líneas malas del simulador cubren los dos tipos de incidente de RF9.
    assert tipos_de_incidente == {"error_comunicacion", "evento_invalido"}


def test_la_caida_simulada_termina_con_error_despues_de_n_lineas() -> None:
    resultado = ejecutar("--cantidad", "100", "--semilla", "9", "--caida-en", "5")
    assert resultado.returncode == 3
    assert len(lineas_de(resultado)) == 5


def test_stderr_no_muestra_teclas() -> None:
    resultado = ejecutar("--cantidad", "100", "--semilla", "10")
    texto_stderr = resultado.stderr.decode("utf-8")
    for linea in lineas_de(resultado):
        evento = cargar(linea)
        if "tecla" in evento:
            assert f'"{evento["tecla"]}"' not in texto_stderr
