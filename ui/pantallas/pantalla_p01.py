"""Pantalla P01 · Panel principal (RF11, RF23).

Qué muestra: el estado de la captura (activa, detenida o con el servicio apagado) con los botones "Iniciar captura" y "Detener
captura", los datos del día (reinicios del capturador, tiempo de actividad y eventos registrados), los periféricos del equipo con su
desgaste frente al límite y las alertas pendientes de envío. Es la pantalla con la que abre la interfaz.

Cómo funciona: la interfaz y el servicio son dos procesos y se hablan solo por la tabla `configuracion` (decisión de arquitectura 1).
Los botones escriben `orden_captura` (`iniciar` o `detener`) y el servicio la aplica en pocos segundos (`servicio/control.py`).
La pantalla no cree que la orden ya se cumplió: lee `estado_captura` y `latido_servicio` con `leer_estado` y muestra lo que el servicio
de verdad hace. Por eso, entre que se pulsa "Detener" y el servicio responde, dice "Deteniendo captura…"; y si el latido es viejo,
dice que el servicio no está en marcha, aunque el último estado haya sido "capturando".

Se actualiza sola mientras la ventana está abierta (un temporizador de Tk): el estado y los botones cada 2 s, y los datos del día y las
tablas cada 10 s. El temporizador se cancela al cerrar la ventana. Si la base no se puede leer un momento (la ocupa el servicio), la
pantalla lo dice en el estado y lo reintenta; no abre cuadros de mensaje cada 2 segundos.

Lo que no dibuja va en funciones puras (`estado_visible`, `botones_activos`, `filas_de_perifericos_del_panel`, `tiempo_hasta`…) que se
prueban sin abrir una ventana en `pruebas/test_pantalla_p01.py`.

Privacidad (RNF4): solo hay totales y porcentajes por periférico, sin nombres de teclas (la tecla más gastada se ve en P03).

Mockup: `docs/mockups/P01_PanelPrincipal.png`. Guía: `docs/interfaz.md`.

Se relaciona con: usa `ui/pantalla_base.py`, `ui/componentes.py` (`Tabla`), `ui/formato.py`, las funciones de texto de
`ui/pantallas/pantalla_p02.py` y `ui/pantallas/pantalla_p03.py` (`miles`), `servicio/control.py` (`leer_estado` y las claves de la
orden) y el repositorio (`listar_perifericos`, `alertas_pendientes`, `actividad_del_dia`, `contar_eventos`, `contar_incidentes`,
`escribir_configuracion`) · la registra `ui/registro.py` y la prueba `pruebas/test_pantalla_p01.py`.
"""
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import ClassVar, override

from comun.repositorio import FilaAlerta, ResumenPeriferico, UsoDeConteo
from servicio.control import (
    CLAVE_ORDEN,
    ESTADO_CAPTURANDO,
    INTERVALO_DE_LECTURA,
    ORDEN_DETENER,
    ORDEN_INICIAR,
    EstadoDelServicio,
    leer_estado,
)
from ui.componentes import Columna, FilaDeTabla, Tabla
from ui.formato import SIN_DATO, duracion, fecha_hora_legible, porcentaje
from ui.pantalla_base import Pantalla
from ui.pantallas.pantalla_p02 import (
    NOMBRE_CORTO_DEL_CONTEO,
    ORDEN_DEL_CONTEO,
    SIN_LIMITE,
    alerta_principal,
    etiqueta_de_color,
    texto_estado,
    texto_etiqueta,
    texto_modelo,
    texto_tipo,
)
from ui.pantallas.pantalla_p03 import miles

CLAVE_DESTINATARIOS = "destinatarios"
INTERVALO_DEL_ESTADO_MS = int(INTERVALO_DE_LECTURA * 1000)  # cada cuánto se vuelve a leer el estado del servicio
CICLOS_POR_REFRESCO_COMPLETO = 5  # cada cuántas lecturas del estado se refrescan también los datos del día y las tablas

TEXTO_SERVICIO_APAGADO = "Servicio detenido"
AVISO_SERVICIO_APAGADO = (
    "El servicio de monitoreo no está en marcha. La orden se guarda y se aplicará cuando el servicio arranque (al iniciar sesión en Windows)."
)
SIN_ALERTAS = "No hay alertas pendientes de envío."
SIN_PERIFERICOS = "Todavía no hay periféricos: aparecen cuando el servicio recibe el primer evento de un teclado o un mouse."
FALLA_DE_LECTURA = "No se pudo leer la base de datos. Se reintentará en unos segundos."


