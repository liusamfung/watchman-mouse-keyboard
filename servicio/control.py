"""Controlador de captura (RF11): aplica la orden de iniciar o detener que deja la interfaz.

La interfaz y el servicio son dos procesos y no se llaman entre sí (decisión de arquitectura 1): se comunican solo por la
tabla `configuracion` de SQLite. Este módulo es la mitad del servicio de esa conversación. Usa tres claves:

- `orden_captura` (`iniciar` o `detener`): la escribe la interfaz (pantalla P01) y la lee el servicio.
- `estado_captura` (`capturando`, `detenida` o `cerrado`): la escribe el servicio para que la interfaz muestre lo que de verdad
  pasa y no solo lo que se pidió. Pedir "iniciar" no significa que el capturador ya esté corriendo. `detenida` es que el servicio
  sigue vivo pero no captura; `cerrado` es que el servicio terminó de forma ordenada.
- `latido_servicio` (fecha y hora): el servicio la actualiza en cada lectura. Si está vieja, el servicio no está en marcha
  (por ejemplo, se apagó el equipo de golpe), y la interfaz no debe decir "capturando" (`leer_estado`). Cuando el servicio se
  cierra bien deja el estado en `cerrado`, para que la interfaz no espere a que el latido venza.

Cómo funciona: `Controlador.aplicar_orden` lee la orden, inicia o detiene el gestor del subproceso solo si hace falta y publica
el estado y el latido. `iniciar` la aplica una vez de inmediato y después la repite cada `intervalo` segundos en un hilo propio;
`detener` para ese hilo y deja el estado en "cerrado". Si la orden falta (base nueva) se entiende "iniciar", que es el valor
por defecto de `schema.sql`; si tiene un texto desconocido, se ignora y la captura queda como estaba, para que un dato mal
escrito no apague el monitoreo por error.

Una falla de la base (por ejemplo, bloqueada unos segundos por la interfaz) nunca detiene al servicio ni se muestra al
trabajador (RNF11): se cuenta en `errores_de_base` y se reintenta en la siguiente lectura. El módulo no guarda ni imprime teclas.

Se relaciona con: usa `comun/repositorio.py` (`leer_configuracion` y `escribir_configuracion`) y `servicio/gestor_subproceso.py`
(a través de la interfaz `GestorDeCaptura`) · lo usan `servicio/principal.py`, `servicio/resumen.py`, la pantalla P01
(`ui/pantallas/pantalla_p01.py`, para escribir la orden y leer el estado) y `pruebas/test_control.py`.
"""
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from comun.repositorio import Repositorio

CLAVE_ORDEN = "orden_captura"
CLAVE_ESTADO = "estado_captura"
CLAVE_LATIDO = "latido_servicio"

ORDEN_INICIAR = "iniciar"
ORDEN_DETENER = "detener"
ESTADO_CAPTURANDO = "capturando"
ESTADO_DETENIDA = "detenida"
ESTADO_CERRADO = "cerrado"  # el servicio terminó de forma ordenada (no es lo mismo que "detenida": ahora no hay quien lea la orden)

INTERVALO_DE_LECTURA = 2.0  # segundos entre lecturas de la orden: lo que tarda en reaccionar el servicio al botón de la interfaz
LATIDOS_PERDIDOS = 5  # cuántos intervalos sin latido se toleran antes de decir que el servicio no está en marcha
ESPERA_AL_CERRAR = 10.0  # segundos que se espera al hilo al detener (el gestor puede tardar unos segundos en cerrar el capturador)


class GestorDeCaptura(Protocol):
    """Lo que el controlador necesita del gestor del subproceso. Con esta interfaz, las pruebas usan un gestor falso."""

    def iniciar(self) -> None:
        """Empieza a lanzar y leer el capturador."""
        ...

    def detener(self) -> None:
        """Detiene el capturador."""
        ...

    def esta_activo(self) -> bool:
        """True si el capturador está en marcha."""
        ...


@dataclass(frozen=True, slots=True)
class EstadoDelServicio:
    """Lo que la interfaz muestra en P01: qué se pidió, qué hace el servicio y si está vivo."""

    orden: str  # lo último que se pidió: iniciar o detener
    estado: str  # lo que el servicio dijo que hace: capturando o detenida
    ultimo_latido: str | None  # fecha y hora del último latido; None si el servicio nunca arrancó
    en_marcha: bool  # True si el latido es reciente y el servicio no se cerró

    @property
    def capturando(self) -> bool:
        """True solo si el servicio está vivo y dice que captura. Un estado "capturando" con latido viejo es un servicio caído."""
        return self.en_marcha and self.estado == ESTADO_CAPTURANDO


