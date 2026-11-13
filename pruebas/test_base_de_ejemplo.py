"""Pruebas del generador de la base de datos de ejemplo.

Con qué datos: la base que genera el propio programa con una fecha final fija (jueves 12 de noviembre de 2026), 21 días y
la semilla 1, en una carpeta temporal. Comprueba: los cuatro periféricos y su desgaste (el límite es por tecla o botón),
las alertas enviadas y pendientes, las sesiones (una en curso y alguna inesperada), los incidentes, que los eventos cubran
varios días y horas para el mapa de calor, que la misma semilla repita la base, que se pueda volver a crear sin error y
que NUNCA sobrescriba un archivo que no sea una base de ejemplo (por ejemplo, la base real).

Se relaciona con: usa `pruebas/base_de_ejemplo.py` y `comun/repositorio.py` · lo ejecuta pytest.
"""
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

from comun.repositorio import Repositorio
from pruebas.base_de_ejemplo import (
    CORREO_DE_EJEMPLO,
    DIAS_MINIMOS,
    BaseExistente,
    crear_base_de_ejemplo,
    principal,
)

HASTA = date(2026, 11, 12)  # jueves


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    """La ruta donde se crea la base de ejemplo (todavía no existe; su carpeta tampoco)."""
    return tmp_path / "datos" / "ejemplo.db"


@pytest.fixture
def repo(ruta_db: Path) -> Iterator[Repositorio]:
    """La base de ejemplo ya creada, abierta con un repositorio que se cierra al terminar la prueba."""
    _ = crear_base_de_ejemplo(ruta_db, HASTA, 21, 1)
    with Repositorio(ruta_db) as repositorio:
        yield repositorio


def test_crea_cuatro_perifericos_con_los_estados_que_piden_las_pantallas(repo: Repositorio) -> None:
    por_etiqueta = {p.etiqueta: p for p in repo.listar_perifericos()}
    sin_etiqueta = [p for p in repo.listar_perifericos() if p.etiqueta is None]

    assert len(repo.listar_perifericos()) == 4
    assert por_etiqueta["TEC-0007"].activo is False and por_etiqueta["TEC-0007"].fecha_retiro is not None
    assert (por_etiqueta["MOU-0108"].activo, por_etiqueta["MOU-0108"].estado_asignacion) == (True, "confirmada")
    assert sorted(p.modelo for p in sin_etiqueta) == ["K120", "desconocido"]
    assert all(p.estado_asignacion == "por_confirmar" and p.activo for p in sin_etiqueta)


def test_el_desgaste_llega_a_los_porcentajes_previstos_por_tecla_o_boton(repo: Repositorio) -> None:
    perifericos = repo.listar_perifericos()
    viejo = next(p for p in perifericos if p.etiqueta == "TEC-0007")
    actual = next(p for p in perifericos if p.etiqueta is None and p.modelo == "K120")
    mouse = next(p for p in perifericos if p.etiqueta == "MOU-0108")
    desconocido = next(p for p in perifericos if p.modelo == "desconocido")

    assert viejo.porcentaje_maximo == 100.0
    assert actual.porcentaje_maximo == 92.0
    assert {uso.tipo_conteo: uso.porcentaje for uso in mouse.usos} == {"clic_boton": 55.0, "scroll_paso": 30.0}
    assert [uso.limite for uso in desconocido.usos] == [None] and desconocido.porcentaje_maximo is None
    # El límite es por tecla: la más gastada llega al tope y las demás llevan menos, aunque la suma pase del límite.
    por_tecla = repo.totales_por_elemento(viejo.id, "pulsacion_tecla")
    assert max(por_tecla.values()) == 20000 and sum(por_tecla.values()) > 20000
    assert len({cantidad for cantidad in por_tecla.values()}) > 5