# ---------- Funciones puras: arman los textos sin usar Tk ----------


def estado_visible(estado: EstadoDelServicio) -> tuple[str, str]:
    """El texto grande del estado y el estilo con que se pinta: `("● Captura ACTIVA", "Exito.TLabel")`.

    Compara lo que se pidió (`orden`) con lo que el servicio dice que hace (`estado`): mientras no coinciden, la captura está en
    transición y se muestra gris, no como un hecho. Si el servicio no está en marcha, no se afirma nada sobre la captura.
    """
    if not estado.en_marcha:
        return f"● {TEXTO_SERVICIO_APAGADO}", "Peligro.TLabel"
    captura_activa = estado.estado == ESTADO_CAPTURANDO
    quiere_detener = estado.orden == ORDEN_DETENER
    if captura_activa and not quiere_detener:
        return "● Captura ACTIVA", "Exito.TLabel"
    if captura_activa:
        return "● Deteniendo captura…", "Suave.TLabel"
    if quiere_detener:
        return "● Captura DETENIDA", "Peligro.TLabel"
    return "● Iniciando captura…", "Suave.TLabel"


def texto_del_proceso(estado: EstadoDelServicio) -> str:
    """Cómo está el proceso del capturador: `en ejecución`, `detenido` o `servicio apagado`."""
    if not estado.en_marcha:
        return "servicio apagado"
    return "en ejecución" if estado.estado == ESTADO_CAPTURANDO else "detenido"


def botones_activos(estado: EstadoDelServicio) -> tuple[bool, bool]:
    """Qué botones se pueden pulsar: `(iniciar, detener)`.

    Se decide por la ORDEN y no por el estado: con la orden "detener" ya dada solo tiene sentido "Iniciar", y viceversa. Así los botones
    responden al instante, sin esperar a que el servicio cumpla la orden, y siguen sirviendo si el servicio está apagado.
    """
    quiere_detener = estado.orden == ORDEN_DETENER
    return quiere_detener, not quiere_detener


def texto_de_actividad(segundos_teclado: int, segundos_mouse: int) -> str:
    """El tiempo de actividad del día: `Teclado 3 h 12 min · Mouse 2 h 47 min`."""
    return f"Teclado {duracion(segundos_teclado)} · Mouse {duracion(segundos_mouse)}"


def _con_limite_ordenados(periferico: ResumenPeriferico) -> list[UsoDeConteo]:
    """Los usos con límite, en el orden fijo teclas, clics, scroll (sin límite no hay porcentaje que mostrar)."""
    def posicion(uso: UsoDeConteo) -> int:
        """La posición del tipo de conteo en ORDEN_DEL_CONTEO; los desconocidos van al final."""
        return ORDEN_DEL_CONTEO.index(uso.tipo_conteo) if uso.tipo_conteo in ORDEN_DEL_CONTEO else len(ORDEN_DEL_CONTEO)

    return sorted((uso for uso in periferico.usos if uso.porcentaje is not None), key=posicion)


def filas_de_perifericos_del_panel(perifericos: Iterable[ResumenPeriferico], alertas: Sequence[FilaAlerta]) -> list[FilaDeTabla]:
    """Las filas de "Periféricos de este equipo": los activos, con una fila por tipo de conteo (el mouse tiene clics y scroll).

    Como en el mockup, la fila lleva `Mouse · clics` cuando el periférico tiene varios conteos con límite. Un periférico sin ningún
    límite (modelo desconocido) tiene una sola fila con `Sin límite`. Los retirados no salen: están en P02.
    """
    filas: list[FilaDeTabla] = []
    for periferico in perifericos:
        if not periferico.activo:
            continue
        alerta = alerta_principal(alertas, periferico.id)
        estado = texto_estado(periferico, alerta)
        color = etiqueta_de_color(periferico, alerta)
        usos = _con_limite_ordenados(periferico)
        if not usos:
            valores = (texto_tipo(periferico.tipo), texto_modelo(periferico), texto_etiqueta(periferico), SIN_LIMITE, estado)
            filas.append(FilaDeTabla(valores, id=str(periferico.id), etiqueta=color))
            continue
        for uso in usos:
            tipo = texto_tipo(periferico.tipo)
            if len(usos) > 1:
                tipo = f"{tipo} · {NOMBRE_CORTO_DEL_CONTEO.get(uso.tipo_conteo, uso.tipo_conteo)}"
            valores = (tipo, texto_modelo(periferico), texto_etiqueta(periferico), porcentaje(uso.porcentaje), estado)
            filas.append(FilaDeTabla(valores, id=f"{periferico.id}-{uso.tipo_conteo}", etiqueta=color))
    return filas