def leer_estado(
    repositorio: Repositorio,
    ahora: datetime | None = None,
    intervalo: float = INTERVALO_DE_LECTURA,
) -> EstadoDelServicio:
    """Lee de la base la orden, el estado y el latido, y decide si el servicio está en marcha.

    ahora: la hora que se toma como "ahora"; por defecto la del sistema (las pruebas pasan una fija).
    intervalo: cada cuántos segundos late el servicio; el servicio se da por caído tras `LATIDOS_PERDIDOS` intervalos sin latir.
    Lanza sqlite3.Error si la base no se puede leer; quien llama decide qué mostrar.
    """
    orden = repositorio.leer_configuracion(CLAVE_ORDEN) or ORDEN_INICIAR
    estado = repositorio.leer_configuracion(CLAVE_ESTADO) or ESTADO_DETENIDA
    latido = repositorio.leer_configuracion(CLAVE_LATIDO) or None
    en_marcha = False
    if latido is not None and estado != ESTADO_CERRADO:
        try:
            antiguedad = ((ahora or datetime.now()) - datetime.fromisoformat(latido)).total_seconds()
            en_marcha = antiguedad <= intervalo * LATIDOS_PERDIDOS
        except ValueError:
            en_marcha = False  # un latido ilegible se trata como servicio caído, no como un error que tumbe la pantalla
    return EstadoDelServicio(orden, estado, latido, en_marcha)


class Controlador:
    """Lee la orden de la interfaz y la aplica al gestor del subproceso. Se puede iniciar y detener varias veces."""

    def __init__(
        self,
        repositorio: Repositorio,
        gestor: GestorDeCaptura,
        intervalo: float = INTERVALO_DE_LECTURA,
        reloj: Callable[[], datetime] = datetime.now,
    ) -> None:
        """
        repositorio: la base donde la interfaz deja la orden y donde se publica el estado.
        gestor: quien lanza y detiene el capturador.
        intervalo: segundos entre lecturas de la orden.
        reloj: hora actual; las pruebas la reemplazan por una falsa.
        """
        self._repositorio: Repositorio = repositorio
        self._gestor: GestorDeCaptura = gestor
        self._intervalo: float = intervalo
        self._reloj: Callable[[], datetime] = reloj
        self._parar: threading.Event = threading.Event()
        self._hilo: threading.Thread | None = None
        self._estado_publicado: str | None = None
        self.errores_de_base: int = 0  # cuántas veces falló la base; para la interfaz y las pruebas

    # ---------- Ciclo de vida ----------

    def iniciar(self) -> None:
        """Aplica la orden una vez, de inmediato, y sigue leyéndola cada `intervalo` segundos en un hilo propio."""
        if self._hilo is not None:
            raise RuntimeError("el controlador ya está en marcha")
        self._parar.clear()
        self.aplicar_orden()
        self._hilo = threading.Thread(target=self._leer_cada_intervalo, name="controlador", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        """Deja de leer la orden y publica que el servicio se cerró. Es seguro llamarlo más de una vez.

        No detiene al gestor: eso lo hace quien cierra el servicio (`servicio/principal.py`), después de esto.
        """
        self._parar.set()
        hilo = self._hilo
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(ESPERA_AL_CERRAR)
        self._hilo = None
        self._publicar_estado(ESTADO_CERRADO)

    def _leer_cada_intervalo(self) -> None:
        """Bucle del hilo: aplica la orden cada `intervalo` segundos hasta que se pide parar."""
        # `wait` hace de pausa y de señal de parada a la vez: devuelve True apenas se llama a `_parar.set()`.
        while not self._parar.wait(self._intervalo):
            self.aplicar_orden()

    # ---------- La orden ----------

    def aplicar_orden(self) -> None:
        """Lee la orden y, si no coincide con lo que hace el gestor, lo inicia o lo detiene. Luego publica estado y latido."""
        try:
            orden = self._repositorio.leer_configuracion(CLAVE_ORDEN)
        except sqlite3.Error:
            self.errores_de_base += 1  # base bloqueada o ilegible: no se cambia nada y se reintenta en la próxima lectura
            return
        quiere_capturar = self._interpretar(orden)
        if quiere_capturar is not None:
            activo = self._gestor.esta_activo()
            if quiere_capturar and not activo:
                self._gestor.iniciar()
            elif not quiere_capturar and activo:
                self._gestor.detener()
        self._publicar_estado(ESTADO_CAPTURANDO if self._gestor.esta_activo() else ESTADO_DETENIDA)

    @staticmethod
    def _interpretar(orden: str | None) -> bool | None:
        """True si la orden pide capturar, False si pide detener, None si no se entiende (entonces no se cambia nada)."""
        if orden is None:
            return True  # base nueva sin la clave: vale el valor por defecto del esquema
        texto = orden.strip().lower()
        if texto == ORDEN_INICIAR:
            return True
        if texto == ORDEN_DETENER:
            return False
        return None

    def _publicar_estado(self, estado: str) -> None:
        """Escribe el latido y, solo si cambió, el estado de la captura. Una falla de la base se cuenta y no detiene nada."""
        try:
            self._repositorio.escribir_configuracion(CLAVE_LATIDO, self._reloj().isoformat(timespec="seconds"))
            if estado != self._estado_publicado:
                self._repositorio.escribir_configuracion(CLAVE_ESTADO, estado)
                self._estado_publicado = estado
        except sqlite3.Error:
            self.errores_de_base += 1
