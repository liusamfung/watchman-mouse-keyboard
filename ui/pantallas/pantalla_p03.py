"""Pantalla P03 · Detalle del periférico (RF23, RF16, RF17, RF18).

Qué muestra: a la izquierda, los datos de un periférico (etiqueta, modelo, VID:PID, equipo, asignación, límite del fabricante,
total acumulado y el estado de sus alertas del 90 % y del 100 %); a la derecha, sus teclas (o botones y rueda, en un mouse) con
mayor desgaste, cada una con su total y su porcentaje frente al límite. Abajo, "Volver a la lista" y "Confirmar asignación"
(abre el mismo diálogo de etiqueta que P02, para un periférico que sigue por confirmar).

Cómo se llega: desde P02 con `contexto.ir_a("p03", id_periferico=5)`. No tiene botón propio en el menú (resalta P02). Si llega
sin `id_periferico` o con uno que ya no existe, muestra un aviso en vez de fallar.

Privacidad (RNF4): las teclas se muestran SOLO como totales por tecla, ordenadas por desgaste (nunca por el orden en que se
pulsaron), y sus nombres no se imprimen ni se escriben en ningún log. El repositorio ya los entrega así (`totales_por_elemento`).

Cómo funciona: las funciones puras de este archivo (`texto_limite`, `texto_total`, `texto_alerta`, `filas_de_desgaste`…) arman
los textos sin usar Tk y se prueban en `pruebas/test_pantalla_p03.py`. El porcentaje de cada tecla es su total dividido entre el
límite POR ELEMENTO de su modelo (20 000 pulsaciones por tecla, 10 000 clics por botón, 15 000 pasos de la rueda).

Mockup: `docs/mockups/P03_DetallePeriferico.png`. Guía: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py`, `ui/componentes.py` (`Tabla`), `ui/formato.py`, las funciones de texto de
`ui/pantallas/pantalla_p02.py`, `ui/pantallas/desgaste.py`, el diálogo de `ui/pantallas/dialogo_etiqueta.py` y, por el contexto, el repositorio
(`obtener_periferico`, `totales_por_elemento`, `listar_alertas`, `listar_equipos`) · la registra `ui/registro.py`, la abre P02 y la
prueba `pruebas/test_pantalla_p03.py`.
"""
from collections.abc import Iterable, Mapping
from tkinter import ttk
from typing import ClassVar, override

from comun.repositorio import FilaAlerta, ResumenPeriferico
from ui.componentes import ETIQUETA_ALERTA, Columna, FilaDeTabla, Tabla
from ui.formato import SIN_DATO, fecha_legible, porcentaje
from ui.pantalla_base import Pantalla
from ui.pantallas.desgaste import Desgaste
from ui.pantallas.dialogo_etiqueta import DialogoEtiqueta
from ui.pantallas.pantalla_p02 import POR_CONFIRMAR, se_puede_confirmar, texto_etiqueta, texto_modelo, texto_tipo, texto_vid_pid

CUANTOS_ELEMENTOS = 10  # cuántas teclas (o botones) se listan: las más gastadas; el resto no cambia ninguna decisión
UMBRAL_RESALTADO = 90.0  # desde este porcentaje la fila se pinta de rojo: es el umbral de la primera alerta (RF19)

# Cómo se escribe cada tipo de conteo: (en el límite, por elemento) y (en el total acumulado).
UNIDADES: dict[str, tuple[str, str]] = {
    "pulsacion_tecla": ("pulsaciones por tecla", "pulsaciones"),
    "clic_boton": ("clics por botón", "clics"),
    "scroll_paso": ("pasos de la rueda", "pasos de la rueda"),
}
ORDEN_DEL_CONTEO: tuple[str, ...] = ("pulsacion_tecla", "clic_boton", "scroll_paso")
NOMBRES_DEL_MOUSE: dict[str, str] = {"izquierdo": "Botón izquierdo", "derecho": "Botón derecho", "rueda": "Rueda"}

ASIGNACIONES: dict[str, str] = {"confirmada": "Confirmada", "por_confirmar": POR_CONFIRMAR}
SIN_PERIFERICO = "Elige un periférico en la lista de Periféricos para ver su detalle."
NOTA_PRIVACIDAD = "Solo se guardan contadores acumulados por tecla: no el orden ni el texto digitado (RNF4)."
TEXTO_PENDIENTE = "pendiente de envío"
SIN_DESGASTE = "Todavía no hay pulsaciones ni clics registrados para este periférico."

