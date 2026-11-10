"""Pruebas del guardador: de los eventos del capturador a las tablas de la base de datos.

Con qué datos: una base SQLite nueva en una carpeta temporal por prueba, un `Reloj` falso con la hora fija
2026-11-02 08:00:00, eventos armados con `evento_de_prueba` y `pulsacion` (teclas inventadas) y, en la última
prueba, el capturador simulado de Python conectado de punta a punta. Comprueba: inicio y fin de la sesión,
creación de modelos y periféricos "por confirmar", guardado de eventos, contadores y actividad, que guardar dos
veces no duplique, que la tecla solo exista en `contador_diario` (RNF4), reintentos si la base falla (RNF12),
que una falla de la base no detenga al servicio (RNF11) y el descarte de los eventos más viejos si la cola
se llena.

Se relaciona con: usa `servicio/guardador.py`, `comun/repositorio.py`, `servicio/gestor_subproceso.py`,
`pruebas/ayudas_base.py` y `pruebas/capturador_simulado.py` · lo ejecuta pytest.
"""
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pytest

from comun.repositorio import Conteo, EventoParaGuardar, Repositorio
from pruebas.ayudas_base import Reloj, consultar, evento_de_prueba, pulsacion
from servicio.gestor_subproceso import GestorSubproceso, Incidente
from servicio.guardador import Guardador

