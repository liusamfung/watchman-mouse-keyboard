"""Pantalla P04 · Sesiones (RF12, RF23).

Qué muestra: las sesiones del equipo entre dos fechas (inicio, fin, tipo de cierre y tiempo de actividad de teclado y de mouse)
y, abajo, el total del día elegido, que es la SUMA de las sesiones que empezaron ese día (decisión de arquitectura 3 de
`CLAUDE.md`). Una sesión va desde que se inicia sesión en Windows (el servicio arranca con la tarea "al iniciar sesión") hasta que
se apaga el equipo. Si el equipo se apagó de golpe, el servicio cierra esa sesión como "inesperado" al volver a arrancar (RNF12),
así que un mismo día puede tener varias sesiones.

Cómo funciona: los campos "Desde" y "Hasta" aceptan fechas `dd/mm/aaaa`. "Filtrar" pide las sesiones al repositorio
(`listar_sesiones`) y las funciones puras de este archivo eligen las del rango y arman las filas. Al elegir una fila, el total
de abajo pasa a ser el de ese día (`actividad_del_dia`). Una sesión todavía abierta se muestra "En curso" y no rompe nada.

Las funciones que no dibujan (`leer_fecha`, `rango_por_defecto`, `sesiones_del_rango`, `filas_de_sesiones`, `titulo_del_total`…)
se prueban sin abrir una ventana en `pruebas/test_pantalla_p04.py`.

Mockup: `docs/mockups/P04_Sesiones.png` (su subtítulo decía "desde que se enciende el equipo"; aquí va el texto correcto).
Guía: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py`, `ui/componentes.py` (`Tabla`), `ui/formato.py` y, por el contexto, el repositorio
(`listar_sesiones`, `actividad_del_dia`) · la registra `ui/registro.py` y la prueba `pruebas/test_pantalla_p04.py`.
"""
import tkinter as tk
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import ClassVar, override

from comun.repositorio import FilaSesion
from ui.componentes import Columna, FilaDeTabla, Tabla
from ui.formato import SIN_DATO, duracion, fecha_legible, hora_legible
from ui.pantalla_base import Pantalla

DIAS_POR_DEFECTO = 14  # al abrir, se ven las dos últimas semanas: alcanza para comparar días sin llenar la tabla
FORMATO_DE_FECHA = "%d/%m/%Y"  # como se escriben las fechas en Perú y en los mockups
CIERRES: dict[str, str] = {"normal": "Normal", "inesperado": "Apagado inesperado"}
EN_CURSO = "En curso"

NOTA_GENERAL = "El total de un día es la suma de las sesiones que empezaron ese día."
NOTA_INESPERADO = (
    "Un apagado inesperado cerró una sesión de este día; al volver a iniciar sesión en Windows se abrió una nueva."
)


# ---------- Funciones puras: fechas, filtro y textos, sin usar Tk ----------


def leer_fecha(texto: str) -> date:
    """Convierte lo que escribió la persona en una fecha. Acepta `05/10/2026` y también `2026-10-05`.

    Lanza ValueError con un mensaje en español si el texto no es una fecha válida (por ejemplo `31/02/2026`).
    """
    limpio = texto.strip()
    for formato in (FORMATO_DE_FECHA, "%Y-%m-%d"):
        try:
            return datetime.strptime(limpio, formato).date()
        except ValueError:
            continue
    raise ValueError(f"«{limpio}» no es una fecha válida. Escríbela como dd/mm/aaaa, por ejemplo 05/10/2026.")


def texto_de_fecha(dia: date) -> str:
    """Una fecha como se escribe en los campos: `05/10/2026`."""
    return dia.strftime(FORMATO_DE_FECHA)


def dia_de(sesion: FilaSesion) -> date:
    """El día en que empezó la sesión: es el día al que se suma (RF12)."""
    return datetime.fromisoformat(sesion.inicio).date()


def rango_por_defecto(sesiones: Iterable[FilaSesion], hoy: date, dias: int = DIAS_POR_DEFECTO) -> tuple[date, date]:
    """El rango que se muestra al abrir la pantalla: los últimos `dias` días hasta la sesión más reciente.

    Se toma la sesión más reciente y no "hoy" para que un equipo que no se usó en días igual muestre algo. Sin sesiones, hasta hoy.
    """
    hasta = max((dia_de(s) for s in sesiones), default=hoy)
    return hasta - timedelta(days=dias - 1), hasta


