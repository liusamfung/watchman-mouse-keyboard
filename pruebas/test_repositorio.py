"""Pruebas del repositorio SQLite. Cada prueba usa su propia base en una carpeta temporal.

Con qué datos: bases nuevas creadas desde `docs/base-de-datos/schema.sql` (con los modelos de ejemplo K120 y
B100), un equipo "PC-PRUEBA-01" y fechas fijas de noviembre de 2026; las teclas son inventadas. Comprueba:
creación de la base y de las diez tablas, los tres PRAGMA en cada conexión, equipos, modelos, periféricos y
etiquetas (RF17, RF18), sesiones y cierre de las que quedaron abiertas (RNF12), eventos e incidentes, que no
exista ningún lugar para guardar la tecla de un evento (RNF4), contadores diarios, configuración, el uso desde
varios hilos y que dos repositorios sobre el mismo archivo se vean entre sí (servicio e interfaz).

Se relaciona con: usa `comun/repositorio.py` y `docs/base-de-datos/schema.sql` · lo ejecuta pytest.
"""
import inspect
import sqlite3
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from comun.repositorio import (
    NOMBRE_DESCONOCIDO,
    VARIABLE_DE_RUTA,
    Conteo,
    EtiquetaDuplicada,
    EventoParaGuardar,
    Repositorio,
    ruta_por_defecto,
)

