"""Pruebas del validador de eventos contra docs/arquitectura/contrato-json.md."""
import json
import re
from pathlib import Path

import pytest

from servicio.validador import EventoValido, LineaRechazada, validar_linea

CONTRATO = Path(__file__).parent.parent / "docs" / "arquitectura" / "contrato-json.md"

type Campos = dict[str, object]

BASE_TECLADO: Campos = {"v": 1, "hora": "2026-10-25T21:14:03.482", "dispositivo": "teclado",
                        "vid": "046D", "pid": "C31C", "nombre": "Logitech K120"}
BASE_MOUSE: Campos = {"v": 1, "hora": "2026-10-25T21:14:04.101", "dispositivo": "mouse",
                      "vid": "046D", "pid": "C077"}


def linea(base: Campos, tipo: str, /, **cambios: object) -> str:
    """Arma una línea JSON a partir de una base. Un cambio con valor None elimina el campo."""
    campos: Campos = {"tipo": tipo, **base}
    for nombre, valor in cambios.items():
        if valor is None:
            _ = campos.pop(nombre, None)
        else:
            campos[nombre] = valor
    return json.dumps(campos)


def rechazada(texto: str) -> LineaRechazada:
    resultado = validar_linea(texto)
    assert isinstance(resultado, LineaRechazada), texto
    return resultado


def ejemplos_del_contrato() -> list[str]:
    """Las líneas del bloque de ejemplos de contrato-json.md."""
    bloque = re.search(r"```json\n(.*?)```", CONTRATO.read_text(encoding="utf-8"), flags=re.DOTALL)
    assert bloque is not None, "el contrato ya no tiene un bloque de ejemplos"
    return bloque.group(1).strip().splitlines()


# ---------- Líneas válidas ----------

def test_acepta_todos_los_ejemplos_del_contrato() -> None:
    ejemplos = ejemplos_del_contrato()
    assert len(ejemplos) >= 5
    for ejemplo in ejemplos:
        assert isinstance(validar_linea(ejemplo), EventoValido), ejemplo


def test_acepta_una_pulsacion_y_conserva_sus_campos() -> None:
    resultado = validar_linea(linea(BASE_TECLADO, "tecla_presionada", tecla="E"))
    assert resultado == EventoValido(
        tipo="tecla_presionada", hora="2026-10-25T21:14:03.482", dispositivo="teclado",
        vid="046D", pid="C31C", nombre="Logitech K120", tecla="E",
    )


def test_acepta_movimiento_con_coordenadas_negativas() -> None:
    # Con varios monitores, el cursor puede estar a la izquierda del monitor principal.
    resultado = validar_linea(linea(BASE_MOUSE, "mouse_movimiento", x=-300, y=40))
    assert isinstance(resultado, EventoValido)
    assert (resultado.x, resultado.y) == (-300, 40)


def test_acepta_scroll_hacia_abajo_y_hacia_arriba() -> None:
    for pasos in (-3, 1):
        resultado = validar_linea(linea(BASE_MOUSE, "scroll", pasos=pasos))
        assert isinstance(resultado, EventoValido)
        assert resultado.pasos == pasos


def test_ignora_espacios_y_salto_de_linea_al_final() -> None:
    assert isinstance(validar_linea(linea(BASE_MOUSE, "clic_izquierdo") + "\n"), EventoValido)


# ---------- Líneas que no son JSON: error_comunicacion ----------

@pytest.mark.parametrize("texto", ["esto no es un json", "", "   ", '{"v":1,"tipo":"scroll"', "{'v': 1}"])
def test_una_linea_que_no_es_json_es_error_de_comunicacion(texto: str) -> None:
    assert rechazada(texto).tipo_incidente == "error_comunicacion"


def test_un_json_que_no_es_objeto_es_evento_invalido() -> None:
    for texto in ("[1, 2]", "42", '"hola"', "null"):
        assert rechazada(texto).tipo_incidente == "evento_invalido", texto


# ---------- JSON con campos incorrectos: evento_invalido ----------

