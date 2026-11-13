"""Pruebas del capturador de C++ en modo simulado.

Compilan el programa con el compilador del sistema y comprueban que lo que escribe cumple
el contrato, usando el validador real de Python. La captura con Raw Input solo se prueba en Windows.

Con qué datos: compila `capturador/src` con las advertencias estrictas del CMakeLists.txt y con los
detectores de errores de memoria (address y undefined; se omiten si el compilador no los trae, como MinGW-w64 en
Windows), ejecuta `captura --simulado` con distintas
semillas y revisa cada línea que escribe con `validar_linea`. También corre `pruebas_unitarias.cpp`, comprueba
que el gestor de Python lee ese capturador y que el código de Raw Input compila para Windows con MinGW-w64
(solo compila: no se ejecuta fuera de Windows). Si no hay compilador, las pruebas se omiten.

Se relaciona con: usa `capturador/src/*.cpp`, `capturador/pruebas/pruebas_unitarias.cpp`,
`servicio/validador.py` y `servicio/gestor_subproceso.py` · lo ejecuta pytest.
"""
import functools
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

import pytest

from servicio.gestor_subproceso import GestorSubproceso, Incidente
from servicio.validador import EventoValido, validar_linea

RAIZ = Path(__file__).parent.parent
FUENTES = RAIZ / "capturador" / "src"
PRUEBAS_UNITARIAS = RAIZ / "capturador" / "pruebas" / "pruebas_unitarias.cpp"

# Las mismas advertencias estrictas que se piden en CMakeLists.txt, más los detectores de errores de memoria.
BANDERAS = ["-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-fsanitize=address,undefined", "-g"]
NUCLEO = ["evento.cpp", "reglas_de_captura.cpp"]
PROGRAMA = [*NUCLEO, "escritor.cpp", "simulador.cpp", "principal.cpp"]

# Compilación cruzada con MinGW-w64: genera .exe para Windows desde macOS o Linux (sin ejecutarlo).
COMPILADOR_WINDOWS = "x86_64-w64-mingw32-g++"
BANDERAS_WINDOWS = ["-std=c++17", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                    "-static", "-static-libgcc", "-static-libstdc++"]
PROGRAMA_WINDOWS = [*PROGRAMA, "raw_input_windows.cpp"]

# En Windows el programa nativo incluye la captura real (principal.cpp la llama), que necesita user32.
EN_WINDOWS = sys.platform == "win32"
FUENTES_PROGRAMA = PROGRAMA_WINDOWS if EN_WINDOWS else PROGRAMA
BIBLIOTECAS_PROGRAMA = ["-luser32"] if EN_WINDOWS else []

TIPOS = {"tecla_presionada", "tecla_liberada", "mouse_movimiento", "clic_izquierdo", "clic_derecho", "scroll"}


@functools.cache
def banderas_del_sistema(compilador: str) -> list[str]:
    """Las banderas de BANDERAS, sin los detectores de memoria si el compilador no los trae.

    MinGW-w64 en Windows (por ejemplo WinLibs) no incluye las bibliotecas asan y ubsan: sin esta
    comprobación, el enlazador falla con `cannot find -lasan` y ninguna prueba de C++ podría correr.
    Se prueba compilando un programa mínimo; el resultado se guarda para no repetirlo.
    """
    with tempfile.TemporaryDirectory() as carpeta:
        minimo = Path(carpeta) / "minimo.cpp"
        _ = minimo.write_text("int main() { return 0; }\n", encoding="utf-8")
        resultado = subprocess.run(
            [compilador, "-fsanitize=address,undefined", str(minimo), "-o", str(Path(carpeta) / "minimo")],
            capture_output=True, timeout=120, check=False,
        )
    if resultado.returncode == 0:
        return BANDERAS
    return [bandera for bandera in BANDERAS if not bandera.startswith("-fsanitize")]


