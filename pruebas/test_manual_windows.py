"""Pruebas del script de prueba manual. Se usan el capturador simulado de Python en lugar del real."""
import sys
from pathlib import Path

from pruebas.manual_windows import Resumen, calcular_estadisticas, cumple, dar_formato, ejecutar_prueba, principal

SIMULADOR = str(Path(__file__).parent / "capturador_simulado.py")


def test_estadisticas_de_una_lista_vacia_son_cero() -> None:
    assert calcular_estadisticas([]) == (0.0, 0.0, 0.0)


def test_estadisticas_de_retrasos() -> None:
    promedio, percentil_95, maximo = calcular_estadisticas([10.0, 20.0, 30.0, 40.0, 100.0])
    assert promedio == 40.0
    assert percentil_95 == 40.0  # índice int(0.95 * 4) = 3
    assert maximo == 100.0


def test_cumple_exige_eventos_sin_caidas_y_retraso_menor_a_un_segundo() -> None:
    bueno = Resumen(total=3, retrasos_ms=(5.0, 10.0, 999.0))
    assert cumple(bueno)
    assert not cumple(Resumen())                                              # sin eventos
    assert not cumple(Resumen(total=1, retrasos_ms=(5.0,), caidas=1))         # hubo una caída
    assert not cumple(Resumen(total=1, retrasos_ms=(1000.0,)))                # tardó 1 s o más


def test_el_informe_resume_sin_mostrar_teclas() -> None:
    resumen = Resumen(total=2, por_tipo={"tecla_presionada": 1, "scroll": 1},
                      dispositivos={"teclado 046D:C31C": 1, "mouse 046D:C077": 1}, retrasos_ms=(4.0, 6.0))
    texto = dar_formato(resumen, 30)
    assert "Eventos válidos recibidos : 2" in texto
    assert "teclado 046D:C31C" in texto
    assert "CUMPLE" in texto


def test_ejecutar_prueba_cuenta_los_eventos_del_capturador() -> None:
    comando = [sys.executable, SIMULADOR, "--intervalo", "0.01", "--semilla", "1"]
    resumen = ejecutar_prueba(comando, 1.5)
    assert resumen.total > 20
    assert len(resumen.retrasos_ms) == resumen.total
    assert all(retraso >= 0 for retraso in resumen.retrasos_ms)
    assert resumen.caidas == 0
    assert set(resumen.dispositivos) == {"teclado 046D:C31C", "mouse 046D:C077"}
    assert cumple(resumen)


def test_ejecutar_prueba_cuenta_las_lineas_descartadas_y_las_caidas() -> None:
    comando = [sys.executable, SIMULADOR, "--intervalo", "0.01", "--proporcion-invalidos", "0.5",
               "--caida-en", "10", "--semilla", "2"]
    resumen = ejecutar_prueba(comando, 1.5, esperas=(0.05,))
    assert resumen.descartadas > 0
    assert resumen.caidas > 0
    assert not cumple(resumen)


def test_con_un_capturador_inexistente_el_script_termina_con_error() -> None:
    codigo = principal(["--capturador", "/ruta/que/no/existe", "--segundos", "0.5"])
    assert codigo == 1
