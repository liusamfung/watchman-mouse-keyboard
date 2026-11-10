"""Control de la sesión (RF12).

Una sesión va desde que el servicio inicia (al iniciar sesión en Windows) hasta que el equipo se apaga.
Este módulo abre y cierra la sesión en la base y mide el tiempo de actividad del teclado y del mouse.

Cómo se mide la actividad: cuenta los **segundos distintos en los que hubo al menos un evento** de ese
dispositivo. Si se escribe de corrido durante 10 segundos, son 10 s de actividad; las pausas no suman. Así no
hay que elegir cuánto tiempo sin eventos significa "inactivo".

Cómo funciona: `abrir` crea la fila de `sesion`; `registrar_actividad` recibe cada evento y suma un segundo
solo si es el primero de su dispositivo en ese segundo (usa la hora del evento, no el reloj de la PC);
`cerrar` guarda el fin y los segundos acumulados. El reloj se recibe como parámetro para que las pruebas
puedan fijar la hora.

Se relaciona con: usa `comun/repositorio.py` (tabla `sesion`: `abrir_sesion` y `cerrar_sesion`) y
`servicio/validador.py` (`EventoValido`) · lo usa `servicio/guardador.py` y `pruebas/test_sesion.py`.
"""
import threading
from collections.abc import Callable
from datetime import datetime

from comun.repositorio import Repositorio
from servicio.validador import EventoValido


def texto_iso(momento: datetime) -> str:
    """Fecha y hora como se guardan las sesiones: 2026-11-02T08:15:30."""
    return momento.isoformat(timespec="seconds")


class ControlSesion:
    """La sesión de un equipo: se abre al iniciar el servicio y se cierra al detenerlo (RF12)."""

    def __init__(self, repositorio: Repositorio, id_equipo: int, reloj: Callable[[], datetime] = datetime.now) -> None:
        """
        repositorio: donde se guarda la sesión.
        id_equipo: equipo (fila de `equipo`) al que pertenece la sesión.
        reloj: devuelve la hora actual; en las pruebas se reemplaza por uno falso.
        """
        self._repositorio: Repositorio = repositorio
        self._id_equipo: int = id_equipo
        self._reloj: Callable[[], datetime] = reloj
        self._candado: threading.Lock = threading.Lock()
        self._id_sesion: int | None = None
        self._segundos: dict[str, int] = {"teclado": 0, "mouse": 0}
        self._ultimo_segundo: dict[str, str] = {}

    @property
    def id_sesion(self) -> int:
        """Id de la sesión abierta. Lanza RuntimeError si todavía no se llamó a `abrir`."""
        if self._id_sesion is None:
            raise RuntimeError("la sesión todavía no se abrió")
        return self._id_sesion

    def abrir(self) -> int:
        """Abre la sesión y devuelve su id."""
        self._id_sesion = self._repositorio.abrir_sesion(self._id_equipo, texto_iso(self._reloj()))
        return self._id_sesion

    def registrar_actividad(self, evento: EventoValido) -> None:
        """Suma un segundo de actividad si es el primer evento de ese dispositivo en ese segundo."""
        segundo = evento.hora[:19]  # AAAA-MM-DDTHH:MM:SS, sin los milisegundos
        with self._candado:
            if self._ultimo_segundo.get(evento.dispositivo) != segundo:
                self._ultimo_segundo[evento.dispositivo] = segundo
                self._segundos[evento.dispositivo] = self._segundos.get(evento.dispositivo, 0) + 1

    def segundos_de_actividad(self) -> tuple[int, int]:
        """(segundos de teclado, segundos de mouse) acumulados hasta ahora."""
        with self._candado:
            return self._segundos["teclado"], self._segundos["mouse"]

    def cerrar(self, tipo_cierre: str = "normal") -> None:
        """Cierra la sesión con la hora actual y la actividad acumulada."""
        teclado, mouse = self.segundos_de_actividad()
        self._repositorio.cerrar_sesion(self.id_sesion, texto_iso(self._reloj()), tipo_cierre, teclado, mouse)
