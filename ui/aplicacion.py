"""La ventana principal de la interfaz: encabezado, menú de la izquierda, pantalla actual y barra de estado.

Cómo funciona: `Aplicacion` dibuja el marco que mostró el mockup (banda azul con el nombre del equipo y la sesión, menú a la izquierda,
título y subtítulo de la pantalla, y barra de estado abajo) y administra las pantallas. Cada pantalla se crea la primera vez que se
visita (`construir`) y se apila en el mismo lugar con las demás; `mostrar` trae una al frente y llama a su `al_mostrar`, que refresca
sus datos. Si una pantalla falla al crearse o al refrescarse, se avisa con un cuadro de mensaje y la ventana sigue funcionando.

Esta interfaz la usa Soporte TI en el PC del trabajador (RF23); no es la del trabajador, que no ve nada (RNF11). La base de datos se abre
con `Repositorio`: la ventana y las pantallas nunca ejecutan SQL.

Se relaciona con: usa `ui/registro.py` (las pantallas), `ui/pantalla_base.py` (`Contexto`), `ui/estilo.py`, `ui/formato.py` y
`comun/repositorio.py` (equipo y última sesión del encabezado) · la abre `ui/__main__.py` y la prueba `pruebas/test_ui_aplicacion.py`.
"""
import tkinter as tk
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from tkinter import messagebox, ttk
from typing import cast

from comun.repositorio import Repositorio
from ui.estilo import Fuentes, aplicar_estilo
from ui.formato import fecha_hora_legible
from ui.pantalla_base import Contexto, Pantalla
from ui.registro import ORDEN_DEL_MENU, PANTALLA_INICIAL, PANTALLAS

TITULO_DE_LA_VENTANA = "Capturador y Auditor de Eventos de Entrada · Soporte TI"
TAMANO_INICIAL = "1000x640"
TAMANO_MINIMO = (900, 560)
ANCHO_DEL_MENU = 180


def _texto_de(widget: ttk.Label | ttk.Button, opcion: str) -> str:
    """El valor de una opción de un widget (`text`, `style`) como texto. Tk lo devuelve sin tipo, y así queda tipado."""
    return str(cast(object, widget.cget(opcion)))


