
"""Pantalla P05: mapa de calor y patrones de uso (RF15, RF22, RF23).

Consulta los horarios de eventos almacenados en SQLite, construye
una matriz de 7 días por 24 horas y la representa en un Canvas.
Muestra patrones calculados por los módulos de análisis existentes.

Se relaciona con: usa analisis/mapa_de_calor.py,
analisis/patrones.py, comun/repositorio.py y ui/pantalla_base.py
· la registra ui/registro.py.
"""

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import ttk
from typing import ClassVar, override

from analisis.mapa_de_calor import calcular_matriz, valor_maximo
from analisis.patrones import (
    Tramo,
    dia_mas_activo,
    hora_pico,
    tramos_sin_pausa,
)
from ui.estilo import FONDO
from ui.pantalla_base import Pantalla


DIAS_SEMANA: tuple[str, ...] = (
    "Lun",
    "Mar",
    "Mié",
    "Jue",
    "Vie",
    "Sáb",
    "Dom",
)

DIAS_COMPLETOS: tuple[str, ...] = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

DISPOSITIVOS: dict[str, str | None] = {
    "Teclado y mouse": None,
    "Teclado": "teclado",
    "Mouse": "mouse",
}

# Escala de menor a mayor actividad, similar al mockup.
COLORES_CALOR: tuple[str, ...] = (
    "#fff1db",
    "#ffdfad",
    "#ffb86b",
    "#fb863c",
    "#e64d20",
    "#a52516",
)


# Color de todos los textos del lienzo (horas, días y leyenda). Sin un color explícito, Tk usa el del sistema: en macOS
# con el modo oscuro es BLANCO y, sobre el fondo claro de esta pantalla, el texto casi no se lee. En Windows el color por
# defecto sería negro, pero así el texto se ve igual con cualquier tema.
COLOR_TEXTO = "#222222"


def validar_periodo(desde: str, hasta: str) -> tuple[str, str]:
    """Valida las fechas y produce un intervalo ISO semiabierto."""
    try:
        inicio = datetime.strptime(
            desde.strip(), "%d/%m/%Y"
        ).date()
        fin = datetime.strptime(
            hasta.strip(), "%d/%m/%Y"
        ).date()
    except ValueError as error:
        raise ValueError(
            "Las fechas deben tener el formato DD/MM/AAAA."
        ) from error

    if inicio > fin:
        raise ValueError(
            "La fecha Desde no puede ser posterior a Hasta."
        )

    if fin == date.max:
        raise ValueError(
            "La fecha Hasta supera el rango permitido."
        )

    # El repositorio excluye el extremo final.
    # Agregar un día permite incluir la fecha Hasta completa.
    return (
        inicio.isoformat(),
        (fin + timedelta(days=1)).isoformat(),
    )


def color_de_actividad(valor: int, maximo: int) -> str:
    """Devuelve un color proporcional a la cantidad de eventos."""
    if valor <= 0 or maximo <= 0:
        return COLORES_CALOR[0]

    indice = round(
        (valor / maximo) * (len(COLORES_CALOR) - 1)
    )
    indice = max(
        1,
        min(indice, len(COLORES_CALOR) - 1),
    )

    return COLORES_CALOR[indice]


def describir_patrones(
    matriz: list[list[int]],
    tramos: list[Tramo],
) -> str:
    """Prepara un resumen de patrones sin utilizar datos de teclas."""
    hora = hora_pico(matriz)
    dia = dia_mas_activo(matriz)

    if hora is None or dia is None:
        return (
            "No se detectaron patrones porque no hay eventos "
            "en el período seleccionado."
        )

    mensajes = [
        f"• Hora pico de actividad: {hora:02d}:00 h.",
        f"• Día de mayor actividad: {DIAS_COMPLETOS[dia]}.",
    ]

    if tramos:
        mayor_duracion = max(
            tramo.minutos for tramo in tramos
        )

        mensajes.append(
            f"• Tramos prolongados: {len(tramos)} detectados "
            + f"(el más largo duró {mayor_duracion} minutos)."
        )
    else:
        mensajes.append(
            "• No se detectaron tramos de 120 minutos o más "
            + "sin pausas superiores a 5 minutos."
        )


    return "\n".join(mensajes)


