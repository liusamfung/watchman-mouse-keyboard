"""Guardador: recibe lo que entrega el gestor del subproceso y lo guarda en la base de datos.

Une las piezas del servicio (RF8, RF9, RF10, RF12, RF13, RF16, RF17, RF18):

- Cada evento válido identifica su periférico (modelo por VID/PID y unidad del equipo), suma al contador de
  desgaste, mide la actividad de la sesión y queda en una cola para guardarse.
- Cada cierto tiempo (por defecto 10 s, y siempre antes de cerrar) la cola, los contadores y la actividad se
  guardan juntos en una sola transacción. Si falla, nada se guarda a medias y se reintenta con todo (RNF12).
- Una falla de la base de datos nunca detiene al servicio ni se muestra al trabajador (RNF11): se cuenta en
  `errores_de_base` y se reintenta en el siguiente guardado.

Privacidad (RNF4): en la cola de eventos no viaja la tecla; el nombre de la tecla solo llega al contador.

Por qué dos candados de guardado: `_candado_eventos` protege la cola, que escriben el hilo del capturador
y el del guardado; `_candado_guardado` impide que dos guardados corran a la vez (el periódico y el de
`detener`), para no guardar dos veces lo mismo. La cola no queda bloqueada mientras se escribe en la base:
el hilo del capturador puede seguir agregando eventos durante un guardado.

Se relaciona con: usa `comun/repositorio.py` (guarda en `evento`, `contador_diario`, `sesion`,
`incidente`, `equipo`, `modelo_periferico` y `periferico`), `servicio/contador.py`, `servicio/sesion.py`,
`servicio/validador.py` (`EventoValido`) y `servicio/gestor_subproceso.py` (`Incidente`) · lo usan el
futuro `servicio/principal.py` (conectará `al_evento` y `al_incidente` con el gestor) y
`pruebas/test_guardador.py`.
"""
import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime

from comun.repositorio import EventoParaGuardar, Repositorio
from servicio.contador import ContadorDesgaste
from servicio.gestor_subproceso import Incidente
from servicio.sesion import ControlSesion, texto_iso
from servicio.validador import EventoValido

INTERVALO_DE_GUARDADO = 10.0  # segundos; RNF12 pide guardar los contadores al menos cada minuto
MAX_EVENTOS_PENDIENTES = 50_000  # si la base falla mucho tiempo, se descartan los eventos más viejos
ESPERA_AL_CERRAR = 5.0  # segundos que se espera al hilo del guardado periódico

type ClaveDispositivo = tuple[str, str, str]  # (vid, pid, dispositivo)


