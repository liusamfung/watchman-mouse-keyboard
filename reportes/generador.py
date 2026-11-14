"""Generador de reportes CSV (RF14).

Escribe en un archivo las filas que ya leyó el repositorio. No lee la base de datos ni tiene pantalla:
la interfaz (pantalla P06) llama a `comun/repositorio.py` para obtener las filas y se las pasa aquí.

Formato de los archivos: UTF-8 con BOM (`utf-8-sig`) para que Excel muestre bien las tildes, separador coma,
`newline=""` (para que csv maneje los saltos de línea dentro de un valor) y un valor `None` sale como celda vacía.

Privacidad (RNF4): el reporte de eventos no tiene columna de tecla. El de contadores sí muestra el elemento
(la tecla), porque ya viene agregado por día.

Cómo funciona: `escribir_csv` es la función genérica: crea la carpeta si falta, escribe el encabezado y una
fila por cada elemento, y devuelve cuántas filas escribió. Cada `reporte_*` solo define sus encabezados en
español y llama a `escribir_csv`.

Se relaciona con: usa la biblioteca estándar (`csv`, `pathlib`) · lo usan la pantalla P06 (cuando exista) y
`pruebas/test_reportes.py`. Las filas las entrega `comun/repositorio.py` (`filas_de_eventos`,
`filas_de_totales_diarios`, `filas_de_contadores`, `filas_de_alertas`).
"""

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path


def escribir_csv(ruta: Path, columnas: Sequence[str], filas: Iterable[Sequence[object]]) -> int:
    """Escribe el archivo y devuelve cuántas filas escribió (sin contar el encabezado).

    ruta: archivo de destino. Si la carpeta no existe, se crea.
    columnas: nombres de las columnas, que van en la primera línea.
    filas: cada fila como secuencia de valores; `None` se escribe como celda vacía.
    """
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    cantidad = 0
    with destino.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo)
        # Se usa `writerows` y no `writerow`: `writerows` devuelve None, así que no hace falta guardar un
        # resultado (guardarlo en `_` daba una advertencia de tipo `Any` en basedpyright).
        escritor.writerows([list(columnas)])
        for fila in filas:
            # csv ya escribe None como vacío; se hace explícito para que el porqué quede a la vista.
            escritor.writerows([["" if valor is None else valor for valor in fila]])
            cantidad += 1
    return cantidad


def reporte_eventos(ruta: Path, filas: Iterable[Sequence[object]]) -> int:
    """Reporte de eventos: id, sesión, periférico, tipo de evento, fecha y hora, x, y. Sin columna de tecla (RNF4)."""
    columnas = ["id", "sesión", "periférico", "tipo de evento", "fecha y hora", "x", "y"]
    return escribir_csv(ruta, columnas, filas)


def reporte_totales_diarios(ruta: Path, filas: Iterable[Sequence[object]]) -> int:
    """Reporte de totales diarios: fecha, periférico, tipo de conteo y total del día."""
    columnas = ["fecha", "periférico", "tipo de conteo", "total"]
    return escribir_csv(ruta, columnas, filas)


def reporte_contadores(ruta: Path, filas: Iterable[Sequence[object]]) -> int:
    """Reporte de contadores: fecha, periférico, tipo de conteo, elemento y cantidad (el elemento es la tecla, ya agregada por día)."""
    columnas = ["fecha", "periférico", "tipo de conteo", "elemento", "cantidad"]
    return escribir_csv(ruta, columnas, filas)


def reporte_alertas(ruta: Path, filas: Iterable[Sequence[object]]) -> int:
    """Reporte de alertas: periférico, umbral, estado, intentos, fecha de creación y fecha de envío."""
    columnas = ["periférico", "umbral", "estado", "intentos", "creada", "enviada"]
    return escribir_csv(ruta, columnas, filas)