def test_las_alertas_del_teclado_retirado_estan_enviadas_y_la_del_actual_sigue_pendiente(repo: Repositorio) -> None:
    alertas = repo.listar_alertas()
    pendientes = repo.alertas_pendientes()

    assert sorted((a.etiqueta, a.umbral, a.estado) for a in alertas if a.etiqueta is not None) == [
        ("TEC-0007", 90, "enviada"), ("TEC-0007", 100, "enviada"),
    ]
    assert len(alertas) == 3 and len(pendientes) == 1
    assert (pendientes[0].umbral, pendientes[0].etiqueta, pendientes[0].intentos) == (90, None, 2)
    assert pendientes[0].ultimo_error is not None and pendientes[0].proximo_reintento is not None
    enviada_con_reintento = next(a for a in alertas if a.umbral == 100)
    assert enviada_con_reintento.intentos == 2 and enviada_con_reintento.fecha_envio is not None
    # Ninguna alerta es de un momento que todavía no llegó: "ahora" es la mitad de la mañana del último día.
    assert all(a.fecha_creacion <= "2026-11-12T11:30:00" for a in alertas)


def test_hay_una_sesion_en_curso_la_del_ultimo_dia_y_alguna_inesperada(repo: Repositorio) -> None:
    sesiones = repo.listar_sesiones()
    en_curso = [s for s in sesiones if s.en_curso]

    assert len(en_curso) == 1 and en_curso[0].inicio.startswith("2026-11-12")
    assert any(s.tipo_cierre == "inesperado" for s in sesiones)
    assert all(datetime.fromisoformat(s.inicio) >= datetime(2026, 10, 23) for s in sesiones)   # 21 días hasta el 12 de noviembre
    assert all(s.seg_actividad_teclado > 0 and s.seg_actividad_mouse > 0 for s in sesiones)
    assert repo.actividad_del_dia("2026-11-12")[0] > 0


def test_hay_incidentes_de_todos_los_tipos_que_el_servicio_registra(repo: Repositorio) -> None:
    tipos = {i.tipo for i in repo.incidentes_recientes(1000)}

    assert tipos == {"caida_proceso", "evento_invalido", "error_comunicacion", "apagado_inesperado", "error_envio"}


def test_los_eventos_cubren_varios_dias_de_la_semana_y_muchas_horas_para_el_mapa_de_calor(repo: Repositorio) -> None:
    momentos = [datetime.fromisoformat(h) for h in repo.horas_de_eventos()]

    assert len(momentos) > 2000
    assert len({m.weekday() for m in momentos}) >= 5
    assert len({m.hour for m in momentos}) >= 8
    assert {m.weekday() for m in momentos} <= {0, 1, 2, 3, 4, 5, 6}


def test_la_misma_semilla_da_exactamente_la_misma_base(tmp_path: Path) -> None:
    resultados: list[tuple[object, ...]] = []
    for nombre in ("a.db", "b.db"):
        _ = crear_base_de_ejemplo(tmp_path / nombre, HASTA, 21, 7)
        with Repositorio(tmp_path / nombre) as repo:
            resultados.append((repo.filas_de_contadores(), repo.horas_de_eventos(incluir_liberaciones=True),
                               [(s.inicio, s.fin, s.tipo_cierre) for s in repo.listar_sesiones()],
                               [(a.umbral, a.detalle, a.fecha_creacion) for a in repo.listar_alertas()]))

    assert resultados[0] == resultados[1]


def test_otra_semilla_da_otra_base(tmp_path: Path) -> None:
    _ = crear_base_de_ejemplo(tmp_path / "a.db", HASTA, 21, 1)
    _ = crear_base_de_ejemplo(tmp_path / "b.db", HASTA, 21, 2)
    with Repositorio(tmp_path / "a.db") as a, Repositorio(tmp_path / "b.db") as b:
        assert a.filas_de_contadores() != b.filas_de_contadores()


