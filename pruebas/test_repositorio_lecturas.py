"""Pruebas de las lecturas y de las operaciones de alertas del repositorio SQLite.

Con qué datos: una base nueva por prueba (con los modelos de ejemplo K120 y B100 de schema.sql), un equipo
"PC-PRUEBA-01", fechas fijas de noviembre de 2026 (el 2 es lunes) y teclas inventadas ("Q", "W"). Comprueba:
el desgaste y el porcentaje de cada periférico (con límite, sin límite y retirados), las sesiones y su total del
día, los incidentes recientes, el ciclo de vida de una alerta (crear sin duplicar, intentos, envío), las horas de
los eventos para el mapa de calor, las filas de los reportes CSV, la validación de los rangos de fechas y que
ninguna lectura de eventos traiga la tecla (RNF4).

Se relaciona con: usa `comun/repositorio.py` y `pruebas/ayudas_base.py` · lo ejecuta pytest. Las pruebas de
escritura del mismo módulo están en `pruebas/test_repositorio.py`.
"""
import dataclasses
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from comun.repositorio import (
    Conteo,
    FilaAlerta,
    FilaIncidente,
    FilaSesion,
    Repositorio,
    ResumenPeriferico,
    UsoDeConteo,
)
from pruebas.ayudas_base import consultar


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta de una base que todavía no existe, dentro de la carpeta temporal de la prueba."""
    return tmp_path / "eventos.db"


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """Un repositorio sobre `ruta_db` que se cierra al terminar la prueba."""
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


def ejecutar(ruta: Path, sql: str, parametros: tuple[object, ...] = ()) -> None:
    """Escribe en la base con una conexión aparte. Sirve para preparar casos que el repositorio no permite (retirar un periférico)."""
    conexion = sqlite3.connect(ruta)
    try:
        with conexion:
            _ = conexion.execute(sql, parametros)
    finally:
        conexion.close()


def crear_teclado(repo: Repositorio) -> tuple[int, int]:
    """Un equipo con un teclado Logitech K120 del esquema (límite de 20 000 pulsaciones). Devuelve (id equipo, id periférico)."""
    equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    modelo = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
    periferico, _ = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")
    return equipo, periferico


def crear_mouse(repo: Repositorio, equipo: int) -> int:
    """Un mouse Logitech B100 del esquema (límites de 10 000 clics y 15 000 pasos de rueda) en ese equipo."""
    modelo = repo.obtener_o_crear_modelo("046D", "C077", "mouse")
    periferico, _ = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")
    return periferico


# ---------- Periféricos y límites ----------


def test_un_periferico_muestra_su_desgaste_frente_al_limite_de_su_modelo(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    repo.sumar_a_contadores([
        Conteo(teclado, "2026-11-02", "pulsacion_tecla", "Q", 3000),
        Conteo(teclado, "2026-11-03", "pulsacion_tecla", "W", 2000),
        Conteo(teclado, "2026-11-03", "pulsacion_tecla", "Q", 500),   # la misma tecla, otro día: se suma
    ])

    resumen = repo.obtener_periferico(teclado)

    assert resumen is not None
    assert (resumen.fabricante, resumen.modelo, resumen.tipo, resumen.vid, resumen.pid) == ("Logitech", "K120", "teclado", "046D", "C31C")
    assert (resumen.etiqueta, resumen.estado_asignacion, resumen.activo) == (None, "por_confirmar", True)
    # El límite es por tecla: la más gastada lleva 3 500 de 20 000 (17,5 %), aunque entre todas sumen 5 500.
    assert resumen.usos == (UsoDeConteo("pulsacion_tecla", total=5500, mayor_uso=3500, limite=20000),)
    assert resumen.usos[0].porcentaje == 17.5
    assert resumen.porcentaje_maximo == 17.5


def test_el_porcentaje_sale_de_la_tecla_mas_gastada_y_no_de_la_suma_de_todas(repo: Repositorio) -> None:
    """Caso del error que se corrigió: 40 teclas con 1 000 pulsaciones cada una suman más que el límite de una tecla."""
    _, teclado = crear_teclado(repo)
    repo.sumar_a_contadores([Conteo(teclado, "2026-11-02", "pulsacion_tecla", f"TECLA_{n:02d}", 1000) for n in range(40)])

    resumen = repo.obtener_periferico(teclado)

    assert resumen is not None
    assert resumen.usos == (UsoDeConteo("pulsacion_tecla", total=40000, mayor_uso=1000, limite=20000),)
    assert resumen.porcentaje_maximo == 5.0   # y no 200 %: ninguna tecla está cerca de agotarse


def test_un_mouse_lista_todos_sus_limites_aunque_no_tenga_conteos_de_alguno(repo: Repositorio) -> None:
    equipo, _ = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)
    repo.sumar_a_contadores([Conteo(mouse, "2026-11-02", "clic_boton", "izquierdo", 100)])

    resumen = repo.obtener_periferico(mouse)

    assert resumen is not None
    assert resumen.usos == (
        UsoDeConteo("clic_boton", total=100, mayor_uso=100, limite=10000),
        UsoDeConteo("scroll_paso", total=0, mayor_uso=0, limite=15000),
    )
    assert resumen.porcentaje_maximo == 1.0


def test_un_modelo_sin_limites_muestra_su_desgaste_sin_porcentaje(repo: Repositorio) -> None:
    equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    modelo = repo.obtener_o_crear_modelo("1234", "5678", "mouse")   # modelo desconocido: se crea sin límites
    desconocido, _ = repo.obtener_o_crear_periferico(equipo, modelo, "2026-11-02T08:00:00")

    sin_uso = repo.obtener_periferico(desconocido)
    assert sin_uso is not None and sin_uso.usos == ()
    assert sin_uso.porcentaje_maximo is None

    repo.sumar_a_contadores([Conteo(desconocido, "2026-11-02", "clic_boton", "izquierdo", 7)])
    con_uso = repo.obtener_periferico(desconocido)
    assert con_uso is not None
    assert con_uso.usos == (UsoDeConteo("clic_boton", total=7, mayor_uso=7, limite=None),)
    assert con_uso.usos[0].porcentaje is None
    assert con_uso.porcentaje_maximo is None


def test_el_porcentaje_puede_pasar_de_cien(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    repo.sumar_a_contadores([Conteo(teclado, "2026-11-02", "pulsacion_tecla", "Q", 25000)])

    resumen = repo.obtener_periferico(teclado)

    assert resumen is not None and resumen.porcentaje_maximo == 125.0


def test_listar_perifericos_pone_primero_los_activos_y_puede_ocultar_los_retirados(repo: Repositorio, ruta_db: Path) -> None:
    equipo, teclado = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)
    ejecutar(ruta_db, "UPDATE periferico SET activo = 0, fecha_retiro = ? WHERE id = ?", ("2026-11-05T09:00:00", teclado))

    todos = repo.listar_perifericos()
    activos = repo.listar_perifericos(incluir_retirados=False)

    assert [p.id for p in todos] == [mouse, teclado]
    assert [p.id for p in activos] == [mouse]
    assert (todos[1].activo, todos[1].fecha_retiro) == (False, "2026-11-05T09:00:00")


def test_listar_perifericos_puede_filtrar_por_equipo(repo: Repositorio) -> None:
    equipo, teclado = crear_teclado(repo)
    otro_equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-02")
    mouse_del_otro = crear_mouse(repo, otro_equipo)

    assert [p.id for p in repo.listar_perifericos(id_equipo=equipo)] == [teclado]
    assert [p.id for p in repo.listar_perifericos(id_equipo=otro_equipo)] == [mouse_del_otro]
    assert len(repo.listar_perifericos()) == 2


def test_un_periferico_que_no_existe_devuelve_none(repo: Repositorio) -> None:
    assert repo.obtener_periferico(999) is None


def test_la_etiqueta_confirmada_aparece_en_el_resumen(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    repo.asignar_etiqueta(teclado, "TEC-0042")

    resumen = repo.obtener_periferico(teclado)

    assert resumen is not None
    assert (resumen.etiqueta, resumen.estado_asignacion) == ("TEC-0042", "confirmada")


def test_limites_del_periferico_son_los_de_su_modelo(repo: Repositorio) -> None:
    equipo, teclado = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)

    assert repo.limites_del_periferico(teclado) == {"pulsacion_tecla": 20000}
    assert repo.limites_del_periferico(mouse) == {"clic_boton": 10000, "scroll_paso": 15000}
    assert repo.limites_del_periferico(999) == {}


# ---------- Sesiones e incidentes ----------


def preparar_sesiones(repo: Repositorio) -> tuple[int, list[int]]:
    """Tres sesiones el lunes 2 (una cerrada, una en curso y una que cruza la medianoche) y una el martes 3."""
    equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    cerrada = repo.abrir_sesion(equipo, "2026-11-02T08:00:00")
    repo.cerrar_sesion(cerrada, "2026-11-02T12:00:00", "normal", 100, 20)
    en_curso = repo.abrir_sesion(equipo, "2026-11-02T14:00:00")
    repo.actualizar_actividad_sesion(en_curso, 50, 5)
    nocturna = repo.abrir_sesion(equipo, "2026-11-02T23:30:00")
    repo.cerrar_sesion(nocturna, "2026-11-03T01:00:00", "inesperado", 10, 0)
    martes = repo.abrir_sesion(equipo, "2026-11-03T08:00:00")
    return equipo, [cerrada, en_curso, nocturna, martes]


def test_listar_sesiones_va_de_la_mas_reciente_a_la_mas_antigua(repo: Repositorio) -> None:
    _, (cerrada, en_curso, nocturna, martes) = preparar_sesiones(repo)

    sesiones = repo.listar_sesiones()

    assert [s.id for s in sesiones] == [martes, nocturna, en_curso, cerrada]
    assert sesiones[3] == FilaSesion(cerrada, sesiones[3].id_equipo, "2026-11-02T08:00:00", "2026-11-02T12:00:00", "normal", 100, 20)
    assert sesiones[2].en_curso and (sesiones[2].tipo_cierre, sesiones[2].seg_actividad_teclado) == (None, 50)
    assert not sesiones[1].en_curso and sesiones[1].tipo_cierre == "inesperado"


def test_las_sesiones_de_un_dia_son_las_que_empezaron_ese_dia(repo: Repositorio) -> None:
    _, (cerrada, en_curso, nocturna, martes) = preparar_sesiones(repo)

    assert [s.id for s in repo.listar_sesiones(dia="2026-11-02")] == [nocturna, en_curso, cerrada]
    assert [s.id for s in repo.listar_sesiones(dia="2026-11-03")] == [martes]   # la nocturna cuenta en su día de inicio
    assert repo.listar_sesiones(dia="2026-11-10") == []


def test_la_actividad_del_dia_es_la_suma_de_sus_sesiones(repo: Repositorio) -> None:
    _ = preparar_sesiones(repo)

    assert repo.actividad_del_dia("2026-11-02") == (160, 25)   # 100 + 50 + 10 de teclado; 20 + 5 + 0 de mouse
    assert repo.actividad_del_dia("2026-11-03") == (0, 0)
    assert repo.actividad_del_dia("2026-11-10") == (0, 0)


def test_las_sesiones_se_pueden_filtrar_por_equipo(repo: Repositorio) -> None:
    equipo, _ = preparar_sesiones(repo)
    otro = repo.obtener_o_crear_equipo("PC-PRUEBA-02")
    de_otro = repo.abrir_sesion(otro, "2026-11-02T09:00:00")

    assert [s.id for s in repo.listar_sesiones(id_equipo=otro)] == [de_otro]
    assert len(repo.listar_sesiones(id_equipo=equipo)) == 4
    assert repo.actividad_del_dia("2026-11-02", id_equipo=otro) == (0, 0)


def test_un_dia_que_no_es_fecha_se_rechaza(repo: Repositorio) -> None:
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        _ = repo.listar_sesiones(dia="hoy")
    with pytest.raises(ValueError, match="AAAA-MM-DD"):
        _ = repo.actividad_del_dia("02/11/2026")


def test_listar_equipos_devuelve_id_y_nombre_por_orden_de_creacion(repo: Repositorio) -> None:
    assert repo.listar_equipos() == []

    primero = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    segundo = repo.obtener_o_crear_equipo("PC-PRUEBA-02")

    assert repo.listar_equipos() == [(primero, "PC-PRUEBA-01"), (segundo, "PC-PRUEBA-02")]


def test_la_ultima_sesion_es_la_que_empezo_mas_tarde_y_sin_sesiones_es_none(repo: Repositorio) -> None:
    assert repo.ultima_sesion() is None

    _, (_, en_curso, nocturna, martes) = preparar_sesiones(repo)

    ultima = repo.ultima_sesion()
    assert ultima is not None and ultima.id == martes and ultima.en_curso
    assert ultima.id not in (en_curso, nocturna)


def test_incidentes_recientes_trae_los_ultimos_del_mas_nuevo_al_mas_viejo(repo: Repositorio) -> None:
    equipo = repo.obtener_o_crear_equipo("PC-PRUEBA-01")
    sesion = repo.abrir_sesion(equipo, "2026-11-02T08:00:00")
    repo.guardar_incidente("evento_invalido", "2026-11-02T08:01:00", "falta el campo hora", "línea descartada", sesion)
    repo.guardar_incidente("caida_proceso", "2026-11-02T08:03:00", "el capturador terminó con código 3", "relanzado en 1 s")
    repo.guardar_incidente("error_comunicacion", "2026-11-02T08:02:00", None, None, sesion)

    ultimos = repo.incidentes_recientes(2)

    assert [i.tipo for i in ultimos] == ["caida_proceso", "error_comunicacion"]
    assert ultimos[0] == FilaIncidente(ultimos[0].id, None, "caida_proceso", "2026-11-02T08:03:00",
                                       "el capturador terminó con código 3", "relanzado en 1 s")
    assert (ultimos[1].id_sesion, ultimos[1].detalle, ultimos[1].accion) == (sesion, None, None)
    assert len(repo.incidentes_recientes()) == 3


def test_incidentes_recientes_exige_un_limite_positivo(repo: Repositorio) -> None:
    with pytest.raises(ValueError, match="al menos 1"):
        _ = repo.incidentes_recientes(0)


# ---------- Alertas ----------


def test_crear_alerta_no_duplica_la_del_mismo_periferico_y_umbral(repo: Repositorio, ruta_db: Path) -> None:
    _, teclado = crear_teclado(repo)

    assert repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00", "Q 91 %")
    assert not repo.crear_alerta(teclado, 90, "2026-11-02T10:05:00", "otro detalle")   # ya existía
    assert repo.crear_alerta(teclado, 100, "2026-11-02T11:00:00")                       # otro umbral, otra alerta

    filas = consultar(ruta_db, "SELECT umbral, estado, detalle, fecha_creacion FROM alerta ORDER BY umbral")
    assert filas == [(90, "pendiente", "Q 91 %", "2026-11-02T10:00:00"), (100, "pendiente", None, "2026-11-02T11:00:00")]


def test_crear_alerta_rechaza_un_umbral_invalido_o_un_periferico_inexistente(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)

    with pytest.raises(sqlite3.IntegrityError):
        _ = repo.crear_alerta(teclado, 95, "2026-11-02T10:00:00")
    with pytest.raises(sqlite3.IntegrityError):
        _ = repo.crear_alerta(999, 90, "2026-11-02T10:00:00")


def test_las_alertas_se_listan_nuevas_primero_y_las_pendientes_viejas_primero(repo: Repositorio) -> None:
    equipo, teclado = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00")
    _ = repo.crear_alerta(mouse, 90, "2026-11-02T11:00:00")
    _ = repo.crear_alerta(teclado, 100, "2026-11-02T12:00:00")

    todas = repo.listar_alertas()
    pendientes = repo.alertas_pendientes()

    assert [(a.id_periferico, a.umbral) for a in todas] == [(teclado, 100), (mouse, 90), (teclado, 90)]
    assert [(a.id_periferico, a.umbral) for a in pendientes] == [(teclado, 90), (mouse, 90), (teclado, 100)]
    assert (todas[1].modelo, todas[1].etiqueta, todas[1].estado, todas[1].intentos) == ("B100", None, "pendiente", 0)


def test_un_intento_fallido_anota_cuando_y_por_que_y_la_alerta_sigue_pendiente(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00")
    alerta = repo.alertas_pendientes()[0]

    repo.registrar_intento_de_alerta(alerta.id, "2026-11-02T10:00:05", "2026-11-02T10:01:05", "no se pudo conectar al servidor")
    repo.registrar_intento_de_alerta(alerta.id, "2026-11-02T10:01:10", "2026-11-02T10:06:10", "no se pudo conectar al servidor")

    despues = repo.alertas_pendientes()[0]
    assert (despues.intentos, despues.estado) == (2, "pendiente")
    assert (despues.fecha_ultimo_intento, despues.proximo_reintento) == ("2026-11-02T10:01:10", "2026-11-02T10:06:10")
    assert despues.ultimo_error == "no se pudo conectar al servidor"


def test_marcar_una_alerta_como_enviada_la_saca_de_las_pendientes(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00")
    alerta = repo.alertas_pendientes()[0]
    repo.registrar_intento_de_alerta(alerta.id, "2026-11-02T10:00:05", "2026-11-02T10:01:05", "sin conexión")

    repo.marcar_alerta_enviada(alerta.id, "2026-11-02T10:01:06")

    assert repo.alertas_pendientes() == []
    enviada = repo.listar_alertas("enviada")[0]
    assert (enviada.estado, enviada.intentos, enviada.fecha_envio) == ("enviada", 2, "2026-11-02T10:01:06")
    assert (enviada.proximo_reintento, enviada.ultimo_error) == (None, "sin conexión")   # el error queda como historial


def test_no_se_puede_reintentar_ni_reenviar_una_alerta_ya_enviada_o_inexistente(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00")
    alerta = repo.alertas_pendientes()[0]
    repo.marcar_alerta_enviada(alerta.id, "2026-11-02T10:00:05")

    with pytest.raises(LookupError):
        repo.marcar_alerta_enviada(alerta.id, "2026-11-02T10:00:09")
    with pytest.raises(LookupError):
        repo.registrar_intento_de_alerta(alerta.id, "2026-11-02T10:00:09", None, "error")
    with pytest.raises(LookupError):
        repo.marcar_alerta_enviada(999, "2026-11-02T10:00:09")


def test_listar_alertas_rechaza_un_estado_desconocido(repo: Repositorio) -> None:
    with pytest.raises(ValueError, match="estado"):
        _ = repo.listar_alertas("cancelada")


def test_una_alerta_no_muestra_su_detalle_al_imprimirse(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00", "Q 91 %")

    alerta = repo.listar_alertas()[0]

    assert alerta.detalle == "Q 91 %"
    assert "Q 91" not in repr(alerta)   # el detalle puede nombrar una tecla (RNF4)


# ---------- Horas de eventos y filas de reportes ----------


def preparar_eventos(repo: Repositorio) -> tuple[int, int, int]:
    """Cuatro eventos: una pulsación con su liberación y un clic el lunes 2, y un movimiento el martes 3."""
    equipo, teclado = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)
    sesion = repo.abrir_sesion(equipo, "2026-11-02T07:59:00")
    repo.guardar_evento(sesion, teclado, "tecla_presionada", "2026-11-02T08:00:00.100")
    repo.guardar_evento(sesion, teclado, "tecla_liberada", "2026-11-02T08:00:00.200")
    repo.guardar_evento(sesion, mouse, "clic_izquierdo", "2026-11-02T09:00:00")
    repo.guardar_evento(sesion, mouse, "mouse_movimiento", "2026-11-03T10:00:00", 640, 360)
    return teclado, mouse, sesion


def test_las_horas_de_eventos_omiten_las_liberaciones_salvo_que_se_pidan(repo: Repositorio) -> None:
    _ = preparar_eventos(repo)

    assert repo.horas_de_eventos() == ["2026-11-02T08:00:00.100", "2026-11-02T09:00:00", "2026-11-03T10:00:00"]
    assert len(repo.horas_de_eventos(incluir_liberaciones=True)) == 4


def test_las_horas_de_eventos_se_pueden_filtrar_por_tipo_de_dispositivo(repo: Repositorio) -> None:
    _ = preparar_eventos(repo)

    assert repo.horas_de_eventos(tipo_dispositivo="teclado") == ["2026-11-02T08:00:00.100"]
    assert repo.horas_de_eventos(tipo_dispositivo="mouse") == ["2026-11-02T09:00:00", "2026-11-03T10:00:00"]


def test_el_rango_de_fechas_incluye_el_inicio_y_excluye_el_final(repo: Repositorio) -> None:
    _ = preparar_eventos(repo)

    assert repo.horas_de_eventos(desde="2026-11-03") == ["2026-11-03T10:00:00"]
    assert repo.horas_de_eventos(hasta="2026-11-03") == ["2026-11-02T08:00:00.100", "2026-11-02T09:00:00"]
    assert repo.horas_de_eventos(desde="2026-11-02T09:00:00", hasta="2026-11-03") == ["2026-11-02T09:00:00"]   # el inicio entra
    assert repo.horas_de_eventos(desde="2026-11-02T08:00:00", hasta="2026-11-02T09:00:00") == ["2026-11-02T08:00:00.100"]   # el final no
    assert repo.horas_de_eventos(desde="2026-12-01") == []


def test_los_reportes_con_una_fecha_que_no_es_iso_fallan_en_vez_de_devolver_una_lista_vacia(repo: Repositorio) -> None:
    for lectura in (repo.horas_de_eventos, repo.filas_de_eventos, repo.filas_de_totales_diarios,
                    repo.filas_de_contadores, repo.filas_de_alertas):
        with pytest.raises(ValueError, match="ISO 8601"):
            _ = lectura(desde="hoy")
        with pytest.raises(ValueError, match="ISO 8601"):
            _ = lectura(hasta="2026-13-45")


def test_las_filas_de_eventos_traen_siete_columnas_y_ninguna_es_la_tecla(repo: Repositorio) -> None:
    teclado, _, sesion = preparar_eventos(repo)
    repo.asignar_etiqueta(teclado, "TEC-0042")

    filas = repo.filas_de_eventos()

    assert len(filas) == 4
    assert all(len(fila) == 7 for fila in filas)
    assert filas[0][1:] == (sesion, "TEC-0042", "tecla_presionada", "2026-11-02T08:00:00.100", None, None)
    assert filas[3][1:] == (sesion, "ID 2", "mouse_movimiento", "2026-11-03T10:00:00", 640, 360)   # el mouse aún no tiene etiqueta


def test_las_filas_de_contadores_y_de_totales_diarios_agregan_por_dia(repo: Repositorio) -> None:
    equipo, teclado = crear_teclado(repo)
    mouse = crear_mouse(repo, equipo)
    repo.asignar_etiqueta(teclado, "TEC-0042")
    repo.sumar_a_contadores([
        Conteo(teclado, "2026-11-02", "pulsacion_tecla", "Q", 3000),
        Conteo(teclado, "2026-11-02", "pulsacion_tecla", "W", 2000),
        Conteo(teclado, "2026-11-03", "pulsacion_tecla", "Q", 10),
        Conteo(mouse, "2026-11-02", "clic_boton", "izquierdo", 40),
    ])

    assert repo.filas_de_contadores() == [
        ("2026-11-02", "ID 2", "clic_boton", "izquierdo", 40),
        ("2026-11-02", "TEC-0042", "pulsacion_tecla", "Q", 3000),
        ("2026-11-02", "TEC-0042", "pulsacion_tecla", "W", 2000),
        ("2026-11-03", "TEC-0042", "pulsacion_tecla", "Q", 10),
    ]
    assert repo.filas_de_totales_diarios() == [
        ("2026-11-02", "ID 2", "clic_boton", 40),
        ("2026-11-02", "TEC-0042", "pulsacion_tecla", 5000),   # Q + W del mismo día
        ("2026-11-03", "TEC-0042", "pulsacion_tecla", 10),
    ]
    assert repo.filas_de_totales_diarios(hasta="2026-11-03") == repo.filas_de_totales_diarios()[:2]   # el 3 queda fuera
    assert repo.filas_de_contadores(desde="2026-11-03") == [("2026-11-03", "TEC-0042", "pulsacion_tecla", "Q", 10)]
    assert len(repo.filas_de_contadores(hasta="2026-11-03")) == 3   # el día final no entra


def test_las_filas_de_alertas_se_filtran_por_su_fecha_de_creacion(repo: Repositorio) -> None:
    _, teclado = crear_teclado(repo)
    _ = repo.crear_alerta(teclado, 90, "2026-11-02T10:00:00")
    _ = repo.crear_alerta(teclado, 100, "2026-11-04T10:00:00")
    alerta = repo.alertas_pendientes()[0]
    repo.marcar_alerta_enviada(alerta.id, "2026-11-02T10:00:05")

    assert repo.filas_de_alertas() == [
        ("ID 1", 90, "enviada", 1, "2026-11-02T10:00:00", "2026-11-02T10:00:05"),
        ("ID 1", 100, "pendiente", 0, "2026-11-04T10:00:00", None),
    ]
    assert repo.filas_de_alertas(desde="2026-11-03") == [("ID 1", 100, "pendiente", 0, "2026-11-04T10:00:00", None)]


def test_los_resultados_de_las_lecturas_no_tienen_ningun_campo_de_tecla() -> None:
    # `seg_actividad_teclado` es un total de segundos del teclado, no el nombre de una tecla: por eso no se prohíbe "teclado".
    prohibidos = {"tecla", "teclas", "elemento"}
    for tipo in (UsoDeConteo, ResumenPeriferico, FilaSesion, FilaIncidente, FilaAlerta):
        nombres = {campo.name for campo in dataclasses.fields(tipo)}
        assert not nombres & prohibidos, tipo.__name__
