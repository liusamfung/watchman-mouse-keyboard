"""Ayudas compartidas por las pruebas que usan la base de datos y eventos."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

from servicio.validador import EventoValido


def consultar(ruta: Path, sql: str, parametros: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    """Lee la base con una conexión aparte, como lo haría otro proceso."""
    conexion = sqlite3.connect(ruta)
    try:
        return cast(list[tuple[object, ...]], conexion.execute(sql, parametros).fetchall())
    finally:
        conexion.close()


def evento_de_prueba(
    tipo: str = "clic_izquierdo",
    hora: str = "2026-11-02T08:00:00.100",
    dispositivo: str = "mouse",
    vid: str = "046D",
    pid: str = "C077",
    tecla: str | None = None,
    x: int | None = None,
    y: int | None = None,
    pasos: int | None = None,
) -> EventoValido:
    """Un evento válido para las pruebas. Por defecto, un clic del mouse Logitech B100 del esquema."""
    return EventoValido(tipo=tipo, hora=hora, dispositivo=dispositivo, vid=vid, pid=pid,
                        tecla=tecla, x=x, y=y, pasos=pasos)


def pulsacion(tecla: str, hora: str = "2026-11-02T08:00:00.100", pid: str = "C31C") -> EventoValido:
    """Una pulsación del teclado Logitech K120 del esquema (VID 046D, PID C31C)."""
    return evento_de_prueba("tecla_presionada", hora, "teclado", "046D", pid, tecla=tecla)


class Reloj:
    """Un reloj falso que solo avanza cuando la prueba lo pide."""

    def __init__(self, inicio: datetime | None = None) -> None:
        self._ahora: datetime = inicio or datetime(2026, 11, 2, 8, 0, 0)

    def __call__(self) -> datetime:
        return self._ahora

    def avanzar(self, segundos: float) -> None:
        self._ahora += timedelta(seconds=segundos)
