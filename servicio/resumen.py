"""Resumen de una corrida del servicio, para comprobarla desde la terminal sin abrir la interfaz.

Qué hace: lee la base de datos y escribe unas líneas con lo que importa para saber si el servicio funciona: si está en marcha,
qué hace con el capturador, cómo va la sesión, el desgaste de cada periférico, las alertas y los incidentes. Sirve igual en
macOS que en Windows (por ejemplo, en la prueba de `docs/pruebas-en-windows.md`).

Cómo funciona: `resumir` arma el texto a partir de las lecturas del repositorio (`leer_estado`, `ultima_sesion`,
`listar_perifericos`, `listar_alertas`, `incidentes_recientes`); no escribe nada en la base y se puede ejecutar mientras el
servicio corre (WAL permite leer a la vez). `principal` lo imprime: `python -m servicio.resumen --base ruta`.

Privacidad (RNF4): el resumen muestra totales y porcentajes por periférico, nunca el nombre de una tecla ni el detalle de una
alerta (que puede nombrar la tecla más gastada). Los incidentes se cuentan por tipo.

Se relaciona con: usa `comun/repositorio.py` y `servicio/control.py` (`leer_estado`) · lo usan quien prueba el servicio a mano y
`pruebas/test_resumen.py`.
"""
import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from comun.repositorio import Repositorio, ruta_por_defecto
from servicio.control import ESTADO_CAPTURANDO, ESTADO_CERRADO, leer_estado

SIN_DATO = "—"
NOMBRE_DEL_CONTEO = {"pulsacion_tecla": "pulsaciones", "clic_boton": "clics", "scroll_paso": "pasos de rueda"}


class Opciones(argparse.Namespace):
    """Opciones de la línea de comandos, con sus tipos."""

    base: str | None = None


def _miles(numero: int) -> str:
    """Un entero con espacio como separador de miles: `12 345`."""
    return f"{numero:,}".replace(",", " ")


def _hace(segundos: float) -> str:
    """Cuánto tiempo pasó, en palabras cortas: `hace 3 s`, `hace 4 min`, `hace 2 h`."""
    if segundos < 60:
        return f"hace {int(segundos)} s"
    if segundos < 3600:
        return f"hace {int(segundos // 60)} min"
    return f"hace {int(segundos // 3600)} h"


def resumir(repositorio: Repositorio, ahora: datetime | None = None) -> str:
    """El resumen de la base como texto de varias líneas.

    ahora: la hora que se toma como "ahora"; por defecto la del sistema (las pruebas pasan una fija).
    """
    ahora = ahora or datetime.now()
    estado = leer_estado(repositorio, ahora)
    lineas: list[str] = []

    if estado.ultimo_latido is None:
        lineas.append("Servicio: nunca se ha iniciado en esta base de datos")
    else:
        edad = (ahora - datetime.fromisoformat(estado.ultimo_latido)).total_seconds()
        if estado.estado == ESTADO_CERRADO:
            vivo = "cerrado de forma ordenada"
        else:
            vivo = "en marcha" if estado.en_marcha else "DETENIDO (sin latido reciente)"
        lineas.append(f"Servicio: {vivo} · último latido {_hace(edad)}")
    capturando = "capturando" if estado.estado == ESTADO_CAPTURANDO else "detenida"
    lineas.append(f"Captura: {capturando} · orden de la interfaz: {estado.orden}")

    equipos = repositorio.listar_equipos()
    lineas.append(f"Equipo: {equipos[0][1] if equipos else SIN_DATO}")
    sesion = repositorio.ultima_sesion()
    if sesion is None:
        lineas.append("Sesión: todavía no hay")
    else:
        situacion = "en curso" if sesion.en_curso else f"cerrada ({sesion.tipo_cierre})"
        actividad = f"teclado {sesion.seg_actividad_teclado} s, mouse {sesion.seg_actividad_mouse} s"
        lineas.append(f"Sesión #{sesion.id}: {situacion}, iniciada {sesion.inicio} · actividad: {actividad}")

    perifericos = repositorio.listar_perifericos()
    lineas.append(f"Periféricos: {len(perifericos)}")
    for periferico in perifericos:
        nombre = periferico.etiqueta or "por confirmar"
        retirado = "" if periferico.activo else " (retirado)"
        lineas.append(f"  · {nombre} · {periferico.tipo} {periferico.fabricante} {periferico.modelo}{retirado}")
        for uso in periferico.usos:
            limite = f" de {_miles(uso.limite)} por elemento = {uso.porcentaje:.0f} %" if uso.limite is not None and uso.porcentaje is not None else ""
            lineas.append(f"      {NOMBRE_DEL_CONTEO.get(uso.tipo_conteo, uso.tipo_conteo)}: {_miles(uso.total)} en total; el más usado lleva {_miles(uso.mayor_uso)}{limite}")

    alertas = repositorio.listar_alertas()
    pendientes = sum(1 for alerta in alertas if alerta.estado == "pendiente")
    lineas.append(f"Alertas: {pendientes} pendientes, {len(alertas) - pendientes} enviadas")

    incidentes = Counter(incidente.tipo for incidente in repositorio.incidentes_recientes())
    if incidentes:
        detalle = ", ".join(f"{tipo}: {cantidad}" for tipo, cantidad in sorted(incidentes.items()))
        lineas.append(f"Incidentes recientes: {sum(incidentes.values())} ({detalle})")
    else:
        lineas.append("Incidentes recientes: ninguno")
    return "\n".join(lineas)


def principal(argumentos: Sequence[str] | None = None) -> int:
    """Imprime el resumen. Devuelve 0, o 2 si `--base` apunta a un archivo que no existe."""
    analizador = argparse.ArgumentParser(prog="python -m servicio.resumen", description="Resumen de la base de datos del servicio.")
    _ = analizador.add_argument("--base", help="archivo de la base de datos (por defecto, la del sistema o CAPTURADOR_RUTA_DB)")
    opciones = analizador.parse_args(argumentos, namespace=Opciones())
    ruta = Path(opciones.base) if opciones.base else ruta_por_defecto()
    if not ruta.is_file():
        # Con una ruta que no existe, `Repositorio` crearía una base vacía y el resumen parecería de un servicio que nunca corrió.
        print(f"No existe la base de datos: {ruta}", file=sys.stderr)
        return 2
    with Repositorio(ruta) as repo:
        print(resumir(repo))
    return 0


if __name__ == "__main__":
    sys.exit(principal())
