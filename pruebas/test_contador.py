"""Pruebas del contador de desgaste."""
import threading

from comun.repositorio import Conteo
from pruebas.ayudas_base import evento_de_prueba, pulsacion
from servicio.contador import ContadorDesgaste, conteo_de

PERIFERICO = 7


def totales(contador: ContadorDesgaste) -> dict[tuple[str, str, str], int]:
    """(fecha, tipo de conteo, elemento) -> cantidad, de lo que hay pendiente."""
    return {(c.fecha, c.tipo_conteo, c.elemento): c.cantidad for c in contador.tomar_pendientes()}


def test_cada_pulsacion_suma_uno_a_su_tecla() -> None:
    contador = ContadorDesgaste()
    for tecla in ("E", "E", "A", "E"):
        contador.registrar(pulsacion(tecla), PERIFERICO)
    assert totales(contador) == {("2026-11-02", "pulsacion_tecla", "E"): 3, ("2026-11-02", "pulsacion_tecla", "A"): 1}


def test_soltar_una_tecla_y_mover_el_mouse_no_cuentan() -> None:
    contador = ContadorDesgaste()
    contador.registrar(evento_de_prueba("tecla_liberada", dispositivo="teclado", pid="C31C"), PERIFERICO)
    contador.registrar(evento_de_prueba("mouse_movimiento", x=10, y=20), PERIFERICO)
    assert contador.cantidad_pendiente() == 0


def test_los_clics_se_cuentan_por_boton() -> None:
    contador = ContadorDesgaste()
    for tipo in ("clic_izquierdo", "clic_izquierdo", "clic_derecho"):
        contador.registrar(evento_de_prueba(tipo), PERIFERICO)
    assert totales(contador) == {("2026-11-02", "clic_boton", "izquierdo"): 2, ("2026-11-02", "clic_boton", "derecho"): 1}


def test_la_rueda_suma_los_pasos_sin_importar_la_direccion() -> None:
    contador = ContadorDesgaste()
    for pasos in (3, -2, 1):
        contador.registrar(evento_de_prueba("scroll", pasos=pasos), PERIFERICO)
    assert totales(contador) == {("2026-11-02", "scroll_paso", "rueda"): 6}


def test_el_conteo_va_al_dia_del_evento_y_no_al_dia_en_que_se_guarda() -> None:
    contador = ContadorDesgaste()
    contador.registrar(pulsacion("E", "2026-11-02T23:59:59.900"), PERIFERICO)
    contador.registrar(pulsacion("E", "2026-11-03T00:00:00.050"), PERIFERICO)
    assert totales(contador) == {("2026-11-02", "pulsacion_tecla", "E"): 1, ("2026-11-03", "pulsacion_tecla", "E"): 1}


def test_cada_periferico_tiene_sus_propios_contadores() -> None:
    contador = ContadorDesgaste()
    contador.registrar(pulsacion("E"), 1)
    contador.registrar(pulsacion("E"), 2)
    ids = sorted(c.id_periferico for c in contador.tomar_pendientes())
    assert ids == [1, 2]


def test_tomar_pendientes_deja_el_contador_en_cero() -> None:
    contador = ContadorDesgaste()
    contador.registrar(pulsacion("E"), PERIFERICO)
    assert len(contador.tomar_pendientes()) == 1
    assert contador.tomar_pendientes() == []


def test_reponer_devuelve_lo_que_no_se_pudo_guardar_y_lo_suma_a_lo_nuevo() -> None:
    contador = ContadorDesgaste()
    contador.registrar(pulsacion("E"), PERIFERICO)
    sin_guardar = contador.tomar_pendientes()
    contador.registrar(pulsacion("E"), PERIFERICO)   # llega algo nuevo mientras tanto
    contador.reponer(sin_guardar)
    assert totales(contador) == {("2026-11-02", "pulsacion_tecla", "E"): 2}


def test_conteo_de_devuelve_none_para_los_eventos_que_no_cuentan() -> None:
    assert conteo_de(evento_de_prueba("tecla_liberada", dispositivo="teclado")) is None
    assert conteo_de(evento_de_prueba("mouse_movimiento", x=1, y=2)) is None
    assert conteo_de(pulsacion("E")) == ("pulsacion_tecla", "E", 1)


def test_soltar_una_tecla_no_cuenta_aunque_el_evento_trajera_una_tecla() -> None:
    # El validador nunca deja pasar una liberación con tecla, pero el contador no debe depender de eso.
    liberacion = evento_de_prueba("tecla_liberada", dispositivo="teclado", pid="C31C", tecla="E")
    assert conteo_de(liberacion) is None


def test_varios_hilos_pueden_contar_a_la_vez() -> None:
    contador = ContadorDesgaste()

    def contar() -> None:
        for _ in range(500):
            contador.registrar(pulsacion("E"), PERIFERICO)

    hilos = [threading.Thread(target=contar) for _ in range(4)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=30)
    assert totales(contador) == {("2026-11-02", "pulsacion_tecla", "E"): 2000}


def test_ni_el_contador_ni_el_conteo_muestran_la_tecla_al_imprimirse() -> None:
    contador = ContadorDesgaste()
    contador.registrar(pulsacion("PAUSA"), PERIFERICO)
    assert "PAUSA" not in repr(contador)
    assert "PAUSA" not in str(contador)
    assert "PAUSA" not in repr(contador.tomar_pendientes())
    assert "PAUSA" not in repr(Conteo(PERIFERICO, "2026-11-02", "pulsacion_tecla", "PAUSA"))