CASOS_INVALIDOS: list[tuple[str, str, str]] = [
    # (descripción, línea, fragmento esperado en el detalle)
    ("falta la hora", linea(BASE_MOUSE, "clic_izquierdo", hora=None), "hora"),
    ("falta la versión", linea(BASE_MOUSE, "clic_izquierdo", v=None), "versión"),
    ("versión distinta de 1", linea(BASE_MOUSE, "clic_izquierdo", v=2), "versión"),
    ("versión booleana", linea(BASE_MOUSE, "clic_izquierdo", v=True), "versión"),
    ("tipo desconocido", linea(BASE_MOUSE, "mouse_arrastre"), "tipo"),
    ("tipo que no es texto", linea(BASE_MOUSE, "clic_izquierdo", tipo=7), "tipo"),
    ("hora sin milisegundos", linea(BASE_MOUSE, "clic_izquierdo", hora="2026-10-25T21:14:03"), "hora"),
    ("hora con espacio", linea(BASE_MOUSE, "clic_izquierdo", hora="2026-10-25 21:14:03.482"), "hora"),
    ("hora con mes 13", linea(BASE_MOUSE, "clic_izquierdo", hora="2026-13-45T21:14:03.482"), "hora"),
    ("dispositivo desconocido", linea(BASE_MOUSE, "clic_izquierdo", dispositivo="tableta"), "dispositivo"),
    ("clic desde un teclado", linea(BASE_TECLADO, "clic_izquierdo"), "dispositivo"),
    ("tecla desde un mouse", linea(BASE_MOUSE, "tecla_presionada", tecla="E"), "dispositivo"),
    ("vid con 3 dígitos", linea(BASE_MOUSE, "clic_izquierdo", vid="46D"), "vid"),
    ("pid en minúsculas", linea(BASE_MOUSE, "clic_izquierdo", pid="c077"), "pid"),
    ("falta el pid", linea(BASE_MOUSE, "clic_izquierdo", pid=None), "pid"),
    ("nombre que no es texto", linea(BASE_MOUSE, "clic_izquierdo", nombre=5), "nombre"),
    ("pulsación sin tecla", linea(BASE_TECLADO, "tecla_presionada"), "falta el campo tecla"),
    ("tecla en una liberación", linea(BASE_TECLADO, "tecla_liberada", tecla="E"), "no corresponde"),
    ("tecla vacía", linea(BASE_TECLADO, "tecla_presionada", tecla=" "), "tecla"),
    ("tecla en minúsculas", linea(BASE_TECLADO, "tecla_presionada", tecla="e"), "tecla"),
    ("tecla demasiado larga", linea(BASE_TECLADO, "tecla_presionada", tecla="A" * 21), "tecla"),
    ("tecla que no es texto", linea(BASE_TECLADO, "tecla_presionada", tecla=5), "tecla"),
    ("movimiento sin y", linea(BASE_MOUSE, "mouse_movimiento", x=10), "falta el campo y"),
    ("x como texto", linea(BASE_MOUSE, "mouse_movimiento", x="10", y=20), "x debe ser"),
    ("x decimal", linea(BASE_MOUSE, "mouse_movimiento", x=10.5, y=20), "x debe ser"),
    ("y booleana", linea(BASE_MOUSE, "mouse_movimiento", x=10, y=True), "y debe ser"),
    ("coordenadas en un clic", linea(BASE_MOUSE, "clic_derecho", x=1, y=2), "no corresponde"),
    ("scroll sin pasos", linea(BASE_MOUSE, "scroll"), "falta el campo pasos"),
    ("scroll con 0 pasos", linea(BASE_MOUSE, "scroll", pasos=0), "pasos"),
    ("pasos como texto", linea(BASE_MOUSE, "scroll", pasos="3"), "pasos"),
    ("pasos en un clic", linea(BASE_MOUSE, "clic_izquierdo", pasos=1), "no corresponde"),
    ("campo desconocido", linea(BASE_MOUSE, "clic_izquierdo", color="rojo"), "desconocido"),
]


@pytest.mark.parametrize(("descripcion", "texto", "fragmento"), CASOS_INVALIDOS, ids=[c[0] for c in CASOS_INVALIDOS])
def test_rechaza_un_evento_que_incumple_el_contrato(descripcion: str, texto: str, fragmento: str) -> None:
    resultado = rechazada(texto)
    assert resultado.tipo_incidente == "evento_invalido", descripcion
    assert fragmento in resultado.detalle, resultado.detalle


def test_informa_todos_los_problemas_de_una_linea() -> None:
    detalle = rechazada(linea(BASE_MOUSE, "scroll", hora=None, pasos=0)).detalle
    assert "hora" in detalle
    assert "pasos" in detalle


# ---------- Privacidad (RNF4) ----------

TECLA_SECRETA = "CLAVEULTRASECRETA"


def test_el_motivo_de_rechazo_no_copia_la_tecla() -> None:
    lineas = [
        linea(BASE_TECLADO, "tecla_liberada", tecla=TECLA_SECRETA),            # tecla donde no debe ir
        linea(BASE_TECLADO, "tecla_presionada", tecla=TECLA_SECRETA, hora=None),  # falla otro campo
        linea(BASE_TECLADO, "tecla_presionada", tecla=TECLA_SECRETA.lower()),   # tecla en minúsculas
        '{"tecla":"' + TECLA_SECRETA,                                          # JSON cortado
    ]
    for texto in lineas:
        detalle = rechazada(texto).detalle
        assert TECLA_SECRETA not in detalle.upper(), texto


def test_el_motivo_de_rechazo_no_repite_nombres_de_campos_desconocidos() -> None:
    detalle = rechazada(linea(BASE_MOUSE, "clic_izquierdo", campo_con_datos_ajenos="x")).detalle
    assert "campo_con_datos_ajenos" not in detalle


def test_el_evento_no_muestra_la_tecla_al_imprimirse() -> None:
    resultado = validar_linea(linea(BASE_TECLADO, "tecla_presionada", tecla="PAUSA"))
    assert isinstance(resultado, EventoValido)
    assert resultado.tecla == "PAUSA"
    assert "PAUSA" not in repr(resultado)
    assert "PAUSA" not in str(resultado)
