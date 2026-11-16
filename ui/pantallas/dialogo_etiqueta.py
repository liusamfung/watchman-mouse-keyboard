"""Diálogo para confirmar la etiqueta de inventario de un periférico (RF18, issue #23).

Por qué existe: dos teclados idénticos comparten VID/PID y a veces no tienen número de serie, así que el sistema no puede saber
cuál es cuál. Un periférico nuevo queda "por confirmar" hasta que Soporte TI pega un sticker (por ejemplo `TEC-0042`) y lo
confirma aquí. Desde ese momento la asignación queda "confirmada" (decisión de arquitectura 5 de `CLAUDE.md`).

Cómo funciona: `DialogoEtiqueta` es una ventana modal con un campo de texto y los botones Confirmar y Cancelar. La lógica que
no dibuja está en funciones puras (`normalizar_etiqueta`, `validar_etiqueta`, `prefijo_sugerido`) y en `guardar_etiqueta`, que
llama a `Repositorio.asignar_etiqueta` y convierte sus errores (etiqueta vacía, repetida o periférico inexistente) en un aviso
claro para la persona, nunca en un error técnico. Se prueban sin abrir una ventana en `pruebas/test_pantalla_p02.py`.

Se relaciona con: usa `comun/repositorio.py` (`asignar_etiqueta` y el error `EtiquetaDuplicada`) y `tkinter` · lo abren
`ui/pantallas/pantalla_p02.py` (botón "Confirmar etiqueta…") y `ui/pantallas/pantalla_p03.py` (botón "Confirmar asignación").
"""
import tkinter as tk
from tkinter import messagebox, ttk

from comun.repositorio import EtiquetaDuplicada, Repositorio, ResumenPeriferico

LARGO_MAXIMO = 20  # una etiqueta de inventario es corta (`TEC-0042`); un texto más largo suele ser un error al escribir
PREFIJOS: dict[str, str] = {"teclado": "TEC-", "mouse": "MOU-"}  # el formato de los stickers de los mockups


def normalizar_etiqueta(texto: str) -> str:
    """La etiqueta sin espacios al borde y en mayúsculas (`  tec-0042 ` → `TEC-0042`), para que no haya dos versiones de la misma."""
    return texto.strip().upper()


def validar_etiqueta(texto: str) -> str | None:
    """Revisa una etiqueta ya normalizada. Devuelve el aviso que se le muestra a la persona, o None si está bien.

    No revisa si está repetida: eso lo sabe la base de datos (índice único de `periferico.etiqueta`), ver `guardar_etiqueta`.
    """
    if not texto:
        return "Escribe la etiqueta de inventario que está pegada en el periférico (por ejemplo, TEC-0042)."
    if any(caracter.isspace() for caracter in texto):
        return "La etiqueta no puede tener espacios. Usa un guion para separar (por ejemplo, TEC-0042)."
    if len(texto) > LARGO_MAXIMO:
        return f"La etiqueta es demasiado larga: tiene {len(texto)} caracteres y el máximo es {LARGO_MAXIMO}."
    return None


def prefijo_sugerido(tipo: str) -> str:
    """El comienzo de la etiqueta que se propone en el campo: `TEC-` para un teclado y `MOU-` para un mouse."""
    return PREFIJOS.get(tipo, "")


def guardar_etiqueta(repo: Repositorio, id_periferico: int, texto: str) -> str | None:
    """Normaliza, valida y guarda la etiqueta, y deja la asignación como confirmada (RF18).

    Devuelve None si se guardó, o el aviso para la persona si no: etiqueta vacía, con espacios, demasiado larga, ya usada por
    otro periférico, o periférico que ya no existe. Así la pantalla nunca muestra un error técnico.
    """
    etiqueta = normalizar_etiqueta(texto)
    aviso = validar_etiqueta(etiqueta)
    if aviso is not None:
        return aviso
    try:
        repo.asignar_etiqueta(id_periferico, etiqueta)
    except EtiquetaDuplicada:
        return f"La etiqueta {etiqueta} ya pertenece a otro periférico. Revisa el sticker o elige otra."
    except LookupError:
        return "Este periférico ya no existe en la base de datos. Actualiza la lista de periféricos."
    except ValueError:  # el repositorio también rechaza la etiqueta vacía; aquí no debería llegar, pero no se muestra el error técnico
        return "Escribe la etiqueta de inventario que está pegada en el periférico (por ejemplo, TEC-0042)."
    return None


def descripcion_del_periferico(periferico: ResumenPeriferico) -> str:
    """Una línea para reconocer el periférico en el diálogo: `Teclado · Logitech K120 · 046D:C31C`."""
    # Un modelo que no está en la tabla de modelos tiene fabricante y modelo "desconocido": se nombra una sola vez.
    modelo = periferico.modelo if periferico.fabricante in ("", periferico.modelo) else f"{periferico.fabricante} {periferico.modelo}"
    return f"{periferico.tipo.capitalize()} · {modelo} · {periferico.vid.upper()}:{periferico.pid.upper()}"


class DialogoEtiqueta(tk.Toplevel):
    """Ventana modal para escribir y confirmar la etiqueta de un periférico. `esperar()` dice si se confirmó."""

    def __init__(self, padre: tk.Misc, repo: Repositorio, periferico: ResumenPeriferico) -> None:
        """Crea el diálogo sobre la ventana de `padre`, con el prefijo sugerido ya escrito y el cursor en el campo."""
        super().__init__(padre)
        self._repo: Repositorio = repo
        self._id_periferico: int = periferico.id
        self._confirmado: bool = False

        self.title("Confirmar etiqueta de inventario")
        self.resizable(width=False, height=False)
        self.transient(padre.winfo_toplevel())  # va encima de la ventana principal y sin botón propio en la barra de tareas

        marco = ttk.Frame(self, padding=16)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text=descripcion_del_periferico(periferico)).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(marco, text="Escribe la etiqueta del sticker pegado en el periférico. La asignación quedará confirmada.",
                  style="Suave.TLabel", wraplength=360).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))
        ttk.Label(marco, text="Etiqueta:").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.texto: tk.StringVar = tk.StringVar(self, value=prefijo_sugerido(periferico.tipo))
        self.campo: ttk.Entry = ttk.Entry(marco, textvariable=self.texto, width=24)
        self.campo.grid(row=2, column=1, sticky="ew")

        botones = ttk.Frame(marco)
        botones.grid(row=3, column=0, columnspan=2, sticky="e", pady=(16, 0))
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right")
        ttk.Button(botones, text="Confirmar", command=self.confirmar).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _evento: self.confirmar())
        self.bind("<Escape>", lambda _evento: self.destroy())
        self.campo.focus_set()
        self.campo.icursor("end")

    def confirmar(self) -> None:
        """Guarda la etiqueta. Si hay un problema, muestra el aviso y deja el diálogo abierto para corregirla."""
        aviso = guardar_etiqueta(self._repo, self._id_periferico, self.texto.get())
        if aviso is not None:
            messagebox.showwarning("No se pudo confirmar la etiqueta", aviso, parent=self)
            self.campo.focus_set()
            return
        self._confirmado = True
        self.destroy()

    def esperar(self) -> bool:
        """Muestra el diálogo como modal (bloquea la ventana principal) hasta que se cierra. Devuelve True si se confirmó."""
        self.wait_visibility()  # grab_set falla si la ventana todavía no se ve
        self.grab_set()
        self.wait_window()
        return self._confirmado
