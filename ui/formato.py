"""Funciones para mostrar datos en las pantallas: porcentajes, duraciones y fechas legibles.

Son funciones puras: no usan Tk ni la base de datos, así que se prueban en cualquier sistema. Todas devuelven texto en español
listo para una etiqueta o una celda de tabla. Las fechas llegan como texto ISO 8601, igual que las entrega el repositorio.

Se relaciona con: usa solo la biblioteca estándar · lo usan las pantallas de `ui/pantallas/`, `ui/aplicacion.py` (encabezado)
y las pruebas de `pruebas/test_ui_formato.py`. Si una pantalla necesita otro formato, se pide en su issue: este archivo lo
cambia solo quien mantiene la base de la interfaz, para que no choquen los pull requests.
"""
from datetime import datetime, timedelta

SIN_DATO = "—"  # lo que se muestra cuando un dato no existe (por ejemplo, un periférico sin límite)


def porcentaje(valor: float | None) -> str:
    """Un porcentaje entero con espacio antes del signo: `91 %`. Sin dato (None), `—`.

    Redondea al entero más cercano y los .5 hacia arriba (91,5 → 92); el redondeo normal de Python iría al par más cercano.
    """
    if valor is None:
        return SIN_DATO
    return f"{int(valor + 0.5)} %"


def duracion(segundos: int) -> str:
    """Una duración corta: `45 s`, `47 min`, `3 h 12 min` o `5 h` (sin los minutos si son cero). Los negativos cuentan como cero."""
    segundos = max(segundos, 0)
    if segundos < 60:
        return f"{segundos} s"
    horas, minutos = divmod(segundos // 60, 60)
    if horas == 0:
        return f"{minutos} min"
    return f"{horas} h" if minutos == 0 else f"{horas} h {minutos} min"


def fecha_legible(texto: str | None) -> str:
    """La fecha de un texto ISO 8601 como `05/11/2026`. Sin dato (None o vacío), `—`. Lanza ValueError si no es una fecha."""
    if not texto:
        return SIN_DATO
    return datetime.fromisoformat(texto).strftime("%d/%m/%Y")


def hora_legible(texto: str | None) -> str:
    """La hora de un texto ISO 8601 en formato de 12 horas: `08:02 a. m.`, `12:30 p. m.`. Sin dato, `—`.

    Se arma a mano y no con `%p` porque `strftime` depende del idioma del sistema y en Windows en español daría `a.m.` sin espacio.
    """
    if not texto:
        return SIN_DATO
    momento = datetime.fromisoformat(texto)
    hora_12 = momento.hour % 12 or 12
    return f"{hora_12:02d}:{momento.minute:02d} {'a. m.' if momento.hour < 12 else 'p. m.'}"


def fecha_hora_legible(texto: str | None, ahora: datetime | None = None) -> str:
    """Fecha y hora para frases: `hoy a las 08:02 a. m.`, `ayer a las 05:10 p. m.` o `el 05/11/2026 a las 08:02 a. m.`.

    ahora: el momento que se toma como "ahora"; por defecto la hora del sistema. Se recibe como parámetro para poder probarla.
    Sin dato, `—`. Lanza ValueError si el texto no es una fecha.
    """
    if not texto:
        return SIN_DATO
    momento = datetime.fromisoformat(texto)
    hoy = (ahora or datetime.now()).date()
    if momento.date() == hoy:
        dia = "hoy"
    elif momento.date() == hoy - timedelta(days=1):
        dia = "ayer"
    else:
        dia = f"el {fecha_legible(texto)}"
    return f"{dia} a las {hora_legible(texto)}"
