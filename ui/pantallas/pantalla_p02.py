"""Pantalla P02 · Periféricos (RF23, RF17, RF18).

Qué muestra: la lista de teclados y mouse registrados en el equipo, incluidos los retirados, con su desgaste frente al límite
que garantiza el fabricante y su estado (normal, alerta pendiente o enviada, retirado). Arriba hay un filtro por tipo y una
casilla para ocultar los retirados; abajo, los botones "Confirmar etiqueta…" (abre el diálogo del issue #23) y "Ver detalle"
(abre P03). Doble clic o Enter sobre una fila también abre el detalle.

Cómo funciona: `al_mostrar` pide al repositorio los periféricos y las alertas, y las funciones puras de este archivo
(`texto_modelo`, `texto_vida_util`, `texto_estado`, `filas_de_perifericos`…) arman los textos de cada fila. Esas funciones no
usan Tk, así que se prueban sin abrir una ventana en `pruebas/test_pantalla_p02.py`.

El porcentaje sale de `UsoDeConteo.porcentaje`: el límite es POR ELEMENTO (por tecla, por botón), así que el porcentaje es el de
la tecla o botón más gastado, no el de la suma de todos (ver `docs/base-de-datos/README.md`).

Mockup: `docs/mockups/P02_Perifericos.png`. Guía: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py`, `ui/componentes.py` (`Tabla`), `ui/formato.py` y, por el contexto, el repositorio
(`listar_perifericos`, `listar_alertas`); abre `ui/pantallas/dialogo_etiqueta.py` · la registra `ui/registro.py`, la usa P03
(sus funciones de texto) y la prueba `pruebas/test_pantalla_p02.py`.
"""
import tkinter as tk
from collections.abc import Iterable, Sequence
from tkinter import ttk
from typing import ClassVar, override

from comun.repositorio import FilaAlerta, ResumenPeriferico, UsoDeConteo
from ui.componentes import ETIQUETA_ALERTA, ETIQUETA_RETIRADO, Columna, FilaDeTabla, Tabla
from ui.formato import fecha_legible, porcentaje
from ui.pantalla_base import Pantalla
from ui.pantallas.dialogo_etiqueta import DialogoEtiqueta

TODOS = "Todos"
# Lo que se ve en el filtro de tipo y el valor de `ResumenPeriferico.tipo` que le corresponde (None: sin filtro).
OPCIONES_DE_TIPO: dict[str, str | None] = {TODOS: None, "Teclado": "teclado", "Mouse": "mouse"}

POR_CONFIRMAR = "Por confirmar"
SIN_LIMITE = "Sin límite"  # un modelo sin límites cargados (por ejemplo, uno "desconocido"): no hay porcentaje que mostrar
MODELO_DESCONOCIDO = "desconocido"  # fabricante y modelo que pone el servicio cuando el VID/PID no está en la tabla de modelos

# Cómo se nombra cada tipo de conteo en la columna "Vida útil usada" cuando un periférico tiene más de uno (el mouse).
NOMBRE_CORTO_DEL_CONTEO: dict[str, str] = {"pulsacion_tecla": "teclas", "clic_boton": "clics", "scroll_paso": "scroll"}
ORDEN_DEL_CONTEO: tuple[str, ...] = ("pulsacion_tecla", "clic_boton", "scroll_paso")

NOTA_RETIRADOS = "Los periféricos retirados se conservan para el historial de reportes y alertas."
SIN_PERIFERICOS = (
    "No hay periféricos que mostrar. Un teclado o mouse aparece aquí cuando el servicio recibe su primer evento."
)


# ---------- Funciones puras: arman los textos sin usar Tk ----------


def texto_tipo(tipo: str) -> str:
    """El tipo con mayúscula inicial: `teclado` → `Teclado`."""
    return tipo.capitalize()


def texto_modelo(periferico: ResumenPeriferico) -> str:
    """Fabricante y modelo (`Logitech K120`). Si el VID/PID no está en la tabla de modelos, `Modelo desconocido`."""
    if periferico.modelo == MODELO_DESCONOCIDO:
        return "Modelo desconocido"
    if periferico.fabricante in ("", MODELO_DESCONOCIDO):
        return periferico.modelo
    return f"{periferico.fabricante} {periferico.modelo}"


def texto_etiqueta(periferico: ResumenPeriferico) -> str:
    """La etiqueta de inventario (`TEC-0042`) o `Por confirmar` si Soporte TI todavía no la confirmó (RF18)."""
    return periferico.etiqueta or POR_CONFIRMAR


def texto_vid_pid(periferico: ResumenPeriferico) -> str:
    """El VID y el PID como los muestra Windows: `046D:C31C`."""
    return f"{periferico.vid}:{periferico.pid}".upper()