def tiempo_hasta(texto: str | None, ahora: datetime) -> str:
    """Cuánto falta para un momento: `en 14 min`, `en 2 h`, `ahora` (si ya pasó) o `—` (sin fecha).

    texto: fecha y hora ISO 8601. ahora: el momento que se toma como "ahora" (se recibe para poder probarla).
    Lanza ValueError si el texto no es una fecha. Menos de un minuto cuenta como `en menos de 1 min`; más de un día se muestra como fecha.
    """
    if not texto:
        return SIN_DATO
    falta = (datetime.fromisoformat(texto) - ahora).total_seconds()
    if falta <= 0:
        return "ahora"
    if falta < 60:
        return "en menos de 1 min"
    if falta < 3600:
        return f"en {int(falta // 60)} min"
    if falta < 86400:
        return f"en {int(falta // 3600)} h"
    return fecha_hora_legible(texto, ahora)


def filas_de_alertas_pendientes(alertas: Iterable[FilaAlerta], ahora: datetime) -> list[FilaDeTabla]:
    """Las filas de "Alertas pendientes de envío": umbral, periférico, estado, intentos y cuándo se reintenta.

    El estado dice `Pendiente` y, si ya hubo intentos, `Pendiente (reintentando)`. No se muestra el texto del error ni el detalle de la
    alerta (que puede nombrar la tecla más gastada): eso lo ve P07.
    """
    filas: list[FilaDeTabla] = []
    for alerta in alertas:
        estado = "Pendiente (reintentando)" if alerta.intentos > 0 else "Pendiente"
        filas.append(FilaDeTabla((
            f"{alerta.umbral} %",
            f"{alerta.etiqueta or 'Sin etiqueta'} · {alerta.modelo}",
            estado,
            str(alerta.intentos),
            tiempo_hasta(alerta.proximo_reintento, ahora),
        ), id=f"alerta-{alerta.id}"))
    return filas


def texto_de_destinatarios(valor: str | None) -> str:
    """Quién recibe los correos: `Destinatarios: soporte@…`, o un aviso si todavía no se configuraron (se definen en Configuración)."""
    if valor is None or not valor.strip():
        return "Destinatarios: sin configurar (se definen en Configuración)."
    return f"Destinatarios: {valor.strip()}"


# ---------- La pantalla ----------