SIMULADOR = str(Path(__file__).parent / "capturador_simulado.py")
TIEMPO_MAXIMO = 15.0


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta de una base que todavía no existe, dentro de la carpeta temporal de la prueba."""
    return tmp_path / "eventos.db"


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """Un repositorio sobre `ruta_db` que se cierra al terminar la prueba."""
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


@pytest.fixture
def reloj() -> Reloj:
    """Un reloj falso que parte el 2026-11-02 a las 08:00:00."""
    return Reloj()


@pytest.fixture
def guardadores() -> Iterator[list[Guardador]]:
    """Garantiza que ningún hilo de guardado quede vivo al terminar la prueba."""
    creados: list[Guardador] = []
    yield creados
    for guardador in creados:
        guardador.detener()


def crear(guardadores: list[Guardador], repo: Repositorio, reloj: Reloj, **opciones: float | int) -> Guardador:
    """Un guardador de la computadora PC-PRUEBA-01, con guardado periódico muy espaciado salvo que se pida otro."""
    intervalo = float(opciones.get("intervalo", 1000.0))
    maximo = int(opciones.get("max_eventos_pendientes", 50_000))
    guardador = Guardador(repo, "PC-PRUEBA-01", reloj, intervalo, maximo)
    guardadores.append(guardador)
    return guardador


def esperar(condicion: Callable[[], bool], tiempo: float = TIEMPO_MAXIMO) -> bool:
    """Revisa `condicion` cada 20 ms hasta `tiempo` segundos. Devuelve True apenas se cumple, False si se acaba el tiempo."""
    limite = time.monotonic() + tiempo
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.02)
    return False


# ---------- Inicio y fin del servicio ----------

def test_al_iniciar_cierra_las_sesiones_viejas_y_abre_una_nueva(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    vieja = repo.abrir_sesion(repo.obtener_o_crear_equipo("PC-PRUEBA-01"), "2026-11-01T08:00:00")
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()

    assert guardador.sesiones_cerradas_al_iniciar == 1
    assert consultar(ruta_db, "SELECT fin, tipo_cierre FROM sesion WHERE id = ?", (vieja,)) == [
        ("2026-11-01T08:00:00", "inesperado")
    ]
    assert consultar(ruta_db, "SELECT inicio, fin FROM sesion WHERE id = ?", (guardador.id_sesion,)) == [
        ("2026-11-02T08:00:00", None)
    ]


def test_no_se_puede_iniciar_dos_veces_ni_usar_antes_de_iniciar(
    repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    with pytest.raises(RuntimeError, match="iniciar"):
        guardador.al_evento(pulsacion("E"))
    guardador.iniciar()
    with pytest.raises(RuntimeError, match="en marcha"):
        guardador.iniciar()


def test_detener_guarda_lo_pendiente_y_cierra_la_sesion(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    identificador = guardador.id_sesion
    guardador.al_evento(pulsacion("E", "2026-11-02T08:00:01.100"))
    guardador.al_evento(evento_de_prueba("clic_izquierdo", "2026-11-02T08:00:02.200"))
    reloj.avanzar(7200)

    guardador.detener()

    sesion = consultar(
        ruta_db, "SELECT fin, tipo_cierre, seg_actividad_teclado, seg_actividad_mouse FROM sesion WHERE id = ?",
        (identificador,),
    )
    assert sesion == [("2026-11-02T10:00:00", "normal", 1, 1)]
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(2,)]
    guardador.detener()  # una segunda vez no hace nada ni falla
    with pytest.raises(RuntimeError):
        _ = guardador.id_sesion


# ---------- Qué se guarda ----------

def test_un_dispositivo_nuevo_crea_su_modelo_y_su_periferico_por_confirmar(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    guardador.al_evento(evento_de_prueba("clic_izquierdo", vid="0000", pid="0000"))  # dispositivo virtual
    guardador.al_evento(evento_de_prueba("clic_derecho", vid="0000", pid="0000"))

    modelos = consultar(ruta_db, "SELECT nombre, tipo FROM modelo_periferico WHERE vid = '0000'")
    assert modelos == [("desconocido", "mouse")]
    perifericos = consultar(
        ruta_db,
        """
        SELECT p.estado_asignacion, p.etiqueta
        FROM periferico p JOIN modelo_periferico m ON m.id = p.id_modelo
        WHERE m.vid = '0000'
        """,
    )
    assert perifericos == [("por_confirmar", None)]  # los dos clics usaron el mismo periférico


def test_un_modelo_del_catalogo_se_reutiliza(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    modelos_antes = consultar(ruta_db, "SELECT COUNT(*) FROM modelo_periferico")
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    guardador.al_evento(pulsacion("E"))   # Logitech K120, que ya está en el esquema
    assert consultar(ruta_db, "SELECT COUNT(*) FROM modelo_periferico") == modelos_antes


def test_guardar_pendiente_graba_eventos_contadores_y_actividad(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    for tecla in ("E", "E", "A"):
        guardador.al_evento(pulsacion(tecla, "2026-11-02T08:00:05.000"))
    guardador.al_evento(evento_de_prueba("mouse_movimiento", "2026-11-02T08:00:06.000", x=-300, y=40))
    guardador.al_evento(evento_de_prueba("scroll", "2026-11-02T08:00:06.500", pasos=-3))

    assert guardador.guardar_pendiente()

    assert consultar(ruta_db, "SELECT tipo_evento, x, y FROM evento ORDER BY id") == [
        ("tecla_presionada", None, None), ("tecla_presionada", None, None), ("tecla_presionada", None, None),
        ("mouse_movimiento", -300, 40), ("scroll", None, None),
    ]
    contadores = consultar(ruta_db, "SELECT tipo_conteo, elemento, cantidad FROM contador_diario ORDER BY 1, 2")
    assert contadores == [("pulsacion_tecla", "A", 1), ("pulsacion_tecla", "E", 2), ("scroll_paso", "rueda", 3)]
    actividad = consultar(ruta_db, "SELECT seg_actividad_teclado, seg_actividad_mouse FROM sesion WHERE fin IS NULL")
    assert actividad == [(1, 1)]


def test_guardar_dos_veces_no_duplica_nada(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    guardador.al_evento(pulsacion("E"))
    assert guardador.guardar_pendiente()
    assert guardador.guardar_pendiente()
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(1,)]
    assert repo.total_acumulado(guardador_periferico(ruta_db), "pulsacion_tecla", "E") == 1


def guardador_periferico(ruta_db: Path) -> int:
    """El id del primer periférico que el guardador creó en la base."""
    fila = consultar(ruta_db, "SELECT id FROM periferico ORDER BY id LIMIT 1")
    identificador = fila[0][0]
    assert isinstance(identificador, int)
    return identificador


def test_la_tecla_solo_existe_en_contador_diario(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    guardador.al_evento(pulsacion("CLAVEULTRASECRETA"))
    guardador.al_evento(evento_de_prueba("clic_izquierdo"))
    guardador.detener()

    nombres = consultar(ruta_db, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")
    tablas = [str(fila[0]) for fila in nombres]
    for tabla in tablas:
        filas = consultar(ruta_db, f"SELECT * FROM {tabla}")  # noqa: S608  (el nombre sale de sqlite_master)
        contiene = any("CLAVEULTRASECRETA" in str(valor) for fila in filas for valor in fila)
        assert contiene == (tabla == "contador_diario"), f"la tecla {'apareció en' if contiene else 'falta en'} {tabla}"


def test_los_incidentes_se_guardan_con_la_sesion_y_la_hora_del_reloj(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    reloj.avanzar(30)
    guardador.al_incidente(Incidente("caida_proceso", "el capturador terminó con código 3", "relanzado en 1 s"))
    assert consultar(ruta_db, "SELECT id_sesion, tipo, fecha_hora, detalle, accion FROM incidente") == [
        (guardador.id_sesion, "caida_proceso", "2026-11-02T08:00:30",
         "el capturador terminó con código 3", "relanzado en 1 s")
    ]


# ---------- Guardado periódico ----------

def test_el_guardado_periodico_graba_sin_que_nadie_lo_pida(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj, intervalo=0.05)
    guardador.iniciar()
    guardador.al_evento(pulsacion("E"))
    assert esperar(lambda: consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(1,)])
    assert esperar(lambda: consultar(ruta_db, "SELECT cantidad FROM contador_diario") == [(1,)])


# ---------- Fallas de la base de datos (RNF11, RNF12) ----------

def test_si_el_guardado_falla_se_reintenta_con_todo_y_sin_duplicar(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador], monkeypatch: pytest.MonkeyPatch,
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()
    original = repo.guardar_lote
    intentos: list[int] = []

    def guardar_lote_con_una_falla(
        id_sesion: int, eventos: Iterable[EventoParaGuardar], conteos: Iterable[Conteo], seg_teclado: int, seg_mouse: int,
    ) -> None:
        """Reemplaza a `guardar_lote`: falla la primera vez (como si la base estuviera bloqueada) y después guarda de verdad."""
        intentos.append(1)
        if len(intentos) == 1:
            raise sqlite3.OperationalError("database is locked")
        original(id_sesion, eventos, conteos, seg_teclado, seg_mouse)

    monkeypatch.setattr(repo, "guardar_lote", guardar_lote_con_una_falla)
    guardador.al_evento(pulsacion("E"))
    guardador.al_evento(pulsacion("E"))

    assert not guardador.guardar_pendiente()                       # falla: la base está bloqueada
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(0,)]
    assert guardador.errores_de_base == 1

    guardador.al_evento(pulsacion("E"))                            # llega otro mientras tanto
    assert guardador.guardar_pendiente()                           # el reintento guarda los tres
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(3,)]
    assert consultar(ruta_db, "SELECT cantidad FROM contador_diario") == [(3,)]


def test_una_falla_al_registrar_un_incidente_o_un_dispositivo_no_detiene_al_servicio(
    repo: Repositorio, reloj: Reloj, guardadores: list[Guardador], monkeypatch: pytest.MonkeyPatch,
) -> None:
    guardador = crear(guardadores, repo, reloj)
    guardador.iniciar()

    def bloqueada(*_argumentos: object) -> int:
        """Reemplaza a un método del repositorio y siempre falla, como una base bloqueada."""
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repo, "guardar_incidente", bloqueada)
    monkeypatch.setattr(repo, "obtener_o_crear_modelo", bloqueada)

    guardador.al_incidente(Incidente("evento_invalido", "falta el campo hora", "línea descartada"))
    guardador.al_evento(evento_de_prueba("clic_izquierdo", vid="1234", pid="5678"))   # dispositivo nunca visto

    assert guardador.errores_de_base == 2   # se anotaron, pero ninguna llamada lanzó una excepción


def test_si_la_base_falla_mucho_tiempo_se_descartan_los_eventos_mas_viejos(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj, max_eventos_pendientes=5)
    guardador.iniciar()
    for segundo in range(8):
        guardador.al_evento(evento_de_prueba("clic_izquierdo", f"2026-11-02T08:00:0{segundo}.000"))

    assert guardador.eventos_perdidos == 3
    assert guardador.guardar_pendiente()
    horas = [str(fila[0]) for fila in consultar(ruta_db, "SELECT fecha_hora FROM evento ORDER BY fecha_hora")]
    assert horas[0] == "2026-11-02T08:00:03.000" and horas[-1] == "2026-11-02T08:00:07.000"   # se conservan los 5 nuevos
    assert repo.total_acumulado(guardador_periferico(ruta_db), "clic_boton", "izquierdo") == 8   # los conteos no se pierden


# ---------- El servicio completo ----------

def test_del_capturador_simulado_a_la_base_de_datos(
    ruta_db: Path, repo: Repositorio, reloj: Reloj, guardadores: list[Guardador],
) -> None:
    guardador = crear(guardadores, repo, reloj, intervalo=0.2)
    guardador.iniciar()
    comando = [sys.executable, SIMULADOR, "--intervalo", "0.001", "--semilla", "4", "--proporcion-invalidos", "0.1"]
    gestor = GestorSubproceso(comando, guardador.al_evento, guardador.al_incidente)
    gestor.iniciar()
    try:
        # Espera a que haya al menos 200 eventos guardados por el hilo periódico (`in range(200, 10**9)` es "200 o más").
        assert esperar(lambda: consultar(ruta_db, "SELECT COUNT(*) FROM evento")[0][0] in range(200, 10**9))
    finally:
        gestor.detener()
        guardador.detener()

    # Lo que se contó coincide con lo que se guardó: las dos cuentas salen de los mismos eventos.
    def suma(tipo_conteo: str) -> object:
        """El total guardado en `contador_diario` para ese tipo de conteo (0 si no hay filas)."""
        return consultar(ruta_db, "SELECT COALESCE(SUM(cantidad), 0) FROM contador_diario WHERE tipo_conteo = ?",
                         (tipo_conteo,))[0][0]

    assert suma("pulsacion_tecla") == consultar(
        ruta_db, "SELECT COUNT(*) FROM evento WHERE tipo_evento = 'tecla_presionada'")[0][0]
    assert suma("clic_boton") == consultar(
        ruta_db, "SELECT COUNT(*) FROM evento WHERE tipo_evento IN ('clic_izquierdo', 'clic_derecho')")[0][0]

    sesion = consultar(
        ruta_db,
        """
        SELECT fin IS NOT NULL, tipo_cierre, seg_actividad_teclado > 0, seg_actividad_mouse > 0
        FROM sesion ORDER BY id DESC LIMIT 1
        """,
    )
    assert sesion == [(1, "normal", 1, 1)]
    assert consultar(ruta_db, "SELECT estado_asignacion, etiqueta FROM periferico") == [("por_confirmar", None)] * 2
    tipos = {str(fila[0]) for fila in consultar(ruta_db, "SELECT DISTINCT tipo FROM incidente")}
    assert tipos == {"error_comunicacion", "evento_invalido"}   # las líneas malas quedaron registradas