class PantallaP05(Pantalla):
    """Muestra la distribución horaria y los patrones de actividad."""

    TITULO: ClassVar[str] = "Análisis de uso"
    SUBTITULO: ClassVar[str] = (
        "Mapa de calor del uso por día y hora, y patrones detectados."
    )

    @override
    def construir(self) -> None:
        """Construye los filtros, el lienzo y el resumen de patrones."""
        hoy = date.today()
        inicio = hoy - timedelta(days=30)

        self.desde: tk.StringVar = tk.StringVar(
            value=inicio.strftime("%d/%m/%Y")
        )
        self.hasta: tk.StringVar = tk.StringVar(
            value=hoy.strftime("%d/%m/%Y")
        )
        self.dispositivo: tk.StringVar = tk.StringVar(
            value="Teclado y mouse"
        )

        self.resumen: tk.StringVar = tk.StringVar(value="")
        self.texto_patrones: tk.StringVar = tk.StringVar(value="")

        self.matriz: list[list[int]] = [
            [0] * 24 for _ in range(7)
        ]
        self.cantidad_eventos: int = 0

        # ----------------------------------------
        # FILTROS
        # ----------------------------------------
        filtros = ttk.Frame(self)
        filtros.pack(fill="x", pady=(0, 12))

        ttk.Label(
            filtros, text="Desde:"
        ).pack(side="left")

        ttk.Entry(
            filtros,
            textvariable=self.desde,
            width=13,
        ).pack(side="left", padx=(8, 16))

        ttk.Label(
            filtros, text="Hasta:"
        ).pack(side="left")

        ttk.Entry(
            filtros,
            textvariable=self.hasta,
            width=13,
        ).pack(side="left", padx=(8, 16))

        ttk.Label(
            filtros, text="Dispositivo:"
        ).pack(side="left")

        selector = ttk.Combobox(
            filtros,
            textvariable=self.dispositivo,
            values=tuple(DISPOSITIVOS),
            state="readonly",
            width=18,
        )
        selector.pack(side="left", padx=(8, 12))

        ttk.Button(
            filtros,
            text="Actualizar",
            command=self.actualizar,
        ).pack(side="left")

        # ----------------------------------------
        # MAPA DE CALOR
        # ----------------------------------------
        bloque_mapa = ttk.LabelFrame(
            self,
            text="Mapa de calor por día y hora",
            padding=8,
        )
        bloque_mapa.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        self.canvas: tk.Canvas = tk.Canvas(
            bloque_mapa,
            background=FONDO,
            highlightthickness=0,
            height=250,
        )
        self.canvas.pack(
            fill="both",
            expand=True,
        )

        # Vuelve a dibujar al maximizar o redimensionar.
        _ = self.canvas.bind(
            "<Configure>",
            self.redibujar,
        )

        ttk.Label(
            bloque_mapa,
            textvariable=self.resumen,
            style="Suave.TLabel",
        ).pack(anchor="w", pady=(5, 0))

        # ----------------------------------------
        # PATRONES DETECTADOS
        # ----------------------------------------
        bloque_patrones = ttk.LabelFrame(
            self,
            text="Patrones detectados",
            padding=12,
        )
        bloque_patrones.pack(fill="x")

        ttk.Label(
            bloque_patrones,
            textvariable=self.texto_patrones,
            justify="left",
            wraplength=750,
        ).pack(anchor="w", fill="x")

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Consulta nuevamente los datos al visitar la pantalla."""
        _ = parametros
        self.actualizar()

    def actualizar(self) -> None:
        """Consulta eventos y calcula la matriz y los patrones reales."""
        try:
            desde, hasta = validar_periodo(
                self.desde.get(),
                self.hasta.get(),
            )

            nombre_dispositivo = self.dispositivo.get()
            if nombre_dispositivo not in DISPOSITIVOS:
                raise ValueError(
                    "Selecciona un dispositivo válido."
                )

            tipo = DISPOSITIVOS[nombre_dispositivo]

            # El repositorio devuelve solo fechas de eventos.
            # No se consultan ni muestran secuencias de teclas.
            horas = self.repo.horas_de_eventos(
                desde=desde,
                hasta=hasta,
                tipo_dispositivo=tipo,
            )

            matriz = calcular_matriz(horas)
            tramos = tramos_sin_pausa(horas)

        except ValueError as error:
            self.matriz = [[0] * 24 for _ in range(7)]
            self.cantidad_eventos = 0
            self.resumen.set(str(error))
            self.texto_patrones.set(
                "Corrige los filtros para consultar el análisis."
            )
            self.redibujar()
            return

        self.matriz = matriz
        self.cantidad_eventos = len(horas)

        if horas:
            self.resumen.set(
                f"Se analizaron {len(horas)} eventos. "
                + "Los colores representan actividad acumulada "
                + "por día de la semana y hora."
            )
        else:
            self.resumen.set(
                "No hay eventos para el período y dispositivo "
                + "seleccionados."
            )


        self.texto_patrones.set(
            describir_patrones(matriz, tramos)
        )

        self.redibujar()

    def redibujar(self, _evento: object = None) -> None:
        """Dibuja las 168 celdas usando el espacio disponible."""
        lienzo = self.canvas
        lienzo.delete("all")

        ancho = lienzo.winfo_width()
        alto = lienzo.winfo_height()

        # Antes de que Tkinter termine el diseño, el Canvas
        # puede tener un tamaño provisional de un píxel.
        if ancho < 250 or alto < 200:
            return

        izquierda = 52
        arriba = 34
        espacio_derecho = 12

        ancho_celda = (
            ancho - izquierda - espacio_derecho
        ) / 24

        alto_celda = min(
            36.0,
            max(17.0, (alto - 105) / 7),
        )

        maximo = valor_maximo(self.matriz)

        # Encabezados para las 24 horas.
        for hora in range(24):
            x = izquierda + (hora + 0.5) * ancho_celda

            # En ventanas pequeñas alterna las etiquetas
            # para que los números no se superpongan.
            if ancho_celda >= 25 or hora % 2 == 0:
                _ = lienzo.create_text(
                    x,
                    arriba - 12,
                    text=f"{hora:02d}h",
                    font="TkDefaultFont",
                    fill=COLOR_TEXTO,
                )

        for dia in range(7):
            y = arriba + dia * alto_celda

            _ = lienzo.create_text(
                izquierda - 9,
                y + alto_celda / 2,
                text=DIAS_SEMANA[dia],
                anchor="e",
                font="TkDefaultFont",
                fill=COLOR_TEXTO,
            )

            for hora in range(24):
                x = izquierda + hora * ancho_celda
                cantidad = self.matriz[dia][hora]

                _ = lienzo.create_rectangle(
                    x + 1,
                    y + 1,
                    x + ancho_celda - 1,
                    y + alto_celda - 1,
                    fill=color_de_actividad(
                        cantidad, maximo
                    ),
                    outline="",
                )

        # Leyenda de intensidad bajo la matriz.
        leyenda_y = arriba + 7 * alto_celda + 23

        _ = lienzo.create_text(
            izquierda,
            leyenda_y,
            text="Pocos eventos",
            anchor="w",
            font="TkDefaultFont",
            fill=COLOR_TEXTO,
        )

        inicio_escala = izquierda + 115
        ancho_color = 32

        for indice, color in enumerate(COLORES_CALOR):
            x = inicio_escala + indice * ancho_color

            _ = lienzo.create_rectangle(
                x,
                leyenda_y - 8,
                x + ancho_color,
                leyenda_y + 8,
                fill=color,
                outline="",
            )

        _ = lienzo.create_text(
            inicio_escala + len(COLORES_CALOR) * ancho_color + 12,
            leyenda_y,
            text="Muchos eventos",
            anchor="w",
            font="TkDefaultFont",
            fill=COLOR_TEXTO,
        )
