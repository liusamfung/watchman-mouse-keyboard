"""Contador de desgaste (RF16).

Cuenta en memoria cuántas veces se pulsó cada tecla, cada botón del mouse y cuántos pasos giró la rueda,
por periférico y por día. Cada cierto tiempo el guardador toma lo pendiente y lo suma en `contador_diario`.

Privacidad (RNF4): solo hay totales por tecla, nunca el orden ni el momento de cada pulsación. El nombre de la
tecla vive únicamente en memoria y en `contador_diario.elemento`; este módulo nunca lo escribe en un log y su
`repr` no lo muestra.
"""
import threading
from collections import Counter
from collections.abc import Iterable
from typing import override

from comun.repositorio import Conteo
from servicio.validador import EventoValido

type ClaveConteo = tuple[int, str, str, str]  # (id_periferico, fecha, tipo_conteo, elemento)

BOTONES_DEL_MOUSE = {"clic_izquierdo": "izquierdo", "clic_derecho": "derecho"}
ELEMENTO_RUEDA = "rueda"


def conteo_de(evento: EventoValido) -> tuple[str, str, int] | None:
    """Qué suma un evento: (tipo de conteo, elemento, cantidad). Devuelve None si no suma a ningún contador.

    Solo cuentan las pulsaciones, los clics y los pasos de la rueda. Soltar una tecla y mover el mouse no.
    """
    if evento.tipo == "tecla_presionada" and evento.tecla is not None:
        return "pulsacion_tecla", evento.tecla, 1
    boton = BOTONES_DEL_MOUSE.get(evento.tipo)
    if boton is not None:
        return "clic_boton", boton, 1
    if evento.tipo == "scroll" and evento.pasos:
        return "scroll_paso", ELEMENTO_RUEDA, abs(evento.pasos)
    return None


class ContadorDesgaste:
    """Acumula los conteos pendientes de guardar. Se puede usar desde varios hilos."""

    def __init__(self) -> None:
        self._candado: threading.Lock = threading.Lock()
        self._pendientes: Counter[ClaveConteo] = Counter()

    def registrar(self, evento: EventoValido, id_periferico: int) -> None:
        """Suma el evento al contador del día en que ocurrió (no al día en que se guarda)."""
        conteo = conteo_de(evento)
        if conteo is None:
            return
        tipo_conteo, elemento, cantidad = conteo
        clave: ClaveConteo = (id_periferico, evento.hora[:10], tipo_conteo, elemento)
        with self._candado:
            self._pendientes[clave] += cantidad

    def tomar_pendientes(self) -> list[Conteo]:
        """Entrega lo acumulado y lo deja en cero. Si no se pudo guardar, devolverlo con `reponer`."""
        with self._candado:
            pendientes, self._pendientes = self._pendientes, Counter()
        return [Conteo(id_periferico, fecha, tipo_conteo, elemento, cantidad)
                for (id_periferico, fecha, tipo_conteo, elemento), cantidad in pendientes.items()]

    def reponer(self, conteos: Iterable[Conteo]) -> None:
        """Devuelve conteos que no se pudieron guardar, para reintentarlos en el siguiente guardado."""
        with self._candado:
            for conteo in conteos:
                self._pendientes[(conteo.id_periferico, conteo.fecha, conteo.tipo_conteo, conteo.elemento)] += conteo.cantidad

    def cantidad_pendiente(self) -> int:
        """Cuántos contadores distintos hay pendientes (no cuántas pulsaciones)."""
        with self._candado:
            return len(self._pendientes)

    @override
    def __repr__(self) -> str:
        return f"ContadorDesgaste({self.cantidad_pendiente()} contadores pendientes)"