def sesiones_del_rango(sesiones: Iterable[FilaSesion], desde: date, hasta: date) -> list[FilaSesion]:
    """Las sesiones que empezaron entre `desde` y `hasta`, AMBOS incluidos (así lo entiende quien escribe "hasta el 09/10").

    Conserva el orden en que llegan (el repositorio las da de la más reciente a la más antigua).
    """
    return [s for s in sesiones if desde <= dia_de(s) <= hasta]


def texto_fin(sesion: FilaSesion) -> str:
    """La hora de fin; `En curso` si la sesión sigue abierta. Si terminó otro día (pasó la medianoche), lleva también la fecha."""
    if sesion.fin is None:
        return EN_CURSO
    if datetime.fromisoformat(sesion.fin).date() != dia_de(sesion):
        return f"{fecha_legible(sesion.fin)} {hora_legible(sesion.fin)}"
    return hora_legible(sesion.fin)


def texto_cierre(sesion: FilaSesion) -> str:
    """`Normal`, `Apagado inesperado` o `—` mientras la sesión está en curso."""
    if sesion.tipo_cierre is None:
        return SIN_DATO
    return CIERRES.get(sesion.tipo_cierre, sesion.tipo_cierre.capitalize())


def filas_de_sesiones(sesiones: Iterable[FilaSesion]) -> list[FilaDeTabla]:
    """Una fila por sesión, con el id de la sesión como identificador de la fila."""
    return [
        FilaDeTabla(
            (
                fecha_legible(s.inicio),
                hora_legible(s.inicio),
                texto_fin(s),
                texto_cierre(s),
                duracion(s.seg_actividad_teclado),
                duracion(s.seg_actividad_mouse),
            ),
            id=str(s.id),
        )
        for s in sesiones
    ]


def sesiones_del_dia(sesiones: Iterable[FilaSesion], dia: date) -> list[FilaSesion]:
    """Las sesiones que empezaron ese día."""
    return [s for s in sesiones if dia_de(s) == dia]


def titulo_del_total(dia: date, cantidad: int) -> str:
    """El título del recuadro de abajo: `Total del día seleccionado (06/10/2026 · 2 sesiones)`."""
    return f"Total del día seleccionado ({texto_de_fecha(dia)} · {cantidad} {'sesión' if cantidad == 1 else 'sesiones'})"


def nota_del_dia(sesiones: Iterable[FilaSesion]) -> str:
    """La nota bajo el total: si alguna sesión de ese día terminó en un apagado inesperado, se explica por qué hay varias."""
    return NOTA_INESPERADO if any(s.tipo_cierre == "inesperado" for s in sesiones) else NOTA_GENERAL


# ---------- La pantalla ----------