class PantallaP01(Pantalla):
    """Panel principal: estado de la captura, botones para iniciar y detener, periféricos del equipo y alertas pendientes."""

    TITULO: ClassVar[str] = "Panel principal"
    SUBTITULO: ClassVar[str] = ""

    @override
    def construir(self) -> None:
        """Dibuja los tres recuadros del mockup. Se llama una sola vez; los datos los pone `refrescar`."""
        # Las dos tablas se reparten el alto que sobra y se achican (con barra de desplazamiento) si la ventana es baja: así nada queda
        # fuera de la ventana ni siquiera con su tamaño mínimo.
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=2)
        self._reloj: Callable[[], datetime] = datetime.now  # las pruebas lo reemplazan por una hora fija
        self._temporizador: str | None = None  # identificador de la próxima lectura programada con `after`
        self._lecturas: int = 0

        self._dibujar_estado_de_la_captura()
        self._dibujar_perifericos()
        self._dibujar_alertas()

    def _dibujar_estado_de_la_captura(self) -> None:
        """El recuadro de arriba: estado grande, datos del día a la izquierda y los dos botones a la derecha."""
        marco = ttk.LabelFrame(self, text="Estado de la captura", padding=10)
        marco.grid(row=0, column=0, sticky="ew")
        marco.columnconfigure(1, weight=1)

        self.estado: ttk.Label = ttk.Label(marco, text="", style="Exito.TLabel")
        self.estado.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.aviso: ttk.Label = ttk.Label(marco, text="", style="Suave.TLabel", wraplength=520, justify="left")
        self.aviso.grid(row=1, column=0, columnspan=2, sticky="w")
        self.aviso.grid_remove()  # solo se muestra cuando hay algo que decir: así no ocupa una línea vacía

        self._datos: dict[str, ttk.Label] = {}
        for numero, (clave, titulo) in enumerate((
            ("proceso", "Proceso de captura (C++):"),
            ("reinicios", "Reinicios automáticos hoy:"),
            ("actividad", "Tiempo de actividad hoy:"),
            ("eventos", "Eventos registrados hoy:"),
        ), start=2):
            ttk.Label(marco, text=titulo, style="Suave.TLabel").grid(row=numero, column=0, sticky="w", padx=(0, 12), pady=1)
            valor = ttk.Label(marco, text=SIN_DATO)
            valor.grid(row=numero, column=1, sticky="w", pady=1)
            self._datos[clave] = valor

        botones = ttk.Frame(marco)
        botones.grid(row=0, column=2, rowspan=6, sticky="ne", padx=(20, 0))
        self.boton_iniciar: ttk.Button = ttk.Button(botones, text="Iniciar captura", command=self.iniciar_captura, width=18)
        self.boton_iniciar.pack(pady=(0, 8))
        self.boton_detener: ttk.Button = ttk.Button(botones, text="Detener captura", command=self.detener_captura, width=18)
        self.boton_detener.pack()

    def _dibujar_perifericos(self) -> None:
        """El recuadro del medio: la tabla de periféricos del equipo."""
        marco = ttk.LabelFrame(self, text="Periféricos de este equipo", padding=8)
        marco.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)
        columnas = [
            Columna("tipo", "Tipo", 110),
            Columna("modelo", "Modelo", 150),
            Columna("etiqueta", "Etiqueta", 110),
            Columna("vida_util", "Vida útil usada", 120),
            Columna("estado", "Estado", 270),
        ]
        self.tabla_perifericos: Tabla = Tabla(marco, columnas, alto=4)
        self.tabla_perifericos.grid(row=0, column=0, sticky="nsew")
        self.nota_perifericos: ttk.Label = ttk.Label(marco, text="", style="Suave.TLabel")
        self.nota_perifericos.grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.nota_perifericos.grid_remove()

    def _dibujar_alertas(self) -> None:
        """El recuadro de abajo: las alertas que todavía no se pudieron enviar y quién las recibe."""
        marco = ttk.LabelFrame(self, text="Alertas pendientes de envío", padding=8)
        marco.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        marco.columnconfigure(0, weight=1)
        marco.rowconfigure(0, weight=1)
        columnas = [
            Columna("umbral", "Umbral", 70),
            Columna("periferico", "Periférico", 200),
            Columna("estado", "Estado", 200),
            Columna("intentos", "Intentos", 70),
            Columna("reintento", "Próximo reintento", 170),
        ]
        self.tabla_alertas: Tabla = Tabla(marco, columnas, alto=2)
        self.tabla_alertas.grid(row=0, column=0, sticky="nsew")
        self.nota_alertas: ttk.Label = ttk.Label(marco, text="", style="Suave.TLabel")
        self.nota_alertas.grid(row=1, column=0, sticky="w", pady=(4, 0))

    # ---------- Datos ----------

    @override
    def al_mostrar(self, **parametros: object) -> None:
        """Refresca todo cada vez que se muestra la pantalla y, la primera vez, empieza a actualizarse sola. No usa parámetros."""
        _ = parametros
        self.refrescar(completo=True)
        if self._temporizador is None:
            self._temporizador = self.after(INTERVALO_DEL_ESTADO_MS, self._actualizar_sola)

    def refrescar(self, completo: bool = True) -> None:
        """Vuelve a leer el estado del servicio y, si `completo`, también los datos del día y las dos tablas.

        completo=False es la lectura barata de cada 2 s (estado y botones); completo=True la de cada 10 s y la de al mostrar la pantalla.
        """
        ahora = self._reloj()
        estado = leer_estado(self.repo, ahora, INTERVALO_DE_LECTURA)
        texto, estilo = estado_visible(estado)
        self.estado.configure(text=texto, style=estilo)
        self.aviso.configure(text="" if estado.en_marcha else AVISO_SERVICIO_APAGADO)
        if estado.en_marcha:
            self.aviso.grid_remove()
        else:
            self.aviso.grid()
        self._datos["proceso"].configure(text=texto_del_proceso(estado))
        puede_iniciar, puede_detener = botones_activos(estado)
        self.boton_iniciar.state(["!disabled"] if puede_iniciar else ["disabled"])
        self.boton_detener.state(["!disabled"] if puede_detener else ["disabled"])
        if completo:
            self._refrescar_datos_del_dia(ahora.date())
            self._refrescar_tablas(ahora)

    def _refrescar_datos_del_dia(self, hoy: date) -> None:
        """Escribe los reinicios del capturador, el tiempo de actividad y los eventos registrados de hoy."""
        desde, hasta = hoy.isoformat(), (hoy + timedelta(days=1)).isoformat()
        segundos_teclado, segundos_mouse = self.repo.actividad_del_dia(desde)
        self._datos["reinicios"].configure(text=str(self.repo.contar_incidentes("caida_proceso", desde, hasta)))
        self._datos["actividad"].configure(text=texto_de_actividad(segundos_teclado, segundos_mouse))
        self._datos["eventos"].configure(text=miles(self.repo.contar_eventos(desde, hasta)))

    def _refrescar_tablas(self, ahora: datetime) -> None:
        """Llena la tabla de periféricos y la de alertas pendientes, y el destinatario."""
        perifericos = self.repo.listar_perifericos(incluir_retirados=False)
        self.tabla_perifericos.llenar(filas_de_perifericos_del_panel(perifericos, self.repo.listar_alertas()))
        self.nota_perifericos.configure(text="" if perifericos else SIN_PERIFERICOS)
        if perifericos:
            self.nota_perifericos.grid_remove()
        else:
            self.nota_perifericos.grid()
        alertas = self.repo.alertas_pendientes()
        self.tabla_alertas.llenar(filas_de_alertas_pendientes(alertas, ahora))
        destinatarios = texto_de_destinatarios(self.repo.leer_configuracion(CLAVE_DESTINATARIOS))
        self.nota_alertas.configure(text=destinatarios if alertas else f"{SIN_ALERTAS}  {destinatarios}")

    def _actualizar_sola(self) -> None:
        """Lectura periódica: refresca el estado y, cada `CICLOS_POR_REFRESCO_COMPLETO` lecturas, también los datos del día y las tablas."""
        self._lecturas += 1
        try:
            self.refrescar(completo=self._lecturas % CICLOS_POR_REFRESCO_COMPLETO == 0)
        except Exception:  # la base puede estar ocupada un momento: se avisa en el estado y se reintenta, sin cuadros de mensaje cada 2 s
            self.estado.configure(text=f"● {FALLA_DE_LECTURA}", style="Suave.TLabel")
        self._temporizador = self.after(INTERVALO_DEL_ESTADO_MS, self._actualizar_sola)

    @override
    def destroy(self) -> None:
        """Cancela la próxima lectura programada antes de destruir la pantalla; si no, Tk llamaría a un widget que ya no existe."""
        if self._temporizador is not None:
            self.after_cancel(self._temporizador)
            self._temporizador = None
        super().destroy()

    # ---------- Los botones ----------

    def iniciar_captura(self) -> None:
        """Deja la orden "iniciar" en la base: el servicio la aplica en pocos segundos."""
        self._dar_orden(ORDEN_INICIAR)

    def detener_captura(self) -> None:
        """Deja la orden "detener" en la base: el servicio la aplica en pocos segundos."""
        self._dar_orden(ORDEN_DETENER)

    def _dar_orden(self, orden: str) -> None:
        """Escribe la orden y refresca el estado al instante (mostrará "Deteniendo…" o "Iniciando…" hasta que el servicio responda)."""
        try:
            self.repo.escribir_configuracion(CLAVE_ORDEN, orden)
            self.refrescar(completo=False)
        except Exception:  # la base ocupada o ilegible: se le dice a la persona que pulse otra vez, sin mostrar un error técnico
            messagebox.showwarning(
                "No se pudo enviar la orden", "La base de datos está ocupada. Vuelve a pulsar el botón en unos segundos.", parent=self,
            )