def _ordenados(usos: Iterable[UsoDeConteo]) -> list[UsoDeConteo]:
    """Los usos en un orden fijo (teclas, clics, scroll), para que la columna no cambie de orden entre refrescos."""
    def posicion(uso: UsoDeConteo) -> int:
        """La posición del tipo de conteo en ORDEN_DEL_CONTEO; los tipos que no conoce van al final."""
        return ORDEN_DEL_CONTEO.index(uso.tipo_conteo) if uso.tipo_conteo in ORDEN_DEL_CONTEO else len(ORDEN_DEL_CONTEO)

    return sorted(usos, key=posicion)


def texto_vida_util(periferico: ResumenPeriferico) -> str:
    """El porcentaje de vida útil usada, como en el mockup.

    - Un solo tipo de conteo con límite (el teclado): `91 %`.
    - Varios (el mouse): `38 % clics · 12 % scroll`.
    - Ningún límite (modelo desconocido): `Sin límite`, sin fallar.
    Solo cuentan los tipos con límite: sin límite no hay porcentaje.
    """
    con_limite = [uso for uso in _ordenados(periferico.usos) if uso.porcentaje is not None]
    if not con_limite:
        return SIN_LIMITE
    if len(con_limite) == 1:
        return porcentaje(con_limite[0].porcentaje)
    partes = [f"{porcentaje(uso.porcentaje)} {NOMBRE_CORTO_DEL_CONTEO.get(uso.tipo_conteo, uso.tipo_conteo)}" for uso in con_limite]
    return " · ".join(partes)


def alerta_principal(alertas: Iterable[FilaAlerta], id_periferico: int) -> FilaAlerta | None:
    """La alerta que manda en el estado del periférico: la pendiente de mayor umbral; si no hay pendientes, la enviada de mayor umbral.

    Las pendientes van primero porque son las que Soporte TI tiene que mirar (el correo todavía no salió, RF20).
    """
    propias = [alerta for alerta in alertas if alerta.id_periferico == id_periferico]
    if not propias:
        return None
    return max(propias, key=lambda alerta: (alerta.estado == "pendiente", alerta.umbral))


def texto_estado(periferico: ResumenPeriferico, alerta: FilaAlerta | None) -> str:
    """El estado del periférico: `Retirado el 15/09/2026`, `Alerta 90 % pendiente`, `Alerta 100 % enviada` o `Normal`.

    Un retirado muestra solo la fecha de retiro: sus alertas ya no se atienden (se cambió el periférico).
    """
    if not periferico.activo:
        return f"Retirado el {fecha_legible(periferico.fecha_retiro)}" if periferico.fecha_retiro else "Retirado"
    if alerta is not None:
        return f"Alerta {alerta.umbral} % {'pendiente' if alerta.estado == 'pendiente' else 'enviada'}"
    return "Normal"


def etiqueta_de_color(periferico: ResumenPeriferico, alerta: FilaAlerta | None) -> str | None:
    """El color de la fila: gris si está retirado, rojo si tiene una alerta pendiente, sin color en otro caso."""
    if not periferico.activo:
        return ETIQUETA_RETIRADO
    if alerta is not None and alerta.estado == "pendiente":
        return ETIQUETA_ALERTA
    return None


def filtrar_por_tipo(perifericos: Iterable[ResumenPeriferico], opcion: str) -> list[ResumenPeriferico]:
    """Los periféricos del tipo elegido en el filtro (`Todos`, `Teclado` o `Mouse`). Una opción desconocida no filtra."""
    tipo = OPCIONES_DE_TIPO.get(opcion)
    return [p for p in perifericos if tipo is None or p.tipo == tipo]


def filas_de_perifericos(perifericos: Iterable[ResumenPeriferico], alertas: Sequence[FilaAlerta]) -> list[FilaDeTabla]:
    """Una fila de la tabla por periférico, con el id del periférico como identificador de la fila."""
    filas: list[FilaDeTabla] = []
    for periferico in perifericos:
        alerta = alerta_principal(alertas, periferico.id)
        valores = (
            texto_tipo(periferico.tipo),
            texto_modelo(periferico),
            texto_etiqueta(periferico),
            texto_vid_pid(periferico),
            texto_vida_util(periferico),
            texto_estado(periferico, alerta),
        )
        filas.append(FilaDeTabla(valores, id=str(periferico.id), etiqueta=etiqueta_de_color(periferico, alerta)))
    return filas


def se_puede_confirmar(periferico: ResumenPeriferico | None) -> bool:
    """True si tiene sentido confirmar la etiqueta: un periférico activo que sigue "por confirmar" (RF18)."""
    return periferico is not None and periferico.activo and periferico.estado_asignacion == "por_confirmar"


# ---------- La pantalla ----------