def test_se_puede_volver_a_crear_la_misma_base_sin_error(ruta_db: Path) -> None:
    primera = crear_base_de_ejemplo(ruta_db, HASTA, 21, 1)
    segunda = crear_base_de_ejemplo(ruta_db, HASTA, 21, 1)

    assert primera == segunda
    with Repositorio(ruta_db) as repo:
        assert len(repo.listar_perifericos()) == 4   # no se duplicó nada


def test_no_sobrescribe_una_base_real_que_no_es_de_ejemplo(tmp_path: Path) -> None:
    real = tmp_path / "eventos.db"
    with Repositorio(real) as repo:
        _ = repo.obtener_o_crear_equipo("PC-REAL-01")

    with pytest.raises(BaseExistente):
        _ = crear_base_de_ejemplo(real, HASTA, 21, 1)

    with Repositorio(real) as repo:   # la base real sigue ahí, con su equipo
        assert repo.obtener_o_crear_equipo("PC-REAL-01") == 1
        assert repo.listar_perifericos() == []


def test_no_sobrescribe_un_archivo_que_ni_siquiera_es_una_base(tmp_path: Path) -> None:
    otro = tmp_path / "notas.db"
    _ = otro.write_text("no soy una base de datos", encoding="utf-8")

    with pytest.raises(BaseExistente):
        _ = crear_base_de_ejemplo(otro, HASTA, 21, 1)

    assert otro.read_text(encoding="utf-8") == "no soy una base de datos"


def test_los_dias_deben_estar_entre_el_minimo_y_365(ruta_db: Path) -> None:
    with pytest.raises(ValueError, match="entre"):
        _ = crear_base_de_ejemplo(ruta_db, HASTA, DIAS_MINIMOS - 1)
    with pytest.raises(ValueError, match="entre"):
        _ = crear_base_de_ejemplo(ruta_db, HASTA, 366)
    assert not ruta_db.exists()   # no dejó nada a medias


def test_con_el_minimo_de_dias_tambien_hay_un_periferico_retirado_y_uno_actual(ruta_db: Path) -> None:
    _ = crear_base_de_ejemplo(ruta_db, HASTA, DIAS_MINIMOS, 3)

    with Repositorio(ruta_db) as repo:
        perifericos = repo.listar_perifericos()
        assert len(perifericos) == 4
        assert [p.activo for p in perifericos].count(False) == 1


def test_los_datos_de_ejemplo_no_contienen_correos_reales_ni_contrasenas(repo: Repositorio) -> None:
    assert repo.leer_configuracion("destinatarios") == CORREO_DE_EJEMPLO
    assert CORREO_DE_EJEMPLO.endswith(".invalid")   # dominio reservado: ningún buzón real lo usa
    assert (repo.leer_configuracion("smtp_remitente") or "").endswith(".invalid")
    for clave in ("contrasena", "contraseña", "password", "smtp_clave"):
        assert repo.leer_configuracion(clave) is None


def test_ninguna_lectura_de_eventos_trae_la_tecla(repo: Repositorio) -> None:
    filas = repo.filas_de_eventos()

    assert filas and all(len(fila) == 7 for fila in filas)   # id, sesión, periférico, tipo, hora, x, y


def test_el_programa_crea_la_base_y_muestra_un_resumen(ruta_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    codigo = principal([str(ruta_db), "--hasta", "2026-11-12", "--dias", "14", "--semilla", "5"])

    salida = capsys.readouterr()
    assert codigo == 0 and ruta_db.is_file()
    assert "4 periféricos" in salida.out and "alertas" in salida.out
    assert salida.err == ""


def test_el_programa_se_niega_a_tocar_un_archivo_que_no_es_de_ejemplo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    otro = tmp_path / "importante.db"
    _ = otro.write_text("datos importantes", encoding="utf-8")

    codigo = principal([str(otro)])

    assert codigo == 2
    assert "No se hizo nada" in capsys.readouterr().err
    assert otro.read_text(encoding="utf-8") == "datos importantes"