class Guardador:
    """Recibe eventos e incidentes del gestor y los guarda en la base, con sesión, contadores y reintentos."""

    def __init__(
        self,
        repositorio: Repositorio,
        nombre_equipo: str,
        reloj: Callable[[], datetime] = datetime.now,
        intervalo: float = INTERVALO_DE_GUARDADO,
        max_eventos_pendientes: int = MAX_EVENTOS_PENDIENTES,
    ) -> None:
        """
        repositorio: la base donde se guarda todo.
        nombre_equipo: nombre de esta PC; se crea en `equipo` la primera vez (RF18).
        reloj: hora actual; las pruebas lo reemplazan por uno falso.
        intervalo: segundos entre guardados periódicos.
        max_eventos_pendientes: tope de la cola; pasado ese número se descartan los más viejos.
        """
        self._repositorio: Repositorio = repositorio
        self._nombre_equipo: str = nombre_equipo
        self._reloj: Callable[[], datetime] = reloj
        self._intervalo: float = intervalo
        self._max_eventos_pendientes: int = max_eventos_pendientes

        self._contador: ContadorDesgaste = ContadorDesgaste()
        self._sesion: ControlSesion | None = None
        self._id_equipo: int | None = None
        self._perifericos: dict[ClaveDispositivo, int] = {}

        self._eventos: list[EventoParaGuardar] = []
        self._candado_eventos: threading.Lock = threading.Lock()
        self._candado_guardado: threading.Lock = threading.Lock()  # un solo guardado a la vez
        self._parar: threading.Event = threading.Event()
        self._hilo: threading.Thread | None = None

        # Datos de diagnóstico, pensados para la interfaz y las pruebas.
        self.sesiones_cerradas_al_iniciar: int = 0
        self.errores_de_base: int = 0
        self.eventos_perdidos: int = 0

    # ---------- Ciclo de vida ----------

    @property
    def id_sesion(self) -> int:
        """Id de la sesión abierta. Lanza RuntimeError si el guardador no está en marcha."""
        return self._sesion_abierta().id_sesion

    def iniciar(self) -> None:
        """Cierra las sesiones que quedaron abiertas, abre una nueva y empieza el guardado periódico."""
        if self._hilo is not None:
            raise RuntimeError("el guardador ya está en marcha")
        self.sesiones_cerradas_al_iniciar = self._repositorio.cerrar_sesiones_abiertas_como_inesperadas()
        self._id_equipo = self._repositorio.obtener_o_crear_equipo(self._nombre_equipo)
        sesion = ControlSesion(self._repositorio, self._id_equipo, self._reloj)
        _ = sesion.abrir()
        self._sesion = sesion

        self._parar.clear()
        self._hilo = threading.Thread(target=self._guardar_cada_intervalo, name="guardador", daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        """Hace un último guardado y cierra la sesión como "normal". Es seguro llamarlo más de una vez."""
        self._parar.set()
        hilo = self._hilo
        if hilo is not None and hilo is not threading.current_thread():
            hilo.join(ESPERA_AL_CERRAR)
        self._hilo = None
        sesion = self._sesion
        if sesion is None:
            return
        _ = self.guardar_pendiente()
        try:
            sesion.cerrar("normal")
        except sqlite3.Error:
            self._anotar_error()
        self._sesion = None

    def _guardar_cada_intervalo(self) -> None:
        """Bucle del hilo: guarda lo pendiente cada `intervalo` segundos hasta que se pide parar."""
        # `wait` hace de pausa y de señal de parada a la vez: devuelve True apenas se llama a `_parar.set()`.
        while not self._parar.wait(self._intervalo):
            _ = self.guardar_pendiente()

    # ---------- Lo que entrega el gestor del subproceso ----------

    def al_evento(self, evento: EventoValido) -> None:
        """Recibe un evento válido. Se llama desde el hilo que lee el capturador."""
        sesion = self._sesion_abierta()
        try:
            id_periferico = self._periferico_de(evento)
        except sqlite3.Error:
            self._anotar_error()
            return
        sesion.registrar_actividad(evento)
        self._contador.registrar(evento, id_periferico)
        with self._candado_eventos:
            self._eventos.append(
                EventoParaGuardar(sesion.id_sesion, id_periferico, evento.tipo, evento.hora, evento.x, evento.y)
            )
            self._recortar_eventos_pendientes()

    def al_incidente(self, incidente: Incidente) -> None:
        """Recibe una línea rechazada o una caída del capturador y la registra (RF9, RF10)."""
        sesion = self._sesion
        try:
            self._repositorio.guardar_incidente(
                incidente.tipo, texto_iso(self._reloj()), incidente.detalle, incidente.accion,
                sesion.id_sesion if sesion is not None else None,
            )
        except sqlite3.Error:
            self._anotar_error()

    # ---------- Guardado ----------

    def guardar_pendiente(self) -> bool:
        """Guarda eventos, contadores y actividad en una transacción. Devuelve False si falló y se reintentará."""
        with self._candado_guardado:
            sesion = self._sesion
            if sesion is None:
                return True
            with self._candado_eventos:
                eventos, self._eventos = self._eventos, []
            conteos = self._contador.tomar_pendientes()
            teclado, mouse = sesion.segundos_de_actividad()
            try:
                self._repositorio.guardar_lote(sesion.id_sesion, eventos, conteos, teclado, mouse)
            except sqlite3.Error:
                # Falló la transacción: nada quedó guardado a medias, así que se devuelve TODO a la cola y a
                # los contadores para reintentarlo en el siguiente guardado (RNF12).
                with self._candado_eventos:
                    self._eventos[:0] = eventos  # los viejos van primero
                    self._recortar_eventos_pendientes()
                self._contador.reponer(conteos)
                self._anotar_error()
                return False
            return True

    # ---------- Ayudas internas ----------

    def _sesion_abierta(self) -> ControlSesion:
        """La sesión en curso. Lanza RuntimeError si `iniciar()` todavía no se llamó (o ya se llamó a `detener()`)."""
        if self._sesion is None:
            raise RuntimeError("el guardador no está en marcha: llame a iniciar()")
        return self._sesion

    def _periferico_de(self, evento: EventoValido) -> int:
        """Id del periférico que generó el evento. La primera vez que se ve, lo crea "por_confirmar" (RF17, RF18)."""
        clave: ClaveDispositivo = (evento.vid, evento.pid, evento.dispositivo)
        conocido = self._perifericos.get(clave)
        if conocido is not None:
            return conocido
        if self._id_equipo is None:
            raise RuntimeError("el guardador no está en marcha: llame a iniciar()")
        id_modelo = self._repositorio.obtener_o_crear_modelo(evento.vid, evento.pid, evento.dispositivo)
        id_periferico, _ = self._repositorio.obtener_o_crear_periferico(
            self._id_equipo, id_modelo, texto_iso(self._reloj())
        )
        self._perifericos[clave] = id_periferico
        return id_periferico

    def _recortar_eventos_pendientes(self) -> None:
        """Descarta los eventos más viejos si se acumularon demasiados. Se llama con el candado de eventos tomado."""
        exceso = len(self._eventos) - self._max_eventos_pendientes
        if exceso > 0:
            del self._eventos[:exceso]
            self.eventos_perdidos += exceso

    def _anotar_error(self) -> None:
        """Cuenta una falla de la base. No se muestra nada al trabajador (RNF11); la cuenta queda para la interfaz."""
        with self._candado_eventos:
            self.errores_de_base += 1