class PantallaP02(Pantalla):
    """Periféricos: lista de periféricos con su desgaste frente al límite, incluidos los retirados, y confirmación de etiqueta."""

    TITULO: ClassVar[str] = "Periféricos"
    SUBTITULO: ClassVar[str] = "Teclados y mouse registrados en este equipo, con su desgaste frente al límite del fabricante."

    @override
    def construir(self) -> None:
        """Dibuja el filtro, la tabla, la nota y los botones. Se llama una sola vez."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._perifericos: dict[str, ResumenPeriferico] = {}  # id de fila → periférico, para los botones

        filtros = ttk.Frame(self)
        filtros.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        filtros.columnconfigure(3, weight=1)
        ttk.Label(filtros, text="Tipo:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.tipo: tk.StringVar = tk.StringVar(self, value=TODOS)
        combo = ttk.Combobox(filtros, textvariable=self.tipo, values=list(OPCIONES_DE_TIPO), state="readonly", width=12)
        combo.grid(row=0, column=1, sticky="w")
        combo.bind("<<ComboboxSelected>>", lambda _evento: self.refrescar())
        self.ver_retirados: tk.BooleanVar = tk.BooleanVar(self, value=True)
        ttk.Checkbutton(filtros, text="Mostrar periféricos retirados", variable=self.ver_retirados,
                        command=self.refrescar).grid(row=0, column=2, sticky="w", padx=(20, 0))
        ttk.Button(filtros, text="Actualizar", command=self.refrescar).grid(row=0, column=4, sticky="e")

        columnas = [
            Columna("tipo", "Tipo", 80),
            Columna("modelo", "Modelo", 140),
            Columna("etiqueta", "Etiqueta", 110),
            Columna("vid_pid", "VID:PID", 95),
            Columna("vida_util", "Vida útil usada", 170),
            Columna("estado", "Estado", 180),
        ]
        self.tabla: Tabla = Tabla(self, columnas, alto=10, al_elegir=lambda _id: self._actualizar_botones())
        self.tabla.grid(row=1, column=0, sticky="nsew")
        # Doble clic o Enter sobre una fila abren el detalle; un solo clic solo la elige (para poder usar "Confirmar etiqueta…").
        self.tabla.arbol.bind("<Double-1>", lambda _evento: self.ver_detalle())
        self.tabla.arbol.bind("<Return>", lambda _evento: self.ver_detalle())

        self.nota: ttk.Label = ttk.Label(self, text=NOTA_RETIRADOS, style="Suave.TLabel")
        self.nota.grid(row=2, column=0, sticky="w", pady=(8, 0))

        botones = ttk.Frame(self)
        botones.grid(row=3, column=0, sticky="e", pady=(12, 0))
        self.boton_confirmar: ttk.Button = ttk.Button(botones, text="Confirmar etiqueta…", command=self.confirmar_etiqueta)
        self.boton_confirmar.pack(side="left", padx=(0, 8))
        self.boton_detalle: ttk.Button = ttk.Button(botones, text="Ver detalle", command=self.ver_detalle)
        self.boton_detalle.pack(side="left")

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Pide los datos y refresca la tabla cada vez que se muestra la pantalla. No usa parámetros."""
        _ = parametros
        self.refrescar()

    def refrescar(self, elegir: str | None = None) -> None:
        """Vuelve a pedir los periféricos y las alertas y llena la tabla con el filtro actual.

        elegir: id de la fila que queda elegida (por ejemplo, la que se acaba de confirmar); por defecto, la que estaba elegida.
        """
        elegida = elegir or self.tabla.elegida()
        perifericos = filtrar_por_tipo(self.repo.listar_perifericos(incluir_retirados=self.ver_retirados.get()), self.tipo.get())
        self._perifericos = {str(p.id): p for p in perifericos}
        self.tabla.llenar(filas_de_perifericos(perifericos, self.repo.listar_alertas()))
        self.nota.configure(text=NOTA_RETIRADOS if perifericos else SIN_PERIFERICOS)
        if elegida in self._perifericos:
            self.tabla.arbol.selection_set(elegida)
            self.tabla.arbol.see(elegida)
        self._actualizar_botones()

    def elegido(self) -> ResumenPeriferico | None:
        """El periférico de la fila elegida, o None si no hay ninguna."""
        id_fila = self.tabla.elegida()
        return self._perifericos.get(id_fila) if id_fila is not None else None

    def _actualizar_botones(self) -> None:
        """Activa "Ver detalle" si hay una fila elegida y "Confirmar etiqueta…" si además está por confirmar."""
        periferico = self.elegido()
        self.boton_detalle.state(["!disabled"] if periferico is not None else ["disabled"])
        self.boton_confirmar.state(["!disabled"] if se_puede_confirmar(periferico) else ["disabled"])

    def ver_detalle(self) -> None:
        """Abre P03 con el periférico elegido. Sin fila elegida, no hace nada."""
        periferico = self.elegido()
        if periferico is not None:
            self.contexto.ir_a("p03", id_periferico=periferico.id)

    def confirmar_etiqueta(self) -> None:
        """Abre el diálogo de etiqueta (RF18) y, si se confirmó, refresca la lista dejando elegida la misma fila."""
        periferico = self.elegido()
        if not se_puede_confirmar(periferico) or periferico is None:
            return
        dialogo = DialogoEtiqueta(self, self.repo, periferico)
        if dialogo.esperar():
            self.refrescar(elegir=str(periferico.id))