TABLAS = {"equipo", "modelo_periferico", "limite_modelo", "periferico", "sesion", "evento",
          "incidente", "contador_diario", "alerta", "configuracion"}


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta de una base que todavía no existe, dentro de una carpeta que tampoco existe."""
    return tmp_path / "datos" / "eventos.db"  # la carpeta "datos" aún no existe


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """Un repositorio sobre `ruta_db` que se cierra al terminar la prueba."""
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


def consultar(ruta: Path, sql: str, parametros: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    """Lee la base con una conexión aparte, como lo haría otro proceso."""
    conexion = sqlite3.connect(ruta)
    try:
        return cast(list[tuple[object, ...]], conexion.execute(sql, parametros).fetchall())
    finally:
        conexion.close()


def preparar_sesion_y_periferico(repo: Repositorio) -> tuple[int, int, int]:
    """Crea un equipo, un teclado conocido (Logitech K120 del esquema) y una sesión. Devuelve los tres ids."""
    equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
    periferico, _ = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")
    sesion = repo.abrir_sesion(equipo, "2026-11-02T08:00:01")
    return equipo, periferico, sesion


# ---------- Creación de la base y PRAGMA ----------

@pytest.mark.usefixtures("repo")  # la prueba solo necesita que la base ya esté creada
def test_crea_la_carpeta_el_archivo_y_las_diez_tablas(ruta_db: Path) -> None:
    assert ruta_db.is_file()
    nombres = {str(fila[0]) for fila in consultar(ruta_db, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert TABLAS <= nombres


def test_cada_conexion_tiene_wal_claves_foraneas_y_espera(repo: Repositorio) -> None:
    conexion = repo._conexion  # pyright: ignore[reportPrivateUsage]
    assert conexion.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    assert conexion.execute("PRAGMA foreign_keys").fetchone() == (1,)
    assert conexion.execute("PRAGMA busy_timeout").fetchone() == (5000,)


@pytest.mark.usefixtures("repo")  # la prueba solo necesita que la base ya esté creada
def test_una_conexion_a_una_base_que_ya_existe_tambien_tiene_los_pragma(ruta_db: Path) -> None:
    # La primera conexión recibe los PRAGMA desde schema.sql; la segunda solo los recibe si el repositorio los ejecuta.
    with Repositorio(ruta_db) as segunda:
        conexion = segunda._conexion  # pyright: ignore[reportPrivateUsage]
        assert conexion.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert conexion.execute("PRAGMA busy_timeout").fetchone() == (5000,)
        assert conexion.execute("PRAGMA journal_mode").fetchone() == ("wal",)
        with pytest.raises(sqlite3.IntegrityError):  # y por eso rechaza un evento sin sesión
            segunda.guardar_evento(9999, 9999, "clic_izquierdo", "2026-11-02T08:00:02.000")


def test_abrir_otra_vez_la_misma_base_conserva_los_datos(ruta_db: Path) -> None:
    with Repositorio(ruta_db) as primero:
        identificador = primero.obtener_o_crear_equipo("PC-CONTAB-014")
    with Repositorio(ruta_db) as segundo:
        assert segundo.obtener_o_crear_equipo("PC-CONTAB-014") == identificador


def test_sin_el_esquema_y_sin_base_explica_el_problema(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="esquema"):
        _ = Repositorio(tmp_path / "nueva.db", ruta_esquema=tmp_path / "no_existe.sql")


def test_la_configuracion_inicial_viene_del_esquema(repo: Repositorio) -> None:
    assert repo.leer_configuracion("umbral_aviso") == "90"
    assert repo.leer_configuracion("umbral_critico") == "100"
    assert repo.leer_configuracion("orden_captura") == "iniciar"
    assert repo.leer_configuracion("clave_que_no_existe") is None


def test_ruta_por_defecto_respeta_la_variable_de_entorno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(VARIABLE_DE_RUTA, str(tmp_path / "otra.db"))
    assert ruta_por_defecto() == tmp_path / "otra.db"
    monkeypatch.delenv(VARIABLE_DE_RUTA)
    assert ruta_por_defecto().name == "eventos.db"


# ---------- Equipos, modelos y periféricos ----------

def test_un_equipo_se_crea_una_sola_vez(repo: Repositorio) -> None:
    primero = repo.obtener_o_crear_equipo("PC-A")
    assert repo.obtener_o_crear_equipo("PC-A") == primero
    assert repo.obtener_o_crear_equipo("PC-B") != primero


def test_un_modelo_del_catalogo_se_reconoce_sin_duplicarlo(ruta_db: Path, repo: Repositorio) -> None:
    antes = consultar(ruta_db, "SELECT COUNT(*) FROM modelo_periferico")
    identificador = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")  # Logitech K120 del esquema
    assert consultar(ruta_db, "SELECT nombre FROM modelo_periferico WHERE id = ?", (identificador,)) == [("K120",)]
    assert consultar(ruta_db, "SELECT COUNT(*) FROM modelo_periferico") == antes


def test_un_modelo_desconocido_se_crea_sin_limites(ruta_db: Path, repo: Repositorio) -> None:
    identificador = repo.obtener_o_crear_modelo("0000", "0000", "teclado")
    assert repo.obtener_o_crear_modelo("0000", "0000", "teclado") == identificador
    fila = consultar(ruta_db, "SELECT fabricante, nombre, tipo FROM modelo_periferico WHERE id = ?", (identificador,))
    assert fila == [(NOMBRE_DESCONOCIDO, NOMBRE_DESCONOCIDO, "teclado")]
    assert consultar(ruta_db, "SELECT COUNT(*) FROM limite_modelo WHERE id_modelo = ?", (identificador,)) == [(0,)]


def test_un_periferico_nuevo_queda_por_confirmar_y_sin_etiqueta(ruta_db: Path, repo: Repositorio) -> None:
    equipo = repo.obtener_o_crear_equipo("PC-A")
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
    identificador, creado = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")
    assert creado
    fila = consultar(ruta_db, "SELECT estado_asignacion, etiqueta, activo FROM periferico WHERE id = ?", (identificador,))
    assert fila == [("por_confirmar", None, 1)]


def test_el_mismo_equipo_y_modelo_reutilizan_el_periferico(repo: Repositorio) -> None:
    equipo = repo.obtener_o_crear_equipo("PC-A")
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
    primero, _ = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")
    segundo, creado = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T09:00:00")
    assert (segundo, creado) == (primero, False)
    otro_modelo = repo.obtener_o_crear_modelo("046D", "C077", "mouse")
    assert repo.obtener_o_crear_periferico(equipo, otro_modelo, "2026-11-02T09:00:00")[0] != primero


def test_el_mismo_modelo_en_otro_equipo_es_otro_periferico(repo: Repositorio) -> None:
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
    en_a, _ = repo.obtener_o_crear_periferico(repo.obtener_o_crear_equipo("PC-A"), modelo, "2026-11-02T08:00:00")
    en_b, _ = repo.obtener_o_crear_periferico(repo.obtener_o_crear_equipo("PC-B"), modelo, "2026-11-02T08:00:00")
    assert en_a != en_b


def test_asignar_la_etiqueta_confirma_el_periferico(ruta_db: Path, repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    repo.asignar_etiqueta(periferico, "  TEC-0042 ")
    fila = consultar(ruta_db, "SELECT etiqueta, estado_asignacion FROM periferico WHERE id = ?", (periferico,))
    assert fila == [("TEC-0042", "confirmada")]


def test_una_etiqueta_repetida_se_rechaza(repo: Repositorio) -> None:
    equipo, teclado, _ = preparar_sesion_y_periferico(repo)
    mouse, _ = repo.obtener_o_crear_periferico(equipo, repo.obtener_o_crear_modelo("046D", "C077", "mouse"),
                                               "2026-11-02T08:00:00")
    repo.asignar_etiqueta(teclado, "TEC-0042")
    with pytest.raises(EtiquetaDuplicada):
        repo.asignar_etiqueta(mouse, "TEC-0042")


def test_etiqueta_vacia_o_periferico_inexistente_fallan(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    with pytest.raises(ValueError, match="vacía"):
        repo.asignar_etiqueta(periferico, "   ")
    with pytest.raises(LookupError):
        repo.asignar_etiqueta(9999, "TEC-0001")


# ---------- Sesiones ----------

def test_abrir_y_cerrar_una_sesion(ruta_db: Path, repo: Repositorio) -> None:
    equipo = repo.obtener_o_crear_equipo("PC-A")
    sesion = repo.abrir_sesion(equipo, "2026-11-02T08:00:00")
    assert consultar(ruta_db, "SELECT fin, tipo_cierre FROM sesion WHERE id = ?", (sesion,)) == [(None, None)]
    repo.actualizar_actividad_sesion(sesion, 120, 60)
    repo.cerrar_sesion(sesion, "2026-11-02T17:00:00", "normal", 3600, 1800)
    fila = consultar(ruta_db, "SELECT fin, tipo_cierre, seg_actividad_teclado, seg_actividad_mouse FROM sesion WHERE id = ?",
                     (sesion,))
    assert fila == [("2026-11-02T17:00:00", "normal", 3600, 1800)]


def test_un_tipo_de_cierre_invalido_se_rechaza(repo: Repositorio) -> None:
    sesion = repo.abrir_sesion(repo.obtener_o_crear_equipo("PC-A"), "2026-11-02T08:00:00")
    with pytest.raises(sqlite3.IntegrityError):
        repo.cerrar_sesion(sesion, "2026-11-02T17:00:00", "raro", 0, 0)


def test_las_sesiones_abiertas_se_cierran_como_inesperadas_con_el_ultimo_evento(ruta_db: Path, repo: Repositorio) -> None:
    equipo, periferico, con_eventos = preparar_sesion_y_periferico(repo)
    sin_eventos = repo.abrir_sesion(equipo, "2026-11-02T09:00:00")
    cerrada = repo.abrir_sesion(equipo, "2026-11-02T10:00:00")
    repo.cerrar_sesion(cerrada, "2026-11-02T10:30:00", "normal", 10, 10)
    repo.guardar_evento(con_eventos, periferico, "tecla_presionada", "2026-11-02T08:15:30.100")
    repo.guardar_evento(con_eventos, periferico, "tecla_liberada", "2026-11-02T08:15:30.200")

    assert repo.cerrar_sesiones_abiertas_como_inesperadas() == 2

    filas = consultar(ruta_db, "SELECT id, fin, tipo_cierre FROM sesion ORDER BY id")
    assert filas == [
        (con_eventos, "2026-11-02T08:15:30.200", "inesperado"),   # termina en su último evento
        (sin_eventos, "2026-11-02T09:00:00", "inesperado"),       # sin eventos: termina donde empezó
        (cerrada, "2026-11-02T10:30:00", "normal"),               # la que ya estaba cerrada no se toca
    ]
    incidentes = consultar(ruta_db, "SELECT id_sesion, tipo, accion FROM incidente ORDER BY id_sesion")
    assert incidentes == [
        (con_eventos, "apagado_inesperado", "sesión cerrada al iniciar el servicio"),
        (sin_eventos, "apagado_inesperado", "sesión cerrada al iniciar el servicio"),
    ]
    assert repo.cerrar_sesiones_abiertas_como_inesperadas() == 0  # una segunda vez no hay nada que cerrar


# ---------- Eventos e incidentes ----------

def test_guarda_un_movimiento_con_coordenadas_y_una_pulsacion_sin_ellas(ruta_db: Path, repo: Repositorio) -> None:
    _, periferico, sesion = preparar_sesion_y_periferico(repo)
    repo.guardar_evento(sesion, periferico, "mouse_movimiento", "2026-11-02T08:00:02.000", x=-300, y=40)
    repo.guardar_evento(sesion, periferico, "tecla_presionada", "2026-11-02T08:00:03.000")
    filas = consultar(ruta_db, "SELECT tipo_evento, x, y FROM evento ORDER BY id")
    assert filas == [("mouse_movimiento", -300, 40), ("tecla_presionada", None, None)]


def test_la_tabla_evento_y_guardar_evento_no_tienen_nada_de_teclas(ruta_db: Path) -> None:
    columnas = [str(fila[1]) for fila in consultar(ruta_db_con_esquema(ruta_db), "PRAGMA table_info(evento)")]
    assert not [c for c in columnas if "tecla" in c.lower() or "key" in c.lower()]
    parametros = set(inspect.signature(Repositorio.guardar_evento).parameters)
    assert not [p for p in parametros if "tecla" in p.lower()]
    assert "tecla" not in EventoParaGuardar.__dataclass_fields__


def ruta_db_con_esquema(ruta: Path) -> Path:
    """Crea en `ruta` una base con el esquema (abrir y cerrar un repositorio) y devuelve la misma ruta."""
    with Repositorio(ruta):
        pass
    return ruta


def test_un_evento_de_una_sesion_inexistente_se_rechaza(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    with pytest.raises(sqlite3.IntegrityError):
        repo.guardar_evento(9999, periferico, "clic_izquierdo", "2026-11-02T08:00:02.000")


def test_un_tipo_de_evento_desconocido_se_rechaza(repo: Repositorio) -> None:
    _, periferico, sesion = preparar_sesion_y_periferico(repo)
    with pytest.raises(sqlite3.IntegrityError):
        repo.guardar_evento(sesion, periferico, "mouse_arrastre", "2026-11-02T08:00:02.000")


def test_guardar_eventos_en_lote_es_todo_o_nada(ruta_db: Path, repo: Repositorio) -> None:
    _, periferico, sesion = preparar_sesion_y_periferico(repo)
    buenos = [EventoParaGuardar(sesion, periferico, "clic_izquierdo", f"2026-11-02T08:00:0{i}.000") for i in range(3)]
    repo.guardar_eventos(buenos)
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(3,)]

    con_error = [*buenos, EventoParaGuardar(sesion, periferico, "tipo_que_no_existe", "2026-11-02T08:00:09.000")]
    with pytest.raises(sqlite3.IntegrityError):
        repo.guardar_eventos(con_error)
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(3,)]  # no entró ninguno del lote


def test_guarda_incidentes_con_y_sin_sesion(ruta_db: Path, repo: Repositorio) -> None:
    _, _, sesion = preparar_sesion_y_periferico(repo)
    repo.guardar_incidente("caida_proceso", "2026-11-02T08:05:00", "terminó con código 3", "relanzado en 1 s", sesion)
    repo.guardar_incidente("evento_invalido", "2026-11-02T08:05:01", "falta el campo hora", "línea descartada")
    filas = consultar(ruta_db, "SELECT id_sesion, tipo, detalle, accion FROM incidente ORDER BY id")
    assert filas == [
        (sesion, "caida_proceso", "terminó con código 3", "relanzado en 1 s"),
        (None, "evento_invalido", "falta el campo hora", "línea descartada"),
    ]
    with pytest.raises(sqlite3.IntegrityError):
        repo.guardar_incidente("inventado", "2026-11-02T08:05:02")


# ---------- Contadores ----------

def test_los_contadores_se_suman_y_se_separan_por_dia_tecla_y_tipo(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    repo.sumar_a_contadores([
        Conteo(periferico, "2026-11-02", "pulsacion_tecla", "E", 10),
        Conteo(periferico, "2026-11-02", "pulsacion_tecla", "A", 4),
        Conteo(periferico, "2026-11-02", "clic_boton", "izquierdo", 7),
    ])
    repo.sumar_a_contadores([Conteo(periferico, "2026-11-02", "pulsacion_tecla", "E", 5)])   # mismo día: se suma
    repo.sumar_a_contadores([Conteo(periferico, "2026-11-03", "pulsacion_tecla", "E", 100)])  # otro día: fila nueva

    assert repo.total_acumulado(periferico, "pulsacion_tecla", "E") == 115
    assert repo.total_acumulado(periferico, "pulsacion_tecla", "A") == 4
    assert repo.total_acumulado(periferico, "pulsacion_tecla") == 119   # todo el teclado
    assert repo.total_acumulado(periferico, "clic_boton") == 7
    assert repo.totales_por_elemento(periferico, "pulsacion_tecla") == {"E": 115, "A": 4}


def test_un_total_sin_datos_es_cero(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    assert repo.total_acumulado(periferico, "scroll_paso") == 0
    assert repo.totales_por_elemento(periferico, "scroll_paso") == {}


def test_las_cantidades_deben_ser_positivas_y_el_lote_es_todo_o_nada(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    with pytest.raises(ValueError, match="mayor que cero"):
        repo.sumar_a_contadores([Conteo(periferico, "2026-11-02", "pulsacion_tecla", "E", 5),
                                 Conteo(periferico, "2026-11-02", "pulsacion_tecla", "A", 0)])
    assert repo.total_acumulado(periferico, "pulsacion_tecla") == 0


def test_un_conteo_no_muestra_la_tecla_al_imprimirse() -> None:
    conteo = Conteo(1, "2026-11-02", "pulsacion_tecla", "PAUSA", 3)
    assert "PAUSA" not in repr(conteo)
    assert "PAUSA" not in str(conteo)


# ---------- Configuración ----------

def test_escribir_configuracion_actualiza_y_crea(repo: Repositorio) -> None:
    repo.escribir_configuracion("umbral_aviso", "80")
    repo.escribir_configuracion("clave_nueva", "valor")
    assert repo.leer_configuracion("umbral_aviso") == "80"
    assert repo.leer_configuracion("clave_nueva") == "valor"


# ---------- Varios hilos y varios procesos ----------

def test_varios_hilos_pueden_guardar_a_la_vez(ruta_db: Path, repo: Repositorio) -> None:
    _, periferico, sesion = preparar_sesion_y_periferico(repo)
    errores: list[BaseException] = []

    def escribir(numero: int) -> None:
        """Lo que hace cada hilo: guarda 50 eventos y suma 50 clics; si algo falla, anota el error para la prueba."""
        try:
            for i in range(50):
                repo.guardar_evento(sesion, periferico, "clic_izquierdo", f"2026-11-02T08:{numero:02d}:{i:02d}.000")
                repo.sumar_a_contadores([Conteo(periferico, "2026-11-02", "clic_boton", "izquierdo", 1)])
        except BaseException as error:  # noqa: BLE001  (se anota para fallar la prueba desde el hilo principal)
            errores.append(error)

    hilos = [threading.Thread(target=escribir, args=(n,)) for n in range(6)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)

    assert errores == []
    assert consultar(ruta_db, "SELECT COUNT(*) FROM evento") == [(300,)]
    assert repo.total_acumulado(periferico, "clic_boton", "izquierdo") == 300


def test_dos_repositorios_sobre_el_mismo_archivo_se_ven_entre_si(ruta_db: Path, repo: Repositorio) -> None:
    # Imita al servicio (escribe) y a la interfaz (lee) como dos procesos con su propia conexión.
    with Repositorio(ruta_db) as interfaz:
        _, periferico, _ = preparar_sesion_y_periferico(repo)
        repo.sumar_a_contadores([Conteo(periferico, "2026-11-02", "pulsacion_tecla", "E", 9)])
        assert interfaz.total_acumulado(periferico, "pulsacion_tecla", "E") == 9
        interfaz.escribir_configuracion("orden_captura", "detener")   # la interfaz deja una orden
        assert repo.leer_configuracion("orden_captura") == "detener"  # el servicio la lee


def test_retirar_un_periferico_lo_marca_inactivo_y_deja_libre_su_lugar(ruta_db: Path, repo: Repositorio) -> None:
    equipo, periferico, _ = preparar_sesion_y_periferico(repo)
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")

    repo.retirar_periferico(periferico, "2026-11-05T18:00:00")

    assert consultar(ruta_db, "SELECT activo, fecha_retiro FROM periferico WHERE id = ?", (periferico,)) == [
        (0, "2026-11-05T18:00:00")
    ]
    nuevo, creado = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-06T08:00:00")   # el mismo modelo, otra unidad
    assert creado and nuevo != periferico


def test_no_se_puede_retirar_dos_veces_ni_uno_que_no_existe(repo: Repositorio) -> None:
    _, periferico, _ = preparar_sesion_y_periferico(repo)
    repo.retirar_periferico(periferico, "2026-11-05T18:00:00")

    with pytest.raises(LookupError):
        repo.retirar_periferico(periferico, "2026-11-06T18:00:00")
    with pytest.raises(LookupError):
        repo.retirar_periferico(999, "2026-11-06T18:00:00")