class Aplicacion(tk.Tk):
    """La ventana principal. Se crea con un repositorio ya abierto y se cierra la base desde quien la creó."""

    def __init__(
        self,
        repo: Repositorio,
        ruta_db: Path,
        pantallas: Mapping[str, type[Pantalla]] | None = None,
        orden_del_menu: Sequence[str] | None = None,
        al_fallar: Callable[[str, Exception], None] | None = None,
    ) -> None:
        """Crea la ventana y muestra la pantalla inicial.

        repo, ruta_db: la base de datos que se muestra (la ruta solo se usa para escribirla en la barra de estado).
        pantallas, orden_del_menu: por defecto las de `ui/registro.py`; las pruebas pasan unas falsas.
        al_fallar: qué hacer cuando una pantalla falla (recibe el título de la pantalla y el error); por defecto, un cuadro de mensaje.
        """
        super().__init__()
        self.title(TITULO_DE_LA_VENTANA)
        self.geometry(TAMANO_INICIAL)
        self.minsize(*TAMANO_MINIMO)
        self._fuentes: Fuentes = aplicar_estilo(self)  # se conservan: si se pierden, Tk borra las fuentes

        self._clases: dict[str, type[Pantalla]] = dict(PANTALLAS if pantallas is None else pantallas)
        self._orden_del_menu: tuple[str, ...] = tuple(ORDEN_DEL_MENU if orden_del_menu is None else orden_del_menu)
        self._al_fallar: Callable[[str, Exception], None] = al_fallar or self._avisar_en_ventana
        self._contexto: Contexto = Contexto(repo=repo, ruta_db=ruta_db, ir_a=self.mostrar)
        self._pantallas: dict[str, Pantalla] = {}
        self._clave_actual: str | None = None
        self._botones: dict[str, ttk.Button] = {}

        self._dibujar_marco(ruta_db)
        self.mostrar(PANTALLA_INICIAL if PANTALLA_INICIAL in self._clases else next(iter(self._clases)))

    # ---------- Marco de la ventana ----------

    def _dibujar_marco(self, ruta_db: Path) -> None:
        """Dibuja lo que no cambia entre pantallas: encabezado, menú, zona de la pantalla y barra de estado."""
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        encabezado = ttk.Frame(self, style="Encabezado.TFrame", padding=(14, 10))
        encabezado.grid(row=0, column=0, columnspan=2, sticky="ew")
        encabezado.columnconfigure(0, weight=1)
        self._equipo: ttk.Label = ttk.Label(encabezado, style="EncabezadoGrande.TLabel")
        self._equipo.grid(row=0, column=0, sticky="w")
        self._sesion: ttk.Label = ttk.Label(encabezado, style="Encabezado.TLabel")
        self._sesion.grid(row=0, column=1, sticky="e")

        menu = ttk.Frame(self, style="Menu.TFrame", width=ANCHO_DEL_MENU, padding=(6, 8))
        menu.grid(row=1, column=0, sticky="ns")
        menu.grid_propagate(flag=False)
        for clave in self._orden_del_menu:
            if clave not in self._clases:
                continue
            boton = ttk.Button(menu, text=self._clases[clave].TITULO, style="Menu.TButton", takefocus=False,
                               command=lambda c=clave: self.mostrar(c))
            boton.pack(fill="x", pady=1)
            self._botones[clave] = boton

        contenido = ttk.Frame(self, padding=(18, 12))
        contenido.grid(row=1, column=1, sticky="nsew")
        contenido.columnconfigure(0, weight=1)
        contenido.rowconfigure(2, weight=1)
        self._titulo: ttk.Label = ttk.Label(contenido, style="Titulo.TLabel")
        self._titulo.grid(row=0, column=0, sticky="w")
        self._subtitulo: ttk.Label = ttk.Label(contenido, style="Subtitulo.TLabel")
        self._subtitulo.grid(row=1, column=0, sticky="w", pady=(0, 8))
        self._zona: ttk.Frame = ttk.Frame(contenido)
        self._zona.grid(row=2, column=0, sticky="nsew")
        self._zona.columnconfigure(0, weight=1)
        self._zona.rowconfigure(0, weight=1)

        barra = ttk.Frame(self, style="Barra.TFrame", padding=(8, 3))
        barra.grid(row=2, column=0, columnspan=2, sticky="ew")
        barra.columnconfigure(1, weight=1)
        ttk.Label(barra, text=f"Base de datos: {ruta_db.name}", style="Barra.TLabel").grid(row=0, column=0, sticky="w")
        self._estado: ttk.Label = ttk.Label(barra, style="Barra.TLabel")
        self._estado.grid(row=0, column=1, sticky="e")

    def _actualizar_encabezado(self) -> None:
        """Escribe en la banda azul el nombre del equipo y cuándo empezó la última sesión, leyéndolos del repositorio."""
        equipos = self._contexto.repo.listar_equipos()
        self._equipo.configure(text=f"Equipo: {equipos[0][1]}" if equipos else "Equipo: sin registrar")
        ultima = self._contexto.repo.ultima_sesion()
        if ultima is None:
            self._sesion.configure(text="Todavía no hay sesiones")
        elif ultima.en_curso:
            self._sesion.configure(text=f"Sesión iniciada {fecha_hora_legible(ultima.inicio)}")
        else:
            self._sesion.configure(text=f"Última sesión iniciada {fecha_hora_legible(ultima.inicio)}")

    def _marcar_menu(self, clave_del_menu: str | None) -> None:
        """Resalta el botón del menú de la pantalla actual (o de su "padre", si la pantalla no tiene botón)."""
        for clave, boton in self._botones.items():
            boton.configure(style="MenuActivo.TButton" if clave == clave_del_menu else "Menu.TButton")

    # ---------- Navegación ----------

    @property
    def clave_actual(self) -> str | None:
        """La clave de la pantalla que se ve ahora (`"p01"` …), o None si todavía no se mostró ninguna."""
        return self._clave_actual

    @property
    def titulo_mostrado(self) -> str:
        """El título que se ve sobre la pantalla actual."""
        return _texto_de(self._titulo, "text")

    @property
    def encabezado(self) -> tuple[str, str]:
        """Los dos textos de la banda azul: (equipo, sesión), tal como se ven."""
        return _texto_de(self._equipo, "text"), _texto_de(self._sesion, "text")

    @property
    def estado(self) -> str:
        """El texto de la derecha de la barra de estado (ver `establecer_estado`)."""
        return _texto_de(self._estado, "text")

    @property
    def menu(self) -> list[tuple[str, str, bool]]:
        """Los botones del menú, de arriba hacia abajo, como (clave, texto, resaltado)."""
        return [
            (clave, _texto_de(boton, "text"), _texto_de(boton, "style") == "MenuActivo.TButton")
            for clave, boton in self._botones.items()
        ]

    def pantalla(self, clave: str) -> Pantalla | None:
        """La pantalla ya creada con esa clave, o None si todavía no se visitó. Sirve para las pruebas."""
        return self._pantallas.get(clave)

    def mostrar(self, clave: str, **parametros: object) -> None:
        """Muestra una pantalla: la crea si es la primera vez, la trae al frente y le pide que refresque sus datos.

        parametros: se los pasa a `al_mostrar` (por ejemplo, `id_periferico=5` para el detalle de un periférico).
        Lanza KeyError si la clave no existe. Si la pantalla falla, se avisa y la ventana queda como estaba.
        """
        if clave not in self._clases:
            raise KeyError(f"no existe la pantalla {clave!r}")
        clase = self._clases[clave]
        pantalla = self._pantallas.get(clave)
        if pantalla is None:
            try:
                pantalla = clase(self._zona, self._contexto)
            except Exception as error:  # una pantalla rota no debe tumbar la ventana
                self._al_fallar(clase.TITULO, error)
                return
            pantalla.grid(row=0, column=0, sticky="nsew")
            self._pantallas[clave] = pantalla
        pantalla.tkraise()  # pyright: ignore[reportUnknownMemberType]  (el stub de Tk de `tkraise` está sobrecargado)
        self._clave_actual = clave
        self._titulo.configure(text=clase.TITULO)
        self._subtitulo.configure(text=clase.SUBTITULO)
        self._marcar_menu(clase.MENU_PADRE or clave)
        self._actualizar_encabezado()
        try:
            pantalla.al_mostrar(**parametros)
        except Exception as error:  # igual: se avisa y se sigue
            self._al_fallar(clase.TITULO, error)

    def establecer_estado(self, texto: str) -> None:
        """Escribe un texto a la derecha de la barra de estado (por ejemplo, "Correo: sin conexión")."""
        self._estado.configure(text=texto)

    def _avisar_en_ventana(self, titulo: str, error: Exception) -> None:
        """Muestra el fallo de una pantalla en un cuadro de mensaje. Solo el tipo de error y su mensaje; nada de datos de teclas."""
        messagebox.showerror(f"No se pudo mostrar «{titulo}»", f"{type(error).__name__}: {error}", parent=self)
