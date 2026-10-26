"""Pruebas del capturador simulado contra docs/arquitectura/contrato-json.md."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent / "capturador_simulado.py"

TIPOS = {"tecla_presionada", "tecla_liberada", "mouse_movimiento", "clic_izquierdo", "clic_derecho", "scroll"}
TIPOS_DE_TECLADO = {"tecla_presionada", "tecla_liberada"}
PATRON_HORA = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}$")
PATRON_HEX = re.compile(r"^[0-9A-F]{4}$")

# Campos que cada tipo debe traer y no debe traer (tabla "Reglas por tipo" del contrato).
OBLIGATORIOS = {
    "tecla_presionada": {"tecla"},
    "tecla_liberada": set(),
    "mouse_movimiento": {"x", "y"},
    "clic_izquierdo": set(),
    "clic_derecho": set(),
    "scroll": {"pasos"},
}
OPCIONALES_COMUNES = {"v", "tipo", "hora", "dispositivo", "vid", "pid", "nombre"}


def ejecutar(*argumentos):
    """Ejecuta el capturador simulado y devuelve el resultado con la salida en bytes."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--intervalo", "0", *argumentos],
        capture_output=True, timeout=30,
    )


def lineas_de(resultado):
    return resultado.stdout.decode("utf-8").splitlines()


def problemas_de(evento):
    """Devuelve la lista de problemas de un evento según el contrato; vacía si es válido."""
    problemas = []
    tipo = evento.get("tipo")
    if tipo not in TIPOS:
        return [f"tipo desconocido: {tipo}"]
    if evento.get("v") != 1:
        problemas.append("versión distinta de 1")
    if not PATRON_HORA.match(str(evento.get("hora", ""))):
        problemas.append("hora ausente o con formato incorrecto")
    if evento.get("dispositivo") not in {"teclado", "mouse"}:
        problemas.append("dispositivo inválido")
    elif (evento["dispositivo"] == "teclado") != (tipo in TIPOS_DE_TECLADO):
        problemas.append("dispositivo incoherente con el tipo")
    for campo in ("vid", "pid"):
        if not PATRON_HEX.match(str(evento.get(campo, ""))):
            problemas.append(f"{campo} inválido")
    permitidos = OPCIONALES_COMUNES | OBLIGATORIOS[tipo]
    for campo in OBLIGATORIOS[tipo]:
        if campo not in evento:
            problemas.append(f"falta {campo}")
    for campo in set(evento) - permitidos:
        problemas.append(f"campo prohibido: {campo}")
    if tipo == "scroll" and evento.get("pasos") == 0:
        problemas.append("pasos no puede ser 0")
    return problemas


def test_escribe_la_cantidad_pedida_de_lineas_json_validas():
    resultado = ejecutar("--cantidad", "200", "--semilla", "1")
    assert resultado.returncode == 0
    lineas = lineas_de(resultado)
    assert len(lineas) == 200
    for linea in lineas:
        evento = json.loads(linea)
        assert problemas_de(evento) == [], linea


def test_usa_todos_los_tipos_de_evento():
    resultado = ejecutar("--cantidad", "500", "--semilla", "2")
    tipos = {json.loads(linea)["tipo"] for linea in lineas_de(resultado)}
    assert tipos == TIPOS


def test_la_tecla_liberada_no_trae_la_tecla():
    resultado = ejecutar("--cantidad", "300", "--semilla", "3")
    for linea in lineas_de(resultado):
        evento = json.loads(linea)
        if evento["tipo"] == "tecla_liberada":
            assert "tecla" not in evento


def test_la_misma_semilla_repite_la_secuencia():
    def sin_hora(resultado):
        eventos = [json.loads(linea) for linea in lineas_de(resultado)]
        for evento in eventos:
            evento.pop("hora")
        return eventos

    primera = sin_hora(ejecutar("--cantidad", "100", "--semilla", "5"))
    segunda = sin_hora(ejecutar("--cantidad", "100", "--semilla", "5"))
    assert primera == segunda


def test_usa_saltos_de_linea_n_y_utf8():
    resultado = ejecutar("--cantidad", "50", "--semilla", "6")
    assert b"\r" not in resultado.stdout
    assert resultado.stdout.endswith(b"\n")
    resultado.stdout.decode("utf-8")


def test_con_proporcion_total_de_invalidos_ninguna_linea_es_valida():
    resultado = ejecutar("--cantidad", "100", "--semilla", "8", "--proporcion-invalidos", "1")
    for linea in lineas_de(resultado):
        try:
            evento = json.loads(linea)
        except json.JSONDecodeError:
            continue  # no es JSON: el validador la rechaza como error de comunicación
        assert problemas_de(evento) != [], linea


def test_la_caida_simulada_termina_con_error_despues_de_n_lineas():
    resultado = ejecutar("--cantidad", "100", "--semilla", "9", "--caida-en", "5")
    assert resultado.returncode == 3
    assert len(lineas_de(resultado)) == 5


def test_stderr_no_muestra_teclas():
    resultado = ejecutar("--cantidad", "100", "--semilla", "10")
    texto_stderr = resultado.stderr.decode("utf-8")
    for linea in lineas_de(resultado):
        evento = json.loads(linea)
        if "tecla" in evento:
            assert f'"{evento["tecla"]}"' not in texto_stderr