# Los datos de la izquierda, en orden: (clave interna, título que se ve).
CAMPOS: tuple[tuple[str, str], ...] = (
    ("etiqueta", "Etiqueta:"),
    ("modelo", "Modelo:"),
    ("vid_pid", "VID:PID:"),
    ("equipo", "Equipo:"),
    ("asignacion", "Asignación:"),
    ("estado", "Estado:"),
    ("limite", "Límite del fabricante:"),
    ("total", "Total acumulado:"),
    ("alerta_90", "Alerta 90 %:"),
    ("alerta_100", "Alerta 100 %:"),
)


# ---------- Funciones puras: arman los textos sin usar Tk ----------


def miles(numero: int) -> str:
    """Un entero con espacio como separador de miles, como en los mockups: `412380` → `412 380`."""
    return f"{numero:,}".replace(",", " ")


def _posicion(tipo_conteo: str) -> int:
    """La posición del tipo de conteo en ORDEN_DEL_CONTEO (teclas, clics, scroll); los que no conoce van al final."""
    return ORDEN_DEL_CONTEO.index(tipo_conteo) if tipo_conteo in ORDEN_DEL_CONTEO else len(ORDEN_DEL_CONTEO)


def texto_limite(periferico: ResumenPeriferico) -> str:
    """El límite del fabricante, uno por línea: `20 000 pulsaciones por tecla` o, en un mouse, clics y rueda.

    Un modelo sin límites cargados (por ejemplo, uno "desconocido") dice `Sin límite configurado` y no falla.
    """
    lineas = [
        f"{miles(uso.limite)} {UNIDADES.get(uso.tipo_conteo, (uso.tipo_conteo, ''))[0]}"
        for uso in sorted(periferico.usos, key=lambda uso: _posicion(uso.tipo_conteo))
        if uso.limite is not None
    ]
    return "\n".join(lineas) if lineas else "Sin límite configurado"


def texto_total(periferico: ResumenPeriferico) -> str:
    """El total acumulado de todos los elementos, uno por tipo de conteo y por línea: `412 380 pulsaciones`."""
    lineas = [
        f"{miles(uso.total)} {UNIDADES.get(uso.tipo_conteo, ('', uso.tipo_conteo))[1]}"
        for uso in sorted(periferico.usos, key=lambda uso: _posicion(uso.tipo_conteo))
    ]
    return "\n".join(lineas) if lineas else "Sin uso registrado"


def texto_asignacion(periferico: ResumenPeriferico) -> str:
    """`Confirmada` o `Por confirmar` (RF18)."""
    return ASIGNACIONES.get(periferico.estado_asignacion, periferico.estado_asignacion)


def texto_estado_del_periferico(periferico: ResumenPeriferico) -> str:
    """`Activo` o `Retirado el 04/11/2026`."""
    if periferico.activo:
        return "Activo"
    return f"Retirado el {fecha_legible(periferico.fecha_retiro)}" if periferico.fecha_retiro else "Retirado"


def alerta_de(alertas: Iterable[FilaAlerta], id_periferico: int, umbral: int) -> FilaAlerta | None:
    """La alerta de ese periférico y umbral, o None si no se generó. Hay una sola por periférico y umbral (índice único)."""
    return next((a for a in alertas if a.id_periferico == id_periferico and a.umbral == umbral), None)


def texto_alerta(alerta: FilaAlerta | None) -> str:
    """El estado de una alerta: `no generada`, `pendiente de envío` o `enviada el 05/11/2026`."""
    if alerta is None:
        return "no generada"
    if alerta.estado == "pendiente":
        return TEXTO_PENDIENTE
    return f"enviada el {fecha_legible(alerta.fecha_envio)}" if alerta.fecha_envio else "enviada"


def nombre_del_elemento(tipo_conteo: str, elemento: str) -> str:
    """Cómo se muestra una tecla, un botón o la rueda.

    Las teclas llegan en mayúsculas desde el capturador (`E`, `ESPACIO`, `F5`, ver el contrato JSON): una palabra se muestra con
    mayúscula inicial (`Espacio`) y lo demás tal cual. Los botones del mouse se nombran completos (`Botón izquierdo`).
    """
    if tipo_conteo in ("clic_boton", "scroll_paso"):
        return NOMBRES_DEL_MOUSE.get(elemento, elemento.capitalize())
    return elemento.capitalize() if len(elemento) > 1 and elemento.isalpha() else elemento