def compilar(
    compilador: str,
    fuentes: list[Path],
    salida: Path,
    banderas: list[str] | None = None,
    bibliotecas: list[str] | None = None,
) -> Path:
    """Compila `fuentes` con `compilador` y devuelve la ruta del ejecutable. Si falla, la prueba muestra el error.

    banderas: por defecto las estrictas de BANDERAS (sin los detectores de memoria si el compilador no los trae);
    bibliotecas: opciones extra para el enlazador.
    """
    resultado = subprocess.run(
        [compilador, *(banderas_del_sistema(compilador) if banderas is None else banderas), f"-I{FUENTES}",
         *map(str, fuentes), *(bibliotecas or []), "-o", str(salida)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    return salida


@pytest.fixture(scope="session")
def compilador() -> str:
    """El compilador de C++ del sistema (clang++, g++ o c++); omite las pruebas si no hay ninguno."""
    encontrado = shutil.which("clang++") or shutil.which("g++") or shutil.which("c++")
    if encontrado is None:
        pytest.skip("no hay un compilador de C++ en este sistema")
    return encontrado


@pytest.fixture(scope="session")
def capturador(compilador: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """El programa completo compilado una sola vez por sesión (compilar tarda unos segundos)."""
    return compilar(compilador, [FUENTES / archivo for archivo in FUENTES_PROGRAMA],
                    tmp_path_factory.mktemp("cpp") / "captura", bibliotecas=BIBLIOTECAS_PROGRAMA)


@pytest.fixture(scope="session")
def pruebas_unitarias(compilador: str, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """El ejecutable de las pruebas unitarias de C++, que solo necesita el núcleo portable (sin simulador)."""
    fuentes = [FUENTES / archivo for archivo in NUCLEO] + [PRUEBAS_UNITARIAS]
    return compilar(compilador, fuentes, tmp_path_factory.mktemp("cpp_unitarias") / "unitarias")


@pytest.fixture(scope="session")
def compilador_windows() -> str:
    """El compilador cruzado MinGW-w64 para generar .exe; omite la prueba si no está instalado."""
    encontrado = shutil.which(COMPILADOR_WINDOWS)
    if encontrado is None:
        pytest.skip("no está instalado MinGW-w64 (brew install mingw-w64)")
    return encontrado


def simular(capturador: Path, *argumentos: str) -> subprocess.CompletedProcess[bytes]:
    """Ejecuta `captura --simulado` con `argumentos` y devuelve su salida en bytes (así se ven exactos los saltos de línea y stderr)."""
    return subprocess.run([str(capturador), "--simulado", *argumentos], capture_output=True, timeout=60, check=False)


def lineas_de(resultado: subprocess.CompletedProcess[bytes]) -> list[str]:
    """Las líneas de stdout ya decodificadas como UTF-8."""
    return resultado.stdout.decode("utf-8").splitlines()


def test_las_pruebas_unitarias_de_cpp_pasan(pruebas_unitarias: Path) -> None:
    resultado = subprocess.run([str(pruebas_unitarias)], capture_output=True, text=True, timeout=60, check=False)
    assert resultado.returncode == 0, resultado.stderr
    assert "0 fallos" in resultado.stdout


def test_el_validador_acepta_todas_las_lineas_del_capturador(capturador: Path) -> None:
    resultado = simular(capturador, "--cantidad", "500", "--semilla", "1")
    assert resultado.returncode == 0
    lineas = lineas_de(resultado)
    assert len(lineas) == 500
    for linea in lineas:
        assert isinstance(validar_linea(linea), EventoValido), linea


def test_usa_todos_los_tipos_de_evento(capturador: Path) -> None:
    resultado = simular(capturador, "--cantidad", "500", "--semilla", "2")
    tipos = {cast(dict[str, object], json.loads(linea))["tipo"] for linea in lineas_de(resultado)}
    assert tipos == TIPOS


def test_usa_saltos_de_linea_n_y_no_escribe_en_stderr(capturador: Path) -> None:
    resultado = simular(capturador, "--cantidad", "50", "--semilla", "3")
    assert b"\r" not in resultado.stdout
    assert resultado.stdout.endswith(b"\n")
    assert resultado.stderr == b""  # stderr es solo para mensajes técnicos, y no hubo ninguno


def test_la_misma_semilla_repite_la_secuencia(capturador: Path) -> None:
    def sin_hora(resultado: subprocess.CompletedProcess[bytes]) -> list[dict[str, object]]:
        """Los eventos sin la hora: la hora cambia en cada ejecución, el resto debe repetirse con la misma semilla."""
        eventos = [cast(dict[str, object], json.loads(linea)) for linea in lineas_de(resultado)]
        for evento in eventos:
            del evento["hora"]
        return eventos

    primera = sin_hora(simular(capturador, "--cantidad", "100", "--semilla", "5"))
    segunda = sin_hora(simular(capturador, "--cantidad", "100", "--semilla", "5"))
    assert primera == segunda


def test_si_el_servicio_cierra_la_lectura_el_capturador_termina_sin_error(capturador: Path) -> None:
    # Sin --cantidad el simulador no termina solo: debe parar al notar que nadie lee.
    with subprocess.Popen([str(capturador), "--simulado"], stdout=subprocess.PIPE) as proceso:
        assert proceso.stdout is not None
        for _ in range(3):
            assert proceso.stdout.readline()
        proceso.stdout.close()
        assert proceso.wait(timeout=30) == 0


def test_con_opciones_invalidas_termina_con_codigo_2(capturador: Path) -> None:
    for argumentos in (["--cantidad"], ["--cantidad", "mucho"], ["--no-existe"]):
        resultado = simular(capturador, *argumentos)
        assert resultado.returncode == 2, argumentos
        assert resultado.stdout == b""


@pytest.mark.skipif(sys.platform == "win32", reason="en Windows sí hay captura real")
def test_sin_modo_simulado_fuera_de_windows_explica_que_no_se_puede(capturador: Path) -> None:
    resultado = subprocess.run([str(capturador)], capture_output=True, timeout=60, check=False)
    assert resultado.returncode == 2
    assert b"Windows" in resultado.stderr


def test_el_gestor_de_python_lee_el_capturador_de_cpp(capturador: Path) -> None:
    eventos: list[EventoValido] = []
    incidentes: list[Incidente] = []
    gestor = GestorSubproceso([str(capturador), "--simulado", "--semilla", "7"], eventos.append, incidentes.append)
    gestor.iniciar()
    try:
        for _ in range(200):
            if len(eventos) >= 100:
                break
            gestor.esperar(0.05)
    finally:
        gestor.detener()
    assert len(eventos) >= 100
    assert incidentes == []


# ---------- Compilación para Windows (no se ejecuta: eso requiere un PC con Windows) ----------

def test_el_capturador_con_raw_input_compila_para_windows(
    compilador_windows: str, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    salida = tmp_path_factory.mktemp("windows") / "captura.exe"
    _ = compilar(compilador_windows, [FUENTES / archivo for archivo in PROGRAMA_WINDOWS], salida,
                 banderas=BANDERAS_WINDOWS, bibliotecas=["-luser32"])
    assert salida.read_bytes()[:2] == b"MZ"  # firma de un ejecutable de Windows


def test_las_pruebas_unitarias_compilan_para_windows(
    compilador_windows: str, tmp_path_factory: pytest.TempPathFactory,
) -> None:
    fuentes = [FUENTES / archivo for archivo in NUCLEO] + [PRUEBAS_UNITARIAS]
    salida = tmp_path_factory.mktemp("windows_unitarias") / "unitarias.exe"
    _ = compilar(compilador_windows, fuentes, salida, banderas=BANDERAS_WINDOWS)
    assert salida.read_bytes()[:2] == b"MZ"
