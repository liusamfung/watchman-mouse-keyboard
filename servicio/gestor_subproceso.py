"""Gestor del subproceso (RF2, RF3, RF10, RF21).

Lanza el capturador como subproceso, lee su stdout línea por línea en tiempo real,
entrega cada línea al validador y, si el capturador se cae, lo registra como
incidente y lo relanza esperando un poco más cada vez.

El gestor no conoce la base de datos: avisa por dos funciones que recibe al crearlo
(`al_evento` y `al_incidente`). Así el repositorio SQLite se conecta después sin
cambiar este módulo, y las pruebas pueden usar funciones simples.

Privacidad (RNF4): el stderr del capturador se descarta y nunca se copia a un incidente.
Los incidentes solo dicen qué pasó (por ejemplo, el código de salida), no el contenido.
"""
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import IO, Literal

from servicio.validador import EventoValido, validar_linea

type TipoIncidente = Literal["error_comunicacion", "evento_invalido", "caida_proceso"]

# Segundos que se espera antes de relanzar: 1.er fallo seguido, 2.º, 3.º y los siguientes.
ESPERAS_POR_DEFECTO: tuple[float, ...] = (1.0, 5.0, 15.0)

# Segundos que se le dan al capturador para cerrarse antes de forzarlo.
TIEMPO_DE_CIERRE = 2.0


@dataclass(frozen=True, slots=True)
class Incidente:
    """Algo que debe quedar registrado en la tabla `incidente` (RF9, RF10)."""

    tipo: TipoIncidente
    detalle: str
    accion: str | None = None


def _banderas_de_creacion() -> int:
    """En Windows evita que el capturador abra una ventana de consola (RNF11)."""
    if sys.platform == "win32":
        return subprocess.CREATE_NO_WINDOW
    return 0


def _terminar(proceso: "subprocess.Popen[str]") -> None:
    """Cierra el proceso con cortesía y, si no responde, a la fuerza."""
    if proceso.poll() is not None:
        return
    proceso.terminate()
    try:
        _ = proceso.wait(timeout=TIEMPO_DE_CIERRE)
    except subprocess.TimeoutExpired:
        proceso.kill()
        _ = proceso.wait()


class GestorSubproceso:
    """Mantiene vivo al capturador y reparte lo que escribe."""

    def __init__(
        self,
        comando: Sequence[str],
        al_evento: Callable[[EventoValido], None],
        al_incidente: Callable[[Incidente], None],
        esperas: Sequence[float] = ESPERAS_POR_DEFECTO,
        max_relanzamientos: int | None = None,
    ) -> None:
        """
        comando: programa y argumentos del capturador.
        al_evento: se llama con cada evento válido.
        al_incidente: se llama con cada línea rechazada y con cada caída.
        esperas: segundos antes de relanzar; el último valor se repite.
        max_relanzamientos: fallos seguidos permitidos antes de rendirse (None = sin límite).
            Un fallo "seguido" es una ejecución que no entregó ningún evento válido.
        """
        if not esperas:
            raise ValueError("esperas no puede estar vacía")
        self._comando: list[str] = list(comando)
        self._al_evento: Callable[[EventoValido], None] = al_evento
        self._al_incidente: Callable[[Incidente], None] = al_incidente
        self._esperas: tuple[float, ...] = tuple(esperas)
        self._max_relanzamientos: int | None = max_relanzamientos
        self._detener: threading.Event = threading.Event()
        self._candado: threading.Lock = threading.Lock()
        self._proceso: subprocess.Popen[str] | None = None
        self._hilo: threading.Thread | None = None

    # ---------- Control ----------

    def iniciar(self) -> None:
        """Empieza a lanzar y leer el capturador en un hilo propio (RF11)."""
        if self.esta_activo():
            raise RuntimeError("el gestor ya está en marcha")
        self._detener.clear()
        self._hilo = threading.Thread(target=self._ejecutar, name="gestor-subproceso", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        """Detiene el capturador y el hilo. Una parada pedida no se registra como caída."""
        self._detener.set()
        with self._candado:
            proceso = self._proceso
        if proceso is not None:
            _terminar(proceso)
        hilo = self._hilo
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(TIEMPO_DE_CIERRE * 3)

    def esta_activo(self) -> bool:
        return self._hilo is not None and self._hilo.is_alive()

    def esperar(self, tiempo: float | None = None) -> None:
        """Espera a que el hilo termine (por una parada o porque se rindió)."""
        if self._hilo is not None:
            self._hilo.join(tiempo)

    # ---------- Bucle principal ----------

    def _ejecutar(self) -> None:
        fallos_seguidos = 0
        while not self._detener.is_set():
            entrego_eventos, motivo = self._una_ejecucion()
            if self._detener.is_set():
                break  # la parada fue pedida: no es una caída
            fallos_seguidos = 0 if entrego_eventos else fallos_seguidos + 1

            if self._max_relanzamientos is not None and fallos_seguidos > self._max_relanzamientos:
                self._al_incidente(Incidente("caida_proceso", f"el capturador {motivo}", "se agotaron los relanzamientos"))
                break

            espera = self._esperas[min(max(fallos_seguidos - 1, 0), len(self._esperas) - 1)]
            self._al_incidente(Incidente("caida_proceso", f"el capturador {motivo}", f"relanzado en {espera:g} s"))
            if self._detener.wait(espera):
                break

    def _una_ejecucion(self) -> tuple[bool, str]:
        """Lanza el capturador y lee hasta que termine. Devuelve (entregó eventos, cómo terminó)."""
        with self._candado:
            if self._detener.is_set():
                return False, "no se lanzó porque se pidió detener"
            try:
                proceso: subprocess.Popen[str] = subprocess.Popen(
                    self._comando,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=_banderas_de_creacion(),
                )
            except OSError as error:
                return False, f"no se pudo iniciar ({type(error).__name__})"
            self._proceso = proceso

        entrego_eventos = False
        try:
            salida: IO[str] | None = proceso.stdout
            if salida is None:
                raise RuntimeError("el capturador no tiene stdout")
            for linea in salida:
                if self._procesar_linea(linea):
                    entrego_eventos = True
            codigo = proceso.wait()
        finally:
            _terminar(proceso)
            with self._candado:
                self._proceso = None
        return entrego_eventos, f"terminó con código {codigo}"

    def _procesar_linea(self, linea: str) -> bool:
        """Valida una línea y la entrega. Devuelve True si era un evento válido (RF9)."""
        resultado = validar_linea(linea)
        if isinstance(resultado, EventoValido):
            self._al_evento(resultado)
            return True
        self._al_incidente(Incidente(resultado.tipo_incidente, resultado.detalle, "línea descartada"))
        return False