def desgaste_por_elemento(
    periferico: ResumenPeriferico, totales: Mapping[str, Mapping[str, int]], cuantos: int = CUANTOS_ELEMENTOS
) -> list[Desgaste]:
    """Los `cuantos` elementos más gastados, del que más al que menos.

    totales: por tipo de conteo, el total de cada elemento (lo que da `Repositorio.totales_por_elemento`).
    Se ordena por porcentaje y, a igual porcentaje o sin límite, por cantidad. Un tipo sin límite tiene porcentaje None y va
    después de los que sí lo tienen: así lo primero que se ve es lo que está más cerca de agotarse.
    """
    limites = {uso.tipo_conteo: uso.limite for uso in periferico.usos}
    lista: list[Desgaste] = []
    for tipo_conteo, por_elemento in totales.items():
        limite = limites.get(tipo_conteo)
        for elemento, cantidad in por_elemento.items():
            lista.append(Desgaste(tipo_conteo, elemento, cantidad, cantidad * 100 / limite if limite else None))
    lista.sort(key=lambda d: (d.porcentaje is not None, d.porcentaje or 0.0, d.cantidad), reverse=True)
    return lista[:cuantos]


def filas_de_desgaste(desgastes: Iterable[Desgaste]) -> list[FilaDeTabla]:
    """Las filas de la tabla de la derecha. Una fila desde el 90 % del límite va en rojo (es el umbral de la primera alerta).

    Las filas no llevan identificador: el nombre de una tecla no se usa como id para que no termine en ningún otro lado (RNF4).
    """
    return [
        FilaDeTabla(
            (nombre_del_elemento(d.tipo_conteo, d.elemento), miles(d.cantidad), porcentaje(d.porcentaje)),
            etiqueta=ETIQUETA_ALERTA if d.porcentaje is not None and d.porcentaje >= UMBRAL_RESALTADO else None,
        )
        for d in desgastes
    ]


def titulo_del_elemento(tipo: str) -> str:
    """El título de la primera columna y del recuadro: teclas en un teclado, botones (y rueda) en un mouse."""
    return "Tecla" if tipo == "teclado" else "Botón o rueda"


def resumen(periferico: ResumenPeriferico) -> str:
    """La línea bajo el título, como en el mockup: `Teclado · TEC-0042 · Logitech K120`."""
    return f"{texto_tipo(periferico.tipo)} · {texto_etiqueta(periferico)} · {texto_modelo(periferico)}"


def datos_del_periferico(
    periferico: ResumenPeriferico, alertas: Iterable[FilaAlerta], nombre_equipo: str | None
) -> dict[str, str]:
    """Los textos de la columna izquierda, por clave de CAMPOS."""
    propias = list(alertas)
    return {
        "etiqueta": texto_etiqueta(periferico),
        "modelo": texto_modelo(periferico),
        "vid_pid": texto_vid_pid(periferico),
        "equipo": nombre_equipo or SIN_DATO,
        "asignacion": texto_asignacion(periferico),
        "estado": texto_estado_del_periferico(periferico),
        "limite": texto_limite(periferico),
        "total": texto_total(periferico),
        "alerta_90": texto_alerta(alerta_de(propias, periferico.id, 90)),
        "alerta_100": texto_alerta(alerta_de(propias, periferico.id, 100)),
    }


def id_de_parametro(valor: object) -> int | None:
    """El `id_periferico` que llegó por `ir_a`, como entero; None si no llegó o no es un número."""
    if isinstance(valor, bool):  # bool es subclase de int: True no es un id válido
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, str) and valor.isdigit():
        return int(valor)
    return None


# ---------- La pantalla ----------