class PantallaP04(Pantalla):
    """Sesiones del equipo y total del día elegido, que es la suma de sus sesiones (RF12)."""

    TITULO: ClassVar[str] = "Sesiones"
    SUBTITULO: ClassVar[str] = (
        "Una sesión va desde que se inicia sesión en Windows hasta que se apaga el equipo. "
        "El total diario es la suma de sus sesiones."
    )

    @override
    def construir(self) -> None:
        """Dibuja el filtro de fechas, la tabla, el recuadro del total del día y la nota. Se llama una sola vez."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._sesiones: dict[str, FilaSesion] = {}  # id de fila → sesión mostrada
        self._rango_elegido: bool = False  # False hasta que la persona filtra: mientras tanto se usa el rango por defecto

        filtro = ttk.Frame(self)
        filtro.grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(filtro, text="Desde:").pack(side="left", padx=(0, 6))
        self.desde: tk.StringVar = tk.StringVar(self)
        ttk.Entry(filtro, textvariable=self.desde, width=12).pack(side="left")
        ttk.Label(filtro, text="Hasta:").pack(side="left", padx=(16, 6))
        self.hasta: tk.StringVar = tk.StringVar(self)
        campo_hasta = ttk.Entry(filtro, textvariable=self.hasta, width=12)
        campo_hasta.pack(side="left")
        ttk.Button(filtro, text="Filtrar", command=self.filtrar).pack(side="left", padx=(16, 0))
        campo_hasta.bind("<Return>", lambda _evento: self.filtrar())

        columnas = [
            Columna("fecha", "Fecha", 110),
            Columna("inicio", "Inicio", 100),
            Columna("fin", "Fin", 120),
            Columna("cierre", "Cierre", 160),
            Columna("teclado", "Actividad teclado", 140),
            Columna("mouse", "Actividad mouse", 140),
        ]
        self.tabla: Tabla = Tabla(self, columnas, alto=8, al_elegir=self._al_elegir)
        self.tabla.grid(row=1, column=0, sticky="nsew")
        self.vacia: ttk.Label = ttk.Label(self, style="Suave.TLabel")
        self.vacia.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self.recuadro_total: ttk.LabelFrame = ttk.LabelFrame(self, text="Total del día seleccionado", padding=(14, 10))
        self.recuadro_total.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(self.recuadro_total, text="Actividad de teclado:", style="Suave.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 16))
        self.total_teclado: ttk.Label = ttk.Label(self.recuadro_total, text=SIN_DATO)
        self.total_teclado.grid(row=0, column=1, sticky="w")
        ttk.Label(self.recuadro_total, text="Actividad de mouse:", style="Suave.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 16), pady=(4, 0))
        self.total_mouse: ttk.Label = ttk.Label(self.recuadro_total, text=SIN_DATO)
        self.total_mouse.grid(row=1, column=1, sticky="w", pady=(4, 0))

        self.nota: ttk.Label = ttk.Label(self, text=NOTA_GENERAL, style="Suave.TLabel")
        self.nota.grid(row=4, column=0, sticky="w", pady=(8, 0))

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Refresca la lista cada vez que se muestra. La primera vez pone el rango por defecto (las dos últimas semanas)."""
        _ = parametros
        if not self._rango_elegido:
            desde, hasta = rango_por_defecto(self.repo.listar_sesiones(), date.today())
            self.desde.set(texto_de_fecha(desde))
            self.hasta.set(texto_de_fecha(hasta))
        self.refrescar()

    def filtrar(self) -> None:
        """Aplica el rango escrito. Si una fecha está mal escrita o el rango está al revés, avisa y no cambia la tabla."""
        try:
            desde, hasta = leer_fecha(self.desde.get()), leer_fecha(self.hasta.get())
        except ValueError as error:
            messagebox.showwarning("Fecha no válida", str(error), parent=self)
            return
        if desde > hasta:
            messagebox.showwarning("Rango no válido", "La fecha «Desde» debe ser anterior o igual a «Hasta».", parent=self)
            return
        self._rango_elegido = True
        self.refrescar()

    def refrescar(self) -> None:
        """Pide las sesiones, llena la tabla con las del rango y elige la primera fila (el día más reciente) para el total."""
        try:
            desde, hasta = leer_fecha(self.desde.get()), leer_fecha(self.hasta.get())
        except ValueError:
            desde, hasta = rango_por_defecto(self.repo.listar_sesiones(), date.today())
        sesiones = sesiones_del_rango(self.repo.listar_sesiones(), desde, hasta)
        self._sesiones = {str(s.id): s for s in sesiones}
        self.tabla.llenar(filas_de_sesiones(sesiones))
        if sesiones:
            self.vacia.configure(text="")
            primera = str(sesiones[0].id)
            self.tabla.arbol.selection_set(primera)  # dispara `_al_elegir`, que llena el total de ese día
            self.tabla.arbol.see(primera)
            self.mostrar_total(dia_de(sesiones[0]))
        else:
            self.vacia.configure(text=f"No hay sesiones entre el {texto_de_fecha(desde)} y el {texto_de_fecha(hasta)}.")
            self.recuadro_total.configure(text="Total del día seleccionado")
            self.total_teclado.configure(text=SIN_DATO)
            self.total_mouse.configure(text=SIN_DATO)
            self.nota.configure(text=NOTA_GENERAL)

    def _al_elegir(self, id_fila: str | None) -> None:
        """Al elegir una sesión, el total de abajo pasa a ser el de su día."""
        sesion = self._sesiones.get(id_fila) if id_fila is not None else None
        if sesion is not None:
            self.mostrar_total(dia_de(sesion))

    def mostrar_total(self, dia: date) -> None:
        """Muestra el total de actividad del día: la suma de sus sesiones, calculada por el repositorio (RF12)."""
        teclado, mouse = self.repo.actividad_del_dia(dia.isoformat())
        del_dia = sesiones_del_dia(self.repo.listar_sesiones(dia=dia.isoformat()), dia)
        self.recuadro_total.configure(text=titulo_del_total(dia, len(del_dia)))
        self.total_teclado.configure(text=duracion(teclado))
        self.total_mouse.configure(text=duracion(mouse))
        self.nota.configure(text=nota_del_dia(del_dia))
