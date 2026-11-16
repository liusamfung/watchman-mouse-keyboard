
"""Pantalla P06: vista previa y exportación de reportes CSV (RF14, RF23).

Consulta filas del repositorio, permite filtrar por fechas y elegir
la carpeta de destino. No genera archivos si no existen registros.

Se relaciona con: usa comun/repositorio.py, reportes/generador.py,
ui/componentes.py y ui/pantalla_base.py · la usa ui/registro.py.
"""

import tkinter as tk
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import ClassVar, override

from comun.repositorio import Fila, Repositorio
from reportes.generador import (
    reporte_alertas,
    reporte_contadores,
    reporte_eventos,
    reporte_totales_diarios,
)
from ui.componentes import Columna, FilaDeTabla, Tabla
from ui.pantalla_base import Pantalla


# Tipos de reportes disponibles y sus nombres visibles.
OPCIONES: tuple[tuple[str, str], ...] = (
    ("eventos", "Eventos"),
    ("totales", "Totales diarios"),
    ("contadores", "Contadores por periférico"),
    ("alertas", "Alertas"),
)


# Cada reporte utiliza las columnas que realmente exporta.
COLUMNAS: dict[str, tuple[Columna, ...]] = {
    "eventos": (
        Columna("id", "ID", 70),
        Columna("sesion", "Sesión", 80),
        Columna("periferico", "Periférico", 135),
        Columna("tipo", "Tipo de evento", 160),
        Columna("fecha", "Fecha y hora", 185),
        Columna("x", "X", 65),
        Columna("y", "Y", 65),
    ),
    "totales": (
        Columna("fecha", "Fecha", 120),
        Columna("periferico", "Periférico", 160),
        Columna("tipo", "Tipo de conteo", 200),
        Columna("total", "Total del día", 150, "e"),
    ),
    "contadores": (
        Columna("fecha", "Fecha", 125),
        Columna("periferico", "Periférico", 145),
        Columna("tipo", "Tipo de conteo", 170),
        Columna("elemento", "Elemento", 170),
        Columna("cantidad", "Cantidad", 120, "e"),
    ),
    "alertas": (
        Columna("periferico", "Periférico", 150),
        Columna("umbral", "Umbral", 90),
        Columna("estado", "Estado", 110),
        Columna("intentos", "Intentos", 90),
        Columna("creada", "Creada", 185),
        Columna("enviada", "Enviada", 185),
    ),
}


def validar_fechas(desde: str, hasta: str) -> tuple[str, str]:
    """Valida DD/MM/AAAA y devuelve un rango ISO semiabierto."""
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

    # El repositorio usa un rango semiabierto.
    # Se agrega un día para incluir toda la fecha Hasta.
    return (
        inicio.isoformat(),
        (fin + timedelta(days=1)).isoformat(),
    )


def consultar_reporte(
    repo: Repositorio,
    tipo: str,
    desde: str,
    hasta: str,
) -> list[Fila]:
    """Obtiene las filas del reporte mediante el repositorio."""

    if tipo == "eventos":
        return repo.filas_de_eventos(desde, hasta)

    if tipo == "totales":
        return repo.filas_de_totales_diarios(desde, hasta)

    if tipo == "contadores":
        return repo.filas_de_contadores(desde, hasta)

    if tipo == "alertas":
        return repo.filas_de_alertas(desde, hasta)

    raise ValueError("Tipo de reporte no reconocido.")


def guardar_csv(
    tipo: str,
    ruta: Path,
    filas: list[Fila],
) -> int:
    """Delega la exportación al generador CSV del proyecto."""

    # Evita generar un CSV que solo contenga encabezados.
    if not filas:
        raise ValueError(
            "No hay registros para exportar."
        )

    if tipo == "eventos":
        return reporte_eventos(ruta, filas)

    if tipo == "totales":
        return reporte_totales_diarios(ruta, filas)

    if tipo == "contadores":
        return reporte_contadores(ruta, filas)

    if tipo == "alertas":
        return reporte_alertas(ruta, filas)

    raise ValueError("Tipo de reporte no reconocido.")


