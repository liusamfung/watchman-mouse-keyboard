"""Pruebas del capturador simulado contra docs/arquitectura/contrato-json.md."""
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

SCRIPT = Path(__file__).parent / "capturador_simulado.py"

TIPOS = {"tecla_presionada", "tecla_liberada", "mouse_movimiento", "clic_izquierdo", "clic_derecho", "scroll"}
TIPOS_DE_TECLADO = {"tecla_presionada", "tecla_liberada"}
PATRON_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$")
PATRON_HEX = re.compile(r"^[0-9A-F]{4}$")

# Campos que cada tipo debe traer (tabla "Reglas por tipo" del contrato).
OBLIGATORIOS: dict[str, set[str]] = {
    "tecla_presionada": {"tecla"},
    "tecla_liberada": set(),
    "mouse_movimiento": {"x", "y"},
    "clic_izquierdo": set(),
    "clic_derecho": set(),
    "scroll": {"pasos"},
}
OPCIONALES_COMUNES = {"v", "tipo", "hora", "dispositivo", "vid", "pid", "nombre"}

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


def problemas_de(evento: Evento) -> list[str]:
    """Devuelve la lista de problemas de un evento según el contrato; vacía si es válido."""
    tipo = evento.get("tipo")
    if not isinstance(tipo, str) or tipo not in TIPOS:
        return [f"tipo desconocido: {tipo}"]
    problemas: list[str] = []
    if evento.get("v") != 1:
        problemas.append("versión distinta de 1")
    if not PATRON_HORA.match(str(evento.get("hora", ""))):
        problemas.append("hora ausente o con formato incorrecto")
    dispositivo = evento.get("dispositivo")
    if dispositivo not in {"teclado", "mouse"}:
        problemas.append("dispositivo inválido")
    elif (dispositivo == "teclado") != (tipo in TIPOS_DE_TECLADO):
        problemas.append("dispositivo incoherente con el tipo")
    for campo in ("vid", "pid"):
        if not PATRON_HEX.match(str(evento.get(campo, ""))):
            problemas.append(f"{campo} inválido")
    permitidos = OPCIONALES_COMUNES | OBLIGATORIOS[tipo]
    problemas.extend(f"falta {campo}" for campo in OBLIGATORIOS[tipo] if campo not in evento)
    problemas.extend(f"campo prohibido: {campo}" for campo in set(evento) - permitidos)
    if tipo == "scroll" and evento.get("pasos") == 0:
        problemas.append("pasos no puede ser 0")
    return problemas


def test_escribe_la_cantidad_pedida_de_lineas_json_validas() -> None:
    resultado = ejecutar("--cantidad", "200", "--semilla", "1")
    assert resultado.returncode == 0
    lineas = lineas_de(resultado)
    assert len(lineas) == 200
    for linea in lineas:
        assert problemas_de(cargar(linea)) == [], linea


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


def test_con_proporcion_total_de_invalidos_ninguna_linea_es_valida() -> None:
    resultado = ejecutar("--cantidad", "100", "--semilla", "8", "--proporcion-invalidos", "1")
    for linea in lineas_de(resultado):
        try:
            evento = cargar(linea)
        except json.JSONDecodeError:
            continue  # no es JSON: el validador la rechaza como error de comunicación
        assert problemas_de(evento) != [], linea


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
