"""Pantalla P07: consulta y muestra alertas de desgaste e incidentes (RF9, RF10, RF19, RF20, RF23).

Construye dos tablas de solo lectura y las actualiza cada vez que se visita
la pantalla. No modifica alertas, incidentes ni datos de periféricos.

Se relaciona con: usa comun/repositorio.py, ui/componentes.py,
ui/formato.py y ui/pantalla_base.py · la usa ui/registro.py.
"""

from tkinter import ttk
from typing import ClassVar, override

from comun.repositorio import FilaAlerta, FilaIncidente
from ui.componentes import Columna, ETIQUETA_ALERTA, FilaDeTabla, Tabla
from ui.formato import SIN_DATO, fecha_legible, hora_legible
from ui.pantalla_base import Pantalla


def mostrar_fecha_hora(valor: str | None) -> str:
    """Convierte una fecha ISO en una fecha y hora legibles."""
    if not valor:
        return SIN_DATO
    return f"{fecha_legible(valor)} {hora_legible(valor)}"


def fila_de_alerta(alerta: FilaAlerta) -> FilaDeTabla:
    """Prepara una alerta para la tabla sin alterar sus datos."""
    fecha_destino = (
        alerta.fecha_envio
        if alerta.estado == "enviada"
        else alerta.proximo_reintento
    )
    periferico = alerta.etiqueta or "Sin etiqueta"

    return FilaDeTabla(
        valores=(
            mostrar_fecha_hora(alerta.fecha_creacion),
            f"{alerta.umbral} %",
            f"{periferico} · {alerta.modelo}",
            alerta.estado.capitalize(),
            str(alerta.intentos),
            mostrar_fecha_hora(fecha_destino),
            alerta.ultimo_error or SIN_DATO,
        ),
        id=f"alerta-{alerta.id}",
        etiqueta=ETIQUETA_ALERTA if alerta.estado == "pendiente" else None,
    )


def nombre_de_incidente(tipo: str) -> str:
    """Convierte el tipo técnico en un nombre legible para Soporte TI."""
    nombres = {
        "error_envio": "Error de envío",
        "caida_proceso": "Caída del proceso C++",
        "evento_invalido": "Evento inválido",
        "error_comunicacion": "Error de comunicación",
        "apagado_inesperado": "Apagado inesperado",
    }
    return nombres.get(tipo, tipo.replace("_", " ").capitalize())



def fila_de_incidente(incidente: FilaIncidente) -> FilaDeTabla:
    """Prepara un incidente reciente para mostrarlo en pantalla."""
    return FilaDeTabla(
        valores=(
            mostrar_fecha_hora(incidente.fecha_hora),
            nombre_de_incidente(incidente.tipo),
            incidente.detalle or SIN_DATO,
            incidente.accion or SIN_DATO,
        ),
        id=f"incidente-{incidente.id}",
    )


def agregar_barra_horizontal(tabla: Tabla) -> None:
    """Permite consultar todas las columnas en ventanas pequeñas."""
    barra = ttk.Scrollbar(
        tabla,
        orient="horizontal",
        command=tabla.arbol.xview,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    )
    tabla.arbol.configure(xscrollcommand=barra.set)
    barra.grid(row=1, column=0, sticky="ew")


class PantallaP07(Pantalla):
    """Muestra las alertas y los incidentes registrados en SQLite."""

    TITULO: ClassVar[str] = "Alertas e incidentes"
    SUBTITULO: ClassVar[str] = (
        "Alertas de desgaste enviadas o pendientes, e incidentes recientes."
    )

    @override
    def construir(self) -> None:
        """Construye las dos secciones de la pantalla una sola vez."""
        bloque_alertas = ttk.LabelFrame(
            self, text="Alertas de desgaste", padding=8
        )
        bloque_alertas.pack(fill="both", expand=True, pady=(0, 10))

        columnas_alertas = [
            Columna("creada", "Creada", 145),
            Columna("umbral", "Umbral", 65, "center"),
            Columna("periferico", "Periférico", 170),
            Columna("estado", "Estado", 95),
            Columna("intentos", "Intentos", 75, "center"),
            Columna("envio", "Envío / próximo reintento", 190),
            Columna("error", "Último error", 360),
        ]
        self.tabla_alertas: Tabla = Tabla(
            bloque_alertas, columnas_alertas, alto=5
        )
        self.tabla_alertas.pack(fill="both", expand=True)
        agregar_barra_horizontal(self.tabla_alertas)

        self.aviso_alertas: ttk.Label = ttk.Label(
            bloque_alertas, style="Suave.TLabel"
        )
        self.aviso_alertas.pack(anchor="w", pady=(4, 0))

        self.info_correo: ttk.Label = ttk.Label(
            bloque_alertas, style="Suave.TLabel"
        )
        self.info_correo.pack(anchor="w", pady=(4, 0))

        bloque_incidentes = ttk.LabelFrame(
            self, text="Incidentes recientes", padding=8
        )
        bloque_incidentes.pack(fill="both", expand=True)

        columnas_incidentes = [
            Columna("fecha", "Fecha y hora", 155),
            Columna("tipo", "Tipo", 170),
            Columna("detalle", "Detalle", 300),
            Columna("accion", "Acción", 220),
        ]
        self.tabla_incidentes: Tabla = Tabla(
            bloque_incidentes, columnas_incidentes, alto=6
        )
        self.tabla_incidentes.pack(fill="both", expand=True)
        agregar_barra_horizontal(self.tabla_incidentes)

        self.aviso_incidentes: ttk.Label = ttk.Label(
            bloque_incidentes, style="Suave.TLabel"
        )
        self.aviso_incidentes.pack(anchor="w", pady=(4, 0))

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Consulta SQLite y actualiza ambas tablas al entrar a P07."""
        _ = parametros

        alertas = self.repo.listar_alertas()
        self.tabla_alertas.llenar(
            fila_de_alerta(alerta) for alerta in alertas
        )
        self.aviso_alertas.configure(
            text="" if alertas else "No hay alertas registradas."
        )

        destinatarios = self.repo.leer_configuracion("destinatarios")
        self.info_correo.configure(
            text=(
                f"Destinatarios: {destinatarios or 'Sin configurar'}"
                "  ·  Reintentos: 1, 5 y luego cada 15 minutos."
            )
        )

        incidentes = self.repo.incidentes_recientes()
        self.tabla_incidentes.llenar(
            fila_de_incidente(incidente) for incidente in incidentes
        )
        self.aviso_incidentes.configure(
            text="" if incidentes else "No hay incidentes registrados."
        )
