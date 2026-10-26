"""Validador de eventos (RF9).

Recibe una línea de stdout del capturador y decide si es un evento válido según
docs/arquitectura/contrato-json.md. No guarda nada: solo devuelve el evento
validado o el motivo del rechazo, y quien lo llama decide qué hacer.

Privacidad (RNF4): el motivo de rechazo describe el problema, pero nunca copia la
línea ni el valor de ningún campo, porque podría contener qué tecla se pulsó.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, cast

type TipoIncidente = Literal["error_comunicacion", "evento_invalido"]

VERSION_CONTRATO = 1

TIPOS_DE_TECLADO = frozenset({"tecla_presionada", "tecla_liberada"})

# Campos adicionales que cada tipo de evento debe traer (tabla "Reglas por tipo" del contrato).
CAMPOS_OBLIGATORIOS: dict[str, frozenset[str]] = {
    "tecla_presionada": frozenset({"tecla"}),
    "tecla_liberada": frozenset(),
    "mouse_movimiento": frozenset({"x", "y"}),
    "clic_izquierdo": frozenset(),
    "clic_derecho": frozenset(),
    "scroll": frozenset({"pasos"}),
}

CAMPOS_COMUNES = frozenset({"v", "tipo", "hora", "dispositivo", "vid", "pid", "nombre"})
CAMPOS_CONOCIDOS = CAMPOS_COMUNES | frozenset({"tecla", "x", "y", "pasos"})

# Se usa [0-9] y no \d porque \d también acepta dígitos de otros alfabetos.
PATRON_HORA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}")
PATRON_HEXADECIMAL = re.compile(r"[0-9A-F]{4}")
# Nombre de tecla: de 1 a 20 caracteres, sin espacios (la barra espaciadora se llama ESPACIO).
PATRON_TECLA = re.compile(r"\S{1,20}")


@dataclass(frozen=True, slots=True)
class EventoValido:
    """Un evento que cumple el contrato. Los campos que no aplican al tipo quedan en None."""

    tipo: str
    hora: str
    dispositivo: str
    vid: str
    pid: str
    nombre: str | None = None
    # repr=False: si alguien imprime el evento por error, la tecla no aparece (RNF4).
    tecla: str | None = field(default=None, repr=False)
    x: int | None = None
    y: int | None = None
    pasos: int | None = None


@dataclass(frozen=True, slots=True)
class LineaRechazada:
    """Una línea que no cumple el contrato, con el tipo de incidente que debe registrarse."""

    tipo_incidente: TipoIncidente
    detalle: str


type ResultadoValidacion = EventoValido | LineaRechazada


def validar_linea(linea: str) -> ResultadoValidacion:
    """Valida una línea del capturador y devuelve el evento o el motivo del rechazo."""
    texto = linea.strip()
    if not texto:
        return LineaRechazada("error_comunicacion", "la línea está vacía")
    try:
        datos = cast(object, json.loads(texto))
    except json.JSONDecodeError as error:
        return LineaRechazada("error_comunicacion", f"la línea no es JSON válido (posición {error.pos})")
    except (ValueError, RecursionError):
        return LineaRechazada("error_comunicacion", "la línea no se pudo leer como JSON")
    if not isinstance(datos, dict):
        return LineaRechazada("evento_invalido", "el JSON no es un objeto")

    campos = cast(dict[str, object], datos)
    problemas = _buscar_problemas(campos)
    if problemas:
        return LineaRechazada("evento_invalido", "; ".join(problemas))
    return _crear_evento(campos)


def _es_entero(valor: object) -> bool:
    """True si es un entero. En Python True y False también son enteros, y aquí no valen."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def _hora_valida(valor: object) -> bool:
    if not isinstance(valor, str) or not PATRON_HORA.fullmatch(valor):
        return False
    try:
        _ = datetime.strptime(valor, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return False  # tiene el formato, pero la fecha no existe (por ejemplo, mes 13)
    return True


def _buscar_problemas(campos: dict[str, object]) -> list[str]:
    tipo = campos.get("tipo")
    if not isinstance(tipo, str) or tipo not in CAMPOS_OBLIGATORIOS:
        return ["tipo ausente o desconocido"]

    problemas: list[str] = []
    if not _es_entero(campos.get("v")) or campos.get("v") != VERSION_CONTRATO:
        problemas.append("versión del contrato no soportada")
    if not _hora_valida(campos.get("hora")):
        problemas.append("hora ausente o con formato incorrecto")

    dispositivo = campos.get("dispositivo")
    if dispositivo not in {"teclado", "mouse"}:
        problemas.append("dispositivo ausente o inválido")
    elif (dispositivo == "teclado") != (tipo in TIPOS_DE_TECLADO):
        problemas.append(f"el dispositivo no corresponde al tipo {tipo}")

    for nombre_campo in ("vid", "pid"):
        valor = campos.get(nombre_campo)
        if not isinstance(valor, str) or not PATRON_HEXADECIMAL.fullmatch(valor):
            problemas.append(f"{nombre_campo} ausente o inválido")

    if "nombre" in campos and not isinstance(campos["nombre"], str):
        problemas.append("nombre debe ser texto")

    obligatorios = CAMPOS_OBLIGATORIOS[tipo]
    problemas.extend(f"falta el campo {campo}" for campo in sorted(obligatorios) if campo not in campos)

    permitidos = CAMPOS_COMUNES | obligatorios
    for campo in sorted(set(campos) - permitidos):
        # Solo se nombra el campo si es del contrato: un nombre desconocido podría contener datos.
        if campo in CAMPOS_CONOCIDOS:
            problemas.append(f"el campo {campo} no corresponde al tipo {tipo}")
        else:
            problemas.append("hay un campo desconocido")

    problemas.extend(_problemas_de_valores(campos))
    return problemas


def _problemas_de_valores(campos: dict[str, object]) -> list[str]:
    """Revisa el valor de los campos opcionales por tipo, solo cuando están presentes."""
    problemas: list[str] = []
    if "tecla" in campos:
        tecla = campos["tecla"]
        if not isinstance(tecla, str) or not PATRON_TECLA.fullmatch(tecla) or tecla != tecla.upper():
            problemas.append("tecla inválida (debe ser un nombre corto, en mayúsculas y sin espacios)")
    for coordenada in ("x", "y"):
        if coordenada in campos and not _es_entero(campos[coordenada]):
            problemas.append(f"{coordenada} debe ser un entero")
    if "pasos" in campos:
        pasos = campos["pasos"]
        if not _es_entero(pasos) or pasos == 0:
            problemas.append("pasos debe ser un entero distinto de 0")
    return problemas


def _texto_opcional(campos: dict[str, object], nombre: str) -> str | None:
    valor = campos.get(nombre)
    return valor if isinstance(valor, str) else None


def _entero_opcional(campos: dict[str, object], nombre: str) -> int | None:
    valor = campos.get(nombre)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def _crear_evento(campos: dict[str, object]) -> EventoValido:
    """Convierte un diccionario ya validado en un EventoValido."""
    return EventoValido(
        tipo=str(campos["tipo"]),
        hora=str(campos["hora"]),
        dispositivo=str(campos["dispositivo"]),
        vid=str(campos["vid"]),
        pid=str(campos["pid"]),
        nombre=_texto_opcional(campos, "nombre"),
        tecla=_texto_opcional(campos, "tecla"),
        x=_entero_opcional(campos, "x"),
        y=_entero_opcional(campos, "y"),
        pasos=_entero_opcional(campos, "pasos"),
    )