class PantallaP03(Pantalla):
    """Detalle del periférico: datos de un periférico y sus teclas con mayor desgaste. Se llega desde P02 con `ir_a("p03", id_periferico=...)`."""

    TITULO: ClassVar[str] = "Detalle del periférico"
    SUBTITULO: ClassVar[str] = "Datos del periférico y sus teclas con mayor desgaste."
    MENU_PADRE: ClassVar[str | None] = "p02"  # no tiene botón en el menú: se resalta P02

    @override
    def construir(self) -> None:
        """Dibuja la línea de resumen, los dos recuadros y los botones. Se llama una sola vez."""
        self._periferico: ResumenPeriferico | None = None
        self.columnconfigure(0, weight=1, uniform="mitades")
        self.columnconfigure(1, weight=1, uniform="mitades")
        self.rowconfigure(1, weight=1)

        self.linea: ttk.Label = ttk.Label(self, style="Suave.TLabel")
        self.linea.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        datos = ttk.LabelFrame(self, text="Datos del periférico", padding=(14, 10))
        datos.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        datos.columnconfigure(1, weight=1)
        self.valores: dict[str, ttk.Label] = {}
        for fila, (clave, titulo) in enumerate(CAMPOS):
            ttk.Label(datos, text=titulo, style="Suave.TLabel").grid(row=fila, column=0, sticky="nw", pady=3, padx=(0, 12))
            valor = ttk.Label(datos, justify="left")
            valor.grid(row=fila, column=1, sticky="nw", pady=3)
            self.valores[clave] = valor

        self.recuadro_desgaste: ttk.LabelFrame = ttk.LabelFrame(self, text="Teclas con mayor desgaste", padding=(10, 10))
        self.recuadro_desgaste.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        self.recuadro_desgaste.columnconfigure(0, weight=1)
        self.recuadro_desgaste.rowconfigure(0, weight=1)
        self.columnas: list[Columna] = [
            Columna("elemento", "Tecla", 130),
            Columna("cantidad", "Pulsaciones", 100, "e"),
            Columna("porcentaje", "% del límite", 100, "e"),
        ]
        self.tabla: Tabla = Tabla(self.recuadro_desgaste, self.columnas, alto=CUANTOS_ELEMENTOS)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        self.nota: ttk.Label = ttk.Label(self.recuadro_desgaste, text=NOTA_PRIVACIDAD, style="Suave.TLabel", wraplength=360)
        self.nota.grid(row=1, column=0, sticky="w", pady=(8, 0))

        botones = ttk.Frame(self)
        botones.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Button(botones, text="Volver a la lista", command=lambda: self.contexto.ir_a("p02")).pack(side="left")
        self.boton_confirmar: ttk.Button = ttk.Button(botones, text="Confirmar asignación", command=self.confirmar_asignacion)
        self.boton_confirmar.pack(side="right")

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Muestra el periférico de `id_periferico`. Si no llegó (o no existe), muestra el aviso y conserva el último mostrado si había uno."""
        id_periferico = id_de_parametro(parametros.get("id_periferico"))
        if id_periferico is None and self._periferico is not None:
            id_periferico = self._periferico.id  # se volvió a la pantalla sin parámetros: se refresca el mismo periférico
        self.cargar(id_periferico)

    def cargar(self, id_periferico: int | None) -> None:
        """Pide los datos del periférico y llena los dos recuadros. Sin periférico, deja todo vacío con un aviso."""
        periferico = self.repo.obtener_periferico(id_periferico) if id_periferico is not None else None
        self._periferico = periferico
        if periferico is None:
            self.linea.configure(text=SIN_PERIFERICO)
            for valor in self.valores.values():
                valor.configure(text=SIN_DATO, style="TLabel")
            self.tabla.limpiar()
            self.boton_confirmar.state(["disabled"])
            return

        equipos = dict(self.repo.listar_equipos())
        alertas = [a for a in self.repo.listar_alertas() if a.id_periferico == periferico.id]
        self.linea.configure(text=resumen(periferico))
        for clave, texto in datos_del_periferico(periferico, alertas, equipos.get(periferico.id_equipo)).items():
            # Una alerta pendiente se resalta en rojo: es lo que Soporte TI tiene que revisar (el correo no salió, RF20).
            estilo = "Peligro.TLabel" if clave.startswith("alerta_") and texto == TEXTO_PENDIENTE else "TLabel"
            self.valores[clave].configure(text=texto, style=estilo)

        # Teclas en un teclado; botones y rueda en un mouse. Los nombres de teclas solo pasan de la base a la tabla (RNF4).
        es_teclado = periferico.tipo == "teclado"
        self.recuadro_desgaste.configure(text="Teclas con mayor desgaste" if es_teclado else "Botones con mayor desgaste")
        self.tabla.arbol.heading("elemento", text=titulo_del_elemento(periferico.tipo))
        self.tabla.arbol.heading("cantidad", text="Pulsaciones" if es_teclado else "Cantidad")
        totales = {uso.tipo_conteo: self.repo.totales_por_elemento(periferico.id, uso.tipo_conteo) for uso in periferico.usos}
        desgastes = desgaste_por_elemento(periferico, totales)
        self.tabla.llenar(filas_de_desgaste(desgastes))
        self.nota.configure(text=NOTA_PRIVACIDAD if desgastes else f"{SIN_DESGASTE} {NOTA_PRIVACIDAD}")
        self.boton_confirmar.state(["!disabled"] if se_puede_confirmar(periferico) else ["disabled"])

    def confirmar_asignacion(self) -> None:
        """Abre el diálogo de etiqueta (RF18) y, si se confirmó, vuelve a cargar el periférico."""
        periferico = self._periferico
        if periferico is None or not se_puede_confirmar(periferico):
            return
        if DialogoEtiqueta(self, self.repo, periferico).esperar():
            self.cargar(periferico.id)
