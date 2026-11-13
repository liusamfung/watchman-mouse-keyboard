"""Colores, fuentes y estilos `ttk` de la interfaz, para que todas las pantallas se vean igual y parecidas a los mockups.

Cómo funciona: `aplicar_estilo` se llama una sola vez al crear la ventana. Elige el tema `clam` (se ve igual en Windows, macOS
y Linux, y a diferencia del tema nativo de Windows deja cambiar los colores de botones y tablas) y define los estilos con nombre
que usan las pantallas: `Titulo.TLabel`, `Subtitulo.TLabel`, `Exito.TLabel`, `Peligro.TLabel`, etc.

Pensado para Windows (el sistema de destino):
- Las fuentes salen de las fuentes con nombre de Tk (`TkDefaultFont`), que en Windows es Segoe UI: no se escribe ningún nombre
  de fuente a mano.
- El alto de las filas de las tablas sale de la fuente, no de un número fijo, para que no se corte el texto con pantallas de alta
  densidad (escala del 125 % o 150 %).
- Solo se usan opciones que existen en Tk 8.6, que es la versión de Python 3.12 y 3.13 en Windows.

Se relaciona con: usa `tkinter.ttk` · lo usan `ui/aplicacion.py` (la llama al crear la ventana) y `ui/componentes.py` (colores de las
filas); las pantallas pueden importar las constantes de colores.
"""
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

AZUL_ENCABEZADO = "#2f5f8a"
TEXTO_ENCABEZADO = "#ffffff"
FONDO = "#f0f0f0"
FONDO_MENU = "#e3e8ee"
FONDO_MENU_ACTIVO = "#c9dcee"
FONDO_MENU_SOBRE = "#d5dfe9"
FONDO_BARRA = "#e6e6e6"
TEXTO_SUAVE = "#666666"
VERDE = "#1e7a34"
ROJO = "#c0392b"
FONDO_ALERTA = "#fde9e4"  # fila de una tabla con una alerta
TEXTO_RETIRADO = "#8a8a8a"  # fila de un periférico retirado

PROPORCION_TITULO = 1.6  # el título de cada pantalla es 1,6 veces el tamaño de la fuente normal
PROPORCION_ENCABEZADO = 1.25
MARGEN_DE_FILA = 8  # píxeles que se suman al alto de la letra para el alto de una fila de tabla


@dataclass(slots=True)
class Fuentes:
    """Las fuentes con nombre que crea `aplicar_estilo`. Hay que conservarla mientras viva la ventana: si se pierde, Tk las borra."""

    titulo: tkfont.Font
    encabezado: tkfont.Font
    negrita: tkfont.Font


def _derivada(raiz: tk.Misc, base: tkfont.Font, proporcion: float = 1.0, negrita: bool = False) -> tkfont.Font:
    """Una fuente con la misma familia que la normal del sistema, escalada y quizá en negrita.

    El tamaño puede ser negativo (Tk usa píxeles en vez de puntos); se conserva el signo para no cambiar la unidad.
    """
    return tkfont.Font(
        root=raiz,
        family=str(base.actual("family")),
        size=round(int(base.cget("size")) * proporcion),
        weight="bold" if negrita else "normal",
    )


def aplicar_estilo(raiz: tk.Misc) -> Fuentes:
    """Activa el tema `clam` y define los estilos con nombre de la interfaz. Devuelve las fuentes creadas, para que quien llama las conserve."""
    base = tkfont.nametofont("TkDefaultFont")
    fuentes = Fuentes(
        titulo=_derivada(raiz, base, PROPORCION_TITULO, negrita=True),
        encabezado=_derivada(raiz, base, PROPORCION_ENCABEZADO),
        negrita=_derivada(raiz, base, negrita=True),
    )
    estilo = ttk.Style(raiz)
    estilo.theme_use("clam")
    estilo.configure(".", background=FONDO)

    # Encabezado azul con el nombre del equipo y la sesión.
    estilo.configure("Encabezado.TFrame", background=AZUL_ENCABEZADO)
    estilo.configure("Encabezado.TLabel", background=AZUL_ENCABEZADO, foreground=TEXTO_ENCABEZADO)
    estilo.configure("EncabezadoGrande.TLabel", background=AZUL_ENCABEZADO, foreground=TEXTO_ENCABEZADO, font=fuentes.encabezado)

    # Menú de la izquierda: un botón plano por pantalla; el de la pantalla actual va resaltado y en negrita.
    estilo.configure("Menu.TFrame", background=FONDO_MENU)
    estilo.configure("Menu.TButton", background=FONDO_MENU, anchor="w", padding=(14, 9), relief="flat", borderwidth=0)
    estilo.map("Menu.TButton", background=[("active", FONDO_MENU_SOBRE)])
    estilo.configure("MenuActivo.TButton", background=FONDO_MENU_ACTIVO, anchor="w", padding=(14, 9), relief="flat",
                     borderwidth=0, font=fuentes.negrita)
    estilo.map("MenuActivo.TButton", background=[("active", FONDO_MENU_ACTIVO)])

    # Título y subtítulo de cada pantalla, y colores de estado para las etiquetas de las pantallas.
    estilo.configure("Titulo.TLabel", font=fuentes.titulo)
    estilo.configure("Subtitulo.TLabel", foreground=TEXTO_SUAVE)
    estilo.configure("Exito.TLabel", foreground=VERDE, font=fuentes.negrita)
    estilo.configure("Peligro.TLabel", foreground=ROJO, font=fuentes.negrita)
    estilo.configure("Suave.TLabel", foreground=TEXTO_SUAVE)

    # Barra de estado de abajo.
    estilo.configure("Barra.TFrame", background=FONDO_BARRA)
    estilo.configure("Barra.TLabel", background=FONDO_BARRA, foreground=TEXTO_SUAVE)

    # Tablas: el alto de la fila sale de la fuente (alta densidad en Windows) y los encabezados llevan relieve.
    alto_de_fila = int(base.metrics("linespace")) + MARGEN_DE_FILA
    estilo.configure("Treeview", rowheight=alto_de_fila)
    estilo.configure("Treeview.Heading", background="#e1e1e1", relief="raised", font=fuentes.negrita)
    return fuentes