class PantallaP06(Pantalla):
    """Permite consultar y exportar reportes de Watchman."""

    TITULO: ClassVar[str] = "Reportes"

    SUBTITULO: ClassVar[str] = (
        "Exporta los datos registrados en un archivo CSV (RF14)."
    )

    @override
    def construir(self) -> None:
        """Crea los filtros, la tabla y los controles de exportación."""

        hoy = date.today()
        inicio = hoy - timedelta(days=30)

        # Variables de selección del reporte.
        self.tipo: tk.StringVar = tk.StringVar(
            value="totales"
        )

        self.desde: tk.StringVar = tk.StringVar(
            value=inicio.strftime("%d/%m/%Y")
        )

        self.hasta: tk.StringVar = tk.StringVar(
            value=hoy.strftime("%d/%m/%Y")
        )

        # Recupera la carpeta configurada anteriormente.
        carpeta_guardada = self.repo.leer_configuracion(
            "carpeta_reportes"
        )

        carpeta_predeterminada = (
            Path.home() / "Documents" / "ReportesWatchman"
        )

        self.carpeta: tk.StringVar = tk.StringVar(
            value=carpeta_guardada or str(carpeta_predeterminada)
        )

        self.aviso: tk.StringVar = tk.StringVar(
            value=""
        )

        self.archivo: tk.StringVar = tk.StringVar(
            value="Archivo: —"
        )

        # -------------------------------------------------
        # SECCIÓN 1: OPCIONES DEL REPORTE
        # -------------------------------------------------

        opciones = ttk.LabelFrame(
            self,
            text="Opciones del reporte",
            padding=12,
        )
        opciones.pack(
            fill="x",
            pady=(0, 12),
        )

        # Selección del tipo de reporte.
        tipos = ttk.Frame(opciones)
        tipos.pack(
            fill="x",
            pady=(0, 10),
        )

        ttk.Label(
            tipos,
            text="Tipo de reporte:",
        ).pack(
            side="left",
            padx=(0, 12),
        )

        for clave, titulo in OPCIONES:
            ttk.Radiobutton(
                tipos,
                text=titulo,
                value=clave,
                variable=self.tipo,
                command=self.actualizar_vista_previa,
            ).pack(
                side="left",
                padx=(0, 16),
            )

        # Selección del rango de fechas.
        fechas = ttk.Frame(opciones)
        fechas.pack(
            fill="x",
            pady=(0, 10),
        )

        ttk.Label(
            fechas,
            text="Desde:",
        ).pack(side="left")

        ttk.Entry(
            fechas,
            textvariable=self.desde,
            width=14,
        ).pack(
            side="left",
            padx=(8, 28),
        )

        ttk.Label(
            fechas,
            text="Hasta:",
        ).pack(side="left")

        ttk.Entry(
            fechas,
            textvariable=self.hasta,
            width=14,
        ).pack(
            side="left",
            padx=(8, 18),
        )

        ttk.Button(
            fechas,
            text="Actualizar vista previa",
            command=self.actualizar_vista_previa,
        ).pack(side="left")

        # Selección de carpeta de destino.
        destino = ttk.Frame(opciones)
        destino.pack(fill="x")

        ttk.Label(
            destino,
            text="Guardar en:",
        ).pack(
            side="left",
            padx=(0, 10),
        )

        ttk.Entry(
            destino,
            textvariable=self.carpeta,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10),
        )

        ttk.Button(
            destino,
            text="Examinar...",
            command=self.elegir_carpeta,
        ).pack(side="left")

        # -------------------------------------------------
        # SECCIÓN 2: VISTA PREVIA
        # -------------------------------------------------

        vista = ttk.LabelFrame(
            self,
            text="Vista previa",
            padding=10,
        )
        vista.pack(
            fill="both",
            expand=True,
            pady=(0, 10),
        )

        self.contenedor_tabla: ttk.Frame = ttk.Frame(
            vista
        )
        self.contenedor_tabla.pack(
            fill="both",
            expand=True,
        )

        self.tipo_tabla: str = "totales"

        self.tabla: Tabla = Tabla(
            self.contenedor_tabla,
            COLUMNAS["totales"],
            alto=7,
        )

        self.tabla.pack(
            fill="both",
            expand=True,
        )

        self.agregar_barra_horizontal()

        ttk.Label(
            vista,
            textvariable=self.aviso,
            style="Suave.TLabel",
        ).pack(
            anchor="w",
            pady=(6, 0),
        )

        # -------------------------------------------------
        # SECCIÓN 3: GENERAR CSV
        # -------------------------------------------------

        pie = ttk.Frame(self)
        pie.pack(fill="x")

        ttk.Label(
            pie,
            textvariable=self.archivo,
            style="Suave.TLabel",
        ).pack(
            side="left",
            fill="x",
            expand=True,
        )

        self.boton_generar: ttk.Button = ttk.Button(
            pie,
            text="Generar CSV",
            command=self.generar,
        )

        self.boton_generar.pack(
            side="right"
        )

        # El botón permanece inactivo si no hay registros.
        self.boton_generar.configure(
            state="disabled"
        )

    def agregar_barra_horizontal(self) -> None:
        """Agrega desplazamiento horizontal a la tabla actual."""

        barra = ttk.Scrollbar(
            self.tabla,
            orient="horizontal",
            command=self.tabla.arbol.xview,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
        )

        self.tabla.arbol.configure(
            xscrollcommand=barra.set
        )

        barra.grid(
            row=1,
            column=0,
            sticky="ew",
        )

    def cambiar_columnas(self, tipo: str) -> None:
        """Actualiza las columnas para el reporte seleccionado."""

        if tipo == self.tipo_tabla:
            return

        # Se crea una tabla nueva porque cada reporte
        # tiene una estructura de columnas diferente.
        self.tabla.destroy()

        self.tabla = Tabla(
            self.contenedor_tabla,
            COLUMNAS[tipo],
            alto=7,
        )

        self.tabla.pack(
            fill="both",
            expand=True,
        )

        self.agregar_barra_horizontal()
        self.tipo_tabla = tipo

    def elegir_carpeta(self) -> None:
        """Permite elegir una carpeta desde el explorador."""

        carpeta = filedialog.askdirectory(
            title="Seleccionar carpeta para reportes"
        )

        if carpeta:
            self.carpeta.set(carpeta)

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Actualiza los datos cuando se vuelve a abrir P06."""

        _ = parametros
        self.actualizar_vista_previa()

    def actualizar_vista_previa(self) -> None:
        """Muestra cinco filas y habilita exportar si hay datos."""

        self.boton_generar.configure(
            state="disabled"
        )

        self.tabla.limpiar()

        try:
            inicio, fin_exclusivo = validar_fechas(
                self.desde.get(),
                self.hasta.get(),
            )

            tipo = self.tipo.get()

            filas = consultar_reporte(
                self.repo,
                tipo,
                inicio,
                fin_exclusivo,
            )

            self.cambiar_columnas(tipo)

        except ValueError as error:
            self.aviso.set(str(error))
            self.archivo.set("Archivo: —")
            return

        # La vista previa muestra únicamente cinco filas.
        # El archivo final incluirá todos los registros.
        self.tabla.llenar(
            FilaDeTabla(
                tuple(
                    "—" if valor is None else str(valor)
                    for valor in fila
                )
            )
            for fila in filas[:5]
        )

        if not filas:
            self.aviso.set(
                "No hay datos para el rango seleccionado."
            )

        else:
            self.aviso.set(
                f"Se muestran hasta 5 filas. Se exportarán {len(filas)} registros."
            )

            self.boton_generar.configure(
                state="normal"
            )

        fecha_fin = datetime.strptime(
            self.hasta.get().strip(),
            "%d/%m/%Y",
        ).date().isoformat()

        self.archivo.set(
            f"Archivo: {tipo}_{inicio}_{fecha_fin}.csv"
        )

    def generar(self) -> None:
        """Genera el CSV cuando hay registros y una carpeta válida."""

        try:
            inicio, fin_exclusivo = validar_fechas(
                self.desde.get(),
                self.hasta.get(),
            )

            tipo = self.tipo.get()

            # Se consulta nuevamente para exportar datos
            # actualizados, no una vista previa antigua.
            filas = consultar_reporte(
                self.repo,
                tipo,
                inicio,
                fin_exclusivo,
            )

            if not filas:
                self.actualizar_vista_previa()

                messagebox.showinfo(
                    "Sin datos",
                    "No hay registros en el rango seleccionado.",
                )
                return

            carpeta_texto = self.carpeta.get().strip()

            if not carpeta_texto:
                raise ValueError(
                    "Selecciona una carpeta de destino."
                )

            carpeta = Path(
                carpeta_texto
            ).expanduser()

            fecha_fin = datetime.strptime(
                self.hasta.get().strip(),
                "%d/%m/%Y",
            ).date().isoformat()

            nombre = (
                f"{tipo}_{inicio}_{fecha_fin}.csv"
            )


            
            
            destino = carpeta / nombre

            # Evita sobrescribir un reporte sin autorización.
            if destino.exists():
                confirmar = messagebox.askyesno(
                    "El archivo ya existe",
                    (
                        f"Ya existe un reporte con este nombre:\n\n"
                        f"{destino.name}\n\n"
                        "¿Deseas reemplazarlo?"
                    ),
                )

                if not confirmar:
                    self.aviso.set(
                        "Exportación cancelada. El archivo existente se conservó."
                    )
                    return

            # Genera el CSV cuando el archivo no existe
            # o cuando el usuario autorizó reemplazarlo.
            cantidad = guardar_csv(
                tipo,
                destino,
                filas,
            )



            # Guarda la carpeta utilizada para futuros reportes.
            self.repo.escribir_configuracion(
                "carpeta_reportes",
                str(carpeta),
            )

        except (ValueError, OSError) as error:
            messagebox.showerror(
                "No se pudo generar el CSV",
                str(error),
            )
            return

        self.aviso.set(
            f"Reporte generado correctamente: {cantidad} registros."
        )

        self.archivo.set(
            f"Archivo: {destino}"
        )

        messagebox.showinfo(
            "Reporte generado",
            f"Se exportaron {cantidad} registros.\n\n{destino}",
        )
