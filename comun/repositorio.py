"""Repositorio SQLite: el único punto de acceso a la base de datos (decisión de arquitectura 4).

El servicio y la interfaz son dos procesos que comparten el archivo `eventos.db`, así que cada uno
crea su propio `Repositorio`. Este módulo no decide nada del negocio: guarda y consulta. Las reglas
(cuándo se abre una sesión, cuándo se guarda un contador) viven en el servicio.

Reglas que este módulo hace cumplir:
- Cada conexión ejecuta los PRAGMA de docs/base-de-datos/README.md (WAL, claves foráneas y espera).
- No hay ningún método para guardar qué tecla se pulsó junto a un evento (RNF4): la tabla `evento`
  no tiene esa columna y `guardar_evento` no recibe ese dato.
- Las fechas llegan como texto ISO 8601; el repositorio no usa el reloj, así que las pruebas son exactas.

Cómo funciona, a grandes rasgos:
- Una sola conexión por `Repositorio`, compartida entre hilos. `check_same_thread=False` lo permite y
  un `threading.Lock` (`_candado`) ordena los accesos, porque el servicio escribe desde varios hilos.
- Cada operación de escritura va en una transacción corta (`with self._conexion`): se confirma al
  salir del bloque y se deshace si hay un error. Así un apagado brusco deja la base consistente (RNF12).
- La primera vez que se abre un archivo nuevo, ejecuta `docs/base-de-datos/schema.sql` para crear las tablas.
- Los SQL van como constantes de módulo, con parámetros `?`: nunca se arma una consulta pegando texto.
- Las lecturas para la interfaz devuelven dataclasses inmutables (`ResumenPeriferico`, `FilaSesion`, `FilaAlerta`…)
  y las de reportes devuelven filas de datos simples. Ninguna trae una tecla junto a un evento (RNF4): las
  teclas solo salen como totales por día en `filas_de_contadores` y `totales_por_elemento`.
- Los rangos de fechas son semiabiertos: `desde` entra y `hasta` no. Pueden ser `AAAA-MM-DD` o fecha y hora ISO 8601;
  `None` significa "sin límite".

Se relaciona con: usa `docs/base-de-datos/schema.sql` (tablas, restricciones y PRAGMA) y la variable de
entorno CAPTURADOR_RUTA_DB · lo usan `servicio/guardador.py`, `servicio/sesion.py`, `servicio/contador.py`
(a través de `Conteo` y `EventoParaGuardar`), las pantallas de `ui/` (lecturas), `servicio/evaluador.py` y
`servicio/notificador.py` (alertas), `reportes/` y `analisis/` (que reciben las filas y las horas que entregan
`filas_de_*` y `horas_de_eventos`) y las pruebas de `pruebas/`.
"""
import os
import sqlite3
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self, cast

RAIZ_DEL_PROYECTO = Path(__file__).resolve().parent.parent
RUTA_ESQUEMA_POR_DEFECTO = RAIZ_DEL_PROYECTO / "docs" / "base-de-datos" / "schema.sql"

ESPERA_DE_BLOQUEO_MS = 5000
NOMBRE_DESCONOCIDO = "desconocido"  # fabricante y nombre de un modelo que aún no está en el catálogo
VARIABLE_DE_RUTA = "CAPTURADOR_RUTA_DB"

type Fila = tuple[object, ...]  # una fila leída de SQLite; sus valores se convierten con `_entero` o `str`

# Consultas que se repiten o que son largas. Las demás (de una línea) van dentro de su método.
SQL_INSERTAR_PERIFERICO = """
    INSERT INTO periferico (id_modelo, id_equipo, estado_asignacion, activo, fecha_asignacion)
    VALUES (?, ?, 'por_confirmar', 1, ?)
"""
SQL_INSERTAR_EVENTO = """
    INSERT INTO evento (id_sesion, id_periferico, tipo_evento, fecha_hora, x, y)
    VALUES (?, ?, ?, ?, ?, ?)
"""
SQL_INSERTAR_INCIDENTE = """
    INSERT INTO incidente (id_sesion, tipo, fecha_hora, detalle, accion)
    VALUES (?, ?, ?, ?, ?)
"""
SQL_ACTUALIZAR_ACTIVIDAD = """
    UPDATE sesion SET seg_actividad_teclado = ?, seg_actividad_mouse = ? WHERE id = ?
"""
SQL_CERRAR_SESION = """
    UPDATE sesion
    SET fin = ?, tipo_cierre = ?, seg_actividad_teclado = ?, seg_actividad_mouse = ?
    WHERE id = ?
"""
# Para cada sesión sin `fin`, devuelve su id y su último momento conocido: la hora del último evento o,
# si no tuvo ninguno, su inicio. Esa hora será el `fin` al cerrarla como inesperada (RNF12).
SQL_SESIONES_ABIERTAS = """
    SELECT s.id, COALESCE((SELECT MAX(e.fecha_hora) FROM evento e WHERE e.id_sesion = s.id), s.inicio)
    FROM sesion s
    WHERE s.fin IS NULL
"""
SQL_INCIDENTE_DE_APAGADO = """
    INSERT INTO incidente (id_sesion, tipo, fecha_hora, detalle, accion)
    VALUES (?, 'apagado_inesperado', ?, ?, ?)
"""
# "Upsert": si ya hay fila para ese periférico, día, tipo y elemento, suma; si no, la crea. Así el
# desgaste de un día es una sola fila por tecla y nunca se guarda la secuencia de pulsaciones (RNF4).
# Requiere la clave primaria compuesta de `contador_diario` (ver schema.sql).
SQL_SUMAR_A_CONTADOR = """
    INSERT INTO contador_diario (id_periferico, fecha, tipo_conteo, elemento, cantidad)
    VALUES (?, ?, ?, ?, ?)
    ON CONFLICT (id_periferico, fecha, tipo_conteo, elemento)
    DO UPDATE SET cantidad = cantidad + excluded.cantidad
"""
SQL_TOTAL_DE_UN_ELEMENTO = """
    SELECT COALESCE(SUM(cantidad), 0) FROM contador_diario
    WHERE id_periferico = ? AND tipo_conteo = ? AND elemento = ?
"""
SQL_TOTALES_POR_ELEMENTO = """
    SELECT elemento, SUM(cantidad) FROM contador_diario
    WHERE id_periferico = ? AND tipo_conteo = ?
    GROUP BY elemento
"""
# Upsert por `clave`: escribir dos veces la misma clave reemplaza el valor (por ejemplo, la orden de la interfaz).
SQL_ESCRIBIR_CONFIGURACION = """
    INSERT INTO configuracion (clave, valor) VALUES (?, ?)
    ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor
"""

# ---------- Lecturas para la interfaz, los reportes y el análisis ----------
# Los filtros opcionales usan el patrón `(? IS NULL OR campo = ?)`: se pasa el mismo valor dos veces y,
# si es None, la condición no filtra. Así hay una sola consulta por lectura y ninguna se arma pegando texto.

# Datos de un periférico y de su modelo; el uso (totales y límites) se junta aparte, en `_resumen_de`.
SQL_PERIFERICOS = """
    SELECT p.id, p.id_equipo, p.id_modelo, p.etiqueta, p.estado_asignacion, p.activo, p.fecha_asignacion,
           p.fecha_retiro, m.fabricante, m.nombre, m.tipo, m.vid, m.pid
    FROM periferico p
    JOIN modelo_periferico m ON m.id = p.id_modelo
"""
# Los retirados (`activo = 0`) salen al final; el tercer parámetro es 1 para incluirlos y 0 para ocultarlos.
SQL_LISTAR_PERIFERICOS = SQL_PERIFERICOS + """
    WHERE (? IS NULL OR p.id_equipo = ?) AND (? OR p.activo = 1)
    ORDER BY p.activo DESC, p.id
"""
SQL_UN_PERIFERICO = SQL_PERIFERICOS + " WHERE p.id = ?"
SQL_LIMITES_DE_UN_MODELO = "SELECT tipo_conteo, limite FROM limite_modelo WHERE id_modelo = ?"
SQL_LIMITES_DE_UN_PERIFERICO = """
    SELECT l.tipo_conteo, l.limite
    FROM limite_modelo l
    JOIN periferico p ON p.id_modelo = l.id_modelo
    WHERE p.id = ?
"""
SQL_TOTALES_POR_TIPO = """
    SELECT tipo_conteo, SUM(cantidad) FROM contador_diario WHERE id_periferico = ? GROUP BY tipo_conteo
"""

# Las sesiones del día son las que EMPEZARON ese día: una sesión que cruza la medianoche cuenta en su día de inicio.
SQL_LISTAR_SESIONES = """
    SELECT id, id_equipo, inicio, fin, tipo_cierre, seg_actividad_teclado, seg_actividad_mouse
    FROM sesion
    WHERE (? IS NULL OR id_equipo = ?) AND (? IS NULL OR inicio >= ?) AND (? IS NULL OR inicio < ?)
    ORDER BY inicio DESC, id DESC
"""
SQL_ACTIVIDAD_DE_SESIONES = """
    SELECT COALESCE(SUM(seg_actividad_teclado), 0), COALESCE(SUM(seg_actividad_mouse), 0)
    FROM sesion
    WHERE (? IS NULL OR id_equipo = ?) AND inicio >= ? AND inicio < ?
"""
SQL_INCIDENTES_RECIENTES = """
    SELECT id, id_sesion, tipo, fecha_hora, detalle, accion
    FROM incidente
    ORDER BY fecha_hora DESC, id DESC
    LIMIT ?
"""

# Alertas con los datos del periférico, listas para mostrarse o enviarse. Falta el ORDER BY, que cambia según quién la use.
SQL_ALERTAS = """
    SELECT a.id, a.id_periferico, p.etiqueta, m.nombre, a.umbral, a.estado, a.detalle, a.fecha_creacion,
           a.intentos, a.fecha_ultimo_intento, a.proximo_reintento, a.ultimo_error, a.fecha_envio
    FROM alerta a
    JOIN periferico p ON p.id = a.id_periferico
    JOIN modelo_periferico m ON m.id = p.id_modelo
    WHERE (? IS NULL OR a.estado = ?)
"""
SQL_ALERTAS_RECIENTES = SQL_ALERTAS + " ORDER BY a.fecha_creacion DESC, a.id DESC"
SQL_ALERTAS_ANTIGUAS = SQL_ALERTAS + " ORDER BY a.id"
# `ON CONFLICT DO NOTHING` apoya el índice único (id_periferico, umbral): una alerta por periférico y umbral (RF19, RNF12).
SQL_CREAR_ALERTA = """
    INSERT INTO alerta (id_periferico, umbral, fecha_creacion, detalle) VALUES (?, ?, ?, ?)
    ON CONFLICT (id_periferico, umbral) DO NOTHING
"""
# Solo se tocan alertas pendientes: una alerta ya enviada no se reintenta ni se vuelve a marcar.
SQL_REGISTRAR_INTENTO = """
    UPDATE alerta
    SET intentos = intentos + 1, fecha_ultimo_intento = ?, proximo_reintento = ?, ultimo_error = ?
    WHERE id = ? AND estado = 'pendiente'
"""
SQL_MARCAR_ENVIADA = """
    UPDATE alerta
    SET estado = 'enviada', intentos = intentos + 1, fecha_ultimo_intento = ?, fecha_envio = ?, proximo_reintento = NULL
    WHERE id = ? AND estado = 'pendiente'
"""

# Horas de los eventos para el mapa de calor. `tecla_liberada` queda fuera salvo que se pida: cada pulsación genera dos
# eventos (presionada y liberada), y contarlos doble haría pesar más al teclado que al mouse.
SQL_HORAS_DE_EVENTOS = """
    SELECT e.fecha_hora
    FROM evento e
    JOIN periferico p ON p.id = e.id_periferico
    JOIN modelo_periferico m ON m.id = p.id_modelo
    WHERE (? IS NULL OR e.fecha_hora >= ?) AND (? IS NULL OR e.fecha_hora < ?)
      AND (? IS NULL OR m.tipo = ?) AND (? OR e.tipo_evento <> 'tecla_liberada')
    ORDER BY e.fecha_hora, e.id
"""

# Filas de los reportes CSV. En la columna del periférico va la etiqueta de inventario o, si todavía no la tiene, `ID n`.
# Las columnas de cada consulta son las que lleva el generador de `reportes/` (el evento NO trae la tecla, RNF4).
SQL_FILAS_DE_EVENTOS = """
    SELECT e.id, e.id_sesion, COALESCE(p.etiqueta, 'ID ' || p.id), e.tipo_evento, e.fecha_hora, e.x, e.y
    FROM evento e
    JOIN periferico p ON p.id = e.id_periferico
    WHERE (? IS NULL OR e.fecha_hora >= ?) AND (? IS NULL OR e.fecha_hora < ?)
    ORDER BY e.fecha_hora, e.id
"""
SQL_FILAS_DE_TOTALES_DIARIOS = """
    SELECT c.fecha, COALESCE(p.etiqueta, 'ID ' || p.id), c.tipo_conteo, SUM(c.cantidad)
    FROM contador_diario c
    JOIN periferico p ON p.id = c.id_periferico
    WHERE (? IS NULL OR c.fecha >= ?) AND (? IS NULL OR c.fecha < ?)
    GROUP BY c.fecha, c.id_periferico, c.tipo_conteo
    ORDER BY c.fecha, 2, c.tipo_conteo
"""
SQL_FILAS_DE_CONTADORES = """
    SELECT c.fecha, COALESCE(p.etiqueta, 'ID ' || p.id), c.tipo_conteo, c.elemento, c.cantidad
    FROM contador_diario c
    JOIN periferico p ON p.id = c.id_periferico
    WHERE (? IS NULL OR c.fecha >= ?) AND (? IS NULL OR c.fecha < ?)
    ORDER BY c.fecha, 2, c.tipo_conteo, c.elemento
"""
SQL_FILAS_DE_ALERTAS = """
    SELECT COALESCE(p.etiqueta, 'ID ' || p.id), a.umbral, a.estado, a.intentos, a.fecha_creacion, a.fecha_envio
    FROM alerta a
    JOIN periferico p ON p.id = a.id_periferico
    WHERE (? IS NULL OR a.fecha_creacion >= ?) AND (? IS NULL OR a.fecha_creacion < ?)
    ORDER BY a.fecha_creacion, a.id
"""


class EtiquetaDuplicada(Exception):
    """La etiqueta de inventario ya pertenece a otro periférico."""


@dataclass(frozen=True, slots=True)
class EventoParaGuardar:
    """Un evento válido listo para la tabla `evento`. No tiene campo de tecla (RNF4)."""

    id_sesion: int
    id_periferico: int
    tipo_evento: str
    fecha_hora: str
    x: int | None = None
    y: int | None = None


@dataclass(frozen=True, slots=True)
class Conteo:
    """Cantidad que se suma a un contador diario. `elemento` es una tecla, un botón o la rueda."""

    id_periferico: int
    fecha: str  # AAAA-MM-DD
    tipo_conteo: str  # pulsacion_tecla, clic_boton o scroll_paso
    # repr=False: si alguien imprime el conteo por error, el nombre de la tecla no aparece (RNF4).
    elemento: str = field(repr=False)
    cantidad: int = 1


@dataclass(frozen=True, slots=True)
class UsoDeConteo:
    """Lo que lleva gastado un periférico en un tipo de conteo frente al límite de su modelo (RF16, RF17)."""

    tipo_conteo: str  # pulsacion_tecla, clic_boton o scroll_paso
    total: int  # suma de todos los días
    limite: int | None  # None si el modelo no tiene límite para este tipo (por ejemplo, un modelo "desconocido")

    @property
    def porcentaje(self) -> float | None:
        """Porcentaje de uso frente al límite (puede pasar de 100). None si no hay límite."""
        if self.limite is None:
            return None
        return self.total * 100 / self.limite


@dataclass(frozen=True, slots=True)
class ResumenPeriferico:
    """Un periférico con los datos de su modelo y su desgaste, listo para mostrarse. No trae nombres de teclas (RNF4)."""

    id: int
    id_equipo: int
    id_modelo: int
    etiqueta: str | None  # None hasta que Soporte TI la confirme (RF18)
    estado_asignacion: str  # confirmada o por_confirmar
    activo: bool  # False si el periférico fue retirado
    fecha_asignacion: str
    fecha_retiro: str | None
    fabricante: str
    modelo: str
    tipo: str  # teclado o mouse
    vid: str
    pid: str
    usos: tuple[UsoDeConteo, ...]  # un elemento por tipo de conteo que tenga límite o algún total

    @property
    def porcentaje_maximo(self) -> float | None:
        """El mayor porcentaje de uso entre sus conteos con límite: el que decide qué tan cerca está de agotarse."""
        porcentajes = [uso.porcentaje for uso in self.usos if uso.porcentaje is not None]
        return max(porcentajes) if porcentajes else None


@dataclass(frozen=True, slots=True)
class FilaSesion:
    """Una sesión del equipo (RF12)."""

    id: int
    id_equipo: int
    inicio: str
    fin: str | None  # None mientras la sesión está en curso
    tipo_cierre: str | None  # normal o inesperado; None mientras está en curso
    seg_actividad_teclado: int
    seg_actividad_mouse: int

    @property
    def en_curso(self) -> bool:
        """True si la sesión todavía no tiene fin."""
        return self.fin is None


@dataclass(frozen=True, slots=True)
class FilaIncidente:
    """Un incidente registrado (RF9, RF10). Su detalle nunca contiene teclas (RNF4)."""

    id: int
    id_sesion: int | None
    tipo: str
    fecha_hora: str
    detalle: str | None
    accion: str | None


@dataclass(frozen=True, slots=True)
class FilaAlerta:
    """Una alerta de desgaste con los datos de su periférico (RF19, RF20)."""

    id: int
    id_periferico: int
    etiqueta: str | None
    modelo: str
    umbral: int  # 90 o 100
    estado: str  # pendiente o enviada
    # repr=False: el detalle puede nombrar la tecla más gastada (por ejemplo "Q 91 %"); no debe salir en un log por error (RNF4).
    detalle: str | None = field(repr=False)
    fecha_creacion: str
    intentos: int
    fecha_ultimo_intento: str | None
    proximo_reintento: str | None
    ultimo_error: str | None
    fecha_envio: str | None


def ruta_por_defecto() -> Path:
    """Ruta de eventos.db: la variable CAPTURADOR_RUTA_DB si existe, y si no la carpeta de datos del sistema."""
    personalizada = os.environ.get(VARIABLE_DE_RUTA)
    if personalizada:
        return Path(personalizada)
    if sys.platform == "win32":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "CapturadorEventos" / "eventos.db"
    return Path.home() / ".capturador_eventos" / "eventos.db"


def _entero(valor: object) -> int:
    """Convierte un valor leído de la base en entero; falla si no lo es (por ejemplo, un NULL inesperado)."""
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    raise TypeError("la base de datos devolvió un valor que no es un entero")


def _filas_de_conteos(conteos: Iterable[Conteo]) -> list[tuple[object, ...]]:
    """Valida los conteos y los convierte en filas para la base."""
    filas: list[tuple[object, ...]] = []
    for conteo in conteos:
        if conteo.cantidad <= 0:
            raise ValueError("la cantidad a sumar debe ser mayor que cero")
        filas.append((conteo.id_periferico, conteo.fecha, conteo.tipo_conteo, conteo.elemento, conteo.cantidad))
    return filas


def _texto_o_none(valor: object) -> str | None:
    """Convierte un valor leído de la base en texto, dejando el NULL como None."""
    return None if valor is None else str(valor)


def _entero_o_none(valor: object) -> int | None:
    """Convierte un valor leído de la base en entero, dejando el NULL como None."""
    return None if valor is None else _entero(valor)


def _rango(desde: str | None, hasta: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    """Valida un rango de fechas y lo deja listo para el patrón `(? IS NULL OR campo >= ?)` de los SQL de lectura.

    Cada extremo es None (sin límite) o una fecha ISO 8601, con o sin hora. Lanza ValueError si no lo es: sin esta
    revisión, un texto como "hoy" se compararía como texto y devolvería una lista vacía sin avisar.
    """
    for fecha in (desde, hasta):
        if fecha is None:
            continue
        try:
            _ = datetime.fromisoformat(fecha)
        except ValueError as error:
            raise ValueError("la fecha debe ser ISO 8601: AAAA-MM-DD o con hora") from error
    return desde, desde, hasta, hasta


class Repositorio:
    """Una conexión a eventos.db con todas las operaciones que necesitan el servicio y la interfaz."""

    def __init__(self, ruta: Path | str | None = None, ruta_esquema: Path | None = None) -> None:
        """Abre la base y, si es la primera vez, la crea a partir de schema.sql.

        ruta: archivo de la base; por defecto `ruta_por_defecto()`.
        ruta_esquema: schema.sql; por defecto el del repositorio del proyecto.
        """
        destino = Path(ruta) if ruta is not None else ruta_por_defecto()
        destino.parent.mkdir(parents=True, exist_ok=True)

        # check_same_thread=False porque el servicio escribe desde varios hilos; el candado los ordena.
        self._candado: threading.Lock = threading.Lock()
        self._conexion: sqlite3.Connection = sqlite3.connect(
            destino, check_same_thread=False, timeout=ESPERA_DE_BLOQUEO_MS / 1000
        )
        self._preparar_conexion()
        self._crear_esquema_si_falta(ruta_esquema or RUTA_ESQUEMA_POR_DEFECTO)

    # ---------- Ciclo de vida ----------

    def cerrar(self) -> None:
        """Cierra la conexión. Después de esto el repositorio ya no se puede usar."""
        with self._candado:
            self._conexion.close()

    def __enter__(self) -> Self:
        """Permite `with Repositorio(...) as repo:` para que la conexión se cierre sola."""
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        valor: BaseException | None,
        traza: TracebackType | None,
    ) -> None:
        """Cierra la conexión al salir del `with`, haya o no un error; no oculta el error."""
        self.cerrar()

    def _preparar_conexion(self) -> None:
        """Ejecuta los tres PRAGMA de esta conexión (decisión de arquitectura 4).

        WAL deja que la interfaz lea mientras el servicio escribe; `foreign_keys` hace que SQLite rechace
        una llave foránea que no existe; `busy_timeout` espera en vez de fallar si el otro proceso tiene
        el bloqueo de escritura. Los valores salen de docs/base-de-datos/schema.sql y de su README.
        """
        # Los PRAGMA van en CADA conexión: solo journal_mode se queda guardado en el archivo.
        _ = self._conexion.execute("PRAGMA journal_mode = WAL").fetchall()
        _ = self._conexion.execute("PRAGMA foreign_keys = ON")
        _ = self._conexion.execute(f"PRAGMA busy_timeout = {ESPERA_DE_BLOQUEO_MS}")

    def _crear_esquema_si_falta(self, ruta_esquema: Path) -> None:
        """Crea las tablas ejecutando `ruta_esquema` solo si la base todavía no tiene la tabla `equipo`.

        Lanza FileNotFoundError si hace falta crear la base y el archivo del esquema no existe.
        """
        if self._uno("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'equipo'") is not None:
            return
        if not ruta_esquema.is_file():
            raise FileNotFoundError(f"No se encontró el esquema de la base de datos: {ruta_esquema}")
        # El esquema usa IF NOT EXISTS e INSERT OR IGNORE: si dos procesos lo ejecutan a la vez, no pasa nada.
        _ = self._conexion.executescript(ruta_esquema.read_text(encoding="utf-8"))

    # ---------- Ayudas internas (se llaman con el candado ya tomado, o durante la creación) ----------

    def _uno(self, sql: str, parametros: tuple[object, ...] = ()) -> Fila | None:
        """Ejecuta una consulta y devuelve su primera fila, o None si no hay ninguna."""
        # `cast` solo ayuda al revisor de tipos: sqlite3 declara `Any` y aquí sabemos que es una tupla.
        return cast(Fila | None, self._conexion.execute(sql, parametros).fetchone())

    def _todas(self, sql: str, parametros: tuple[object, ...] = ()) -> list[Fila]:
        """Ejecuta una consulta y devuelve todas sus filas (lista vacía si no hay ninguna)."""
        return cast(list[Fila], self._conexion.execute(sql, parametros).fetchall())

    def _insertar(self, sql: str, parametros: tuple[object, ...]) -> int:
        """Ejecuta un INSERT y devuelve el id de la fila nueva. Lanza RuntimeError si SQLite no lo da."""
        identificador = self._conexion.execute(sql, parametros).lastrowid
        if identificador is None:
            raise RuntimeError("SQLite no devolvió el identificador de la fila nueva")
        return identificador

    # ---------- Equipos ----------

    def obtener_o_crear_equipo(self, nombre: str) -> int:
        """Devuelve el id del equipo con ese nombre (por ejemplo PC-CONTAB-014), creándolo si no existe (RF18)."""
        with self._candado, self._conexion:
            fila = self._uno("SELECT id FROM equipo WHERE nombre = ?", (nombre,))
            if fila is not None:
                return _entero(fila[0])
            return self._insertar("INSERT INTO equipo (nombre) VALUES (?)", (nombre,))

    # ---------- Modelos y periféricos ----------

    def obtener_o_crear_modelo(self, vid: str, pid: str, tipo: str) -> int:
        """Devuelve el id del modelo con ese VID/PID (RF17).

        Si no está en el catálogo, lo crea con el nombre "desconocido" y sin límites de vida útil:
        Soporte TI lo completa después. `tipo` es "teclado" o "mouse".
        """
        with self._candado, self._conexion:
            fila = self._uno("SELECT id FROM modelo_periferico WHERE vid = ? AND pid = ?", (vid, pid))
            if fila is not None:
                return _entero(fila[0])
            return self._insertar(
                "INSERT INTO modelo_periferico (fabricante, nombre, tipo, vid, pid) VALUES (?, ?, ?, ?, ?)",
                (NOMBRE_DESCONOCIDO, NOMBRE_DESCONOCIDO, tipo, vid, pid),
            )

    def obtener_o_crear_periferico(self, id_equipo: int, id_modelo: int, fecha_asignacion: str) -> tuple[int, bool]:
        """Devuelve (id del periférico, si se acaba de crear) para ese equipo y modelo (RF18).

        Un periférico nuevo queda "por_confirmar" y sin etiqueta hasta que Soporte TI la confirme.
        Dos unidades idénticas en el mismo equipo comparten VID/PID y se tratan como una sola.
        """
        with self._candado, self._conexion:
            fila = self._uno(
                "SELECT id FROM periferico WHERE id_equipo = ? AND id_modelo = ? AND activo = 1 ORDER BY id LIMIT 1",
                (id_equipo, id_modelo),
            )
            if fila is not None:
                return _entero(fila[0]), False
            identificador = self._insertar(SQL_INSERTAR_PERIFERICO, (id_modelo, id_equipo, fecha_asignacion))
            return identificador, True

    def asignar_etiqueta(self, id_periferico: int, etiqueta: str) -> None:
        """Asocia la etiqueta de inventario (por ejemplo TEC-0042) y confirma la asignación (RF18).

        Lanza EtiquetaDuplicada si otro periférico ya la tiene, y LookupError si el periférico no existe.
        """
        limpia = etiqueta.strip()
        if not limpia:
            raise ValueError("la etiqueta no puede estar vacía")
        with self._candado:
            # El `try` va FUERA de `with self._conexion` para que la transacción ya se haya deshecho cuando
            # llega el IntegrityError (índice único de `periferico.etiqueta`); entonces se traduce a un error propio.
            try:
                with self._conexion:
                    cursor = self._conexion.execute(
                        "UPDATE periferico SET etiqueta = ?, estado_asignacion = 'confirmada' WHERE id = ?",
                        (limpia, id_periferico),
                    )
            except sqlite3.IntegrityError as error:
                raise EtiquetaDuplicada(f"la etiqueta {limpia} ya está asignada a otro periférico") from error
            if cursor.rowcount == 0:
                raise LookupError(f"no existe el periférico {id_periferico}")

    # ---------- Sesiones ----------

    def abrir_sesion(self, id_equipo: int, inicio: str) -> int:
        """Abre una sesión: desde que el servicio inicia hasta que el equipo se apaga (RF12)."""
        with self._candado, self._conexion:
            return self._insertar("INSERT INTO sesion (id_equipo, inicio) VALUES (?, ?)", (id_equipo, inicio))

    def actualizar_actividad_sesion(self, id_sesion: int, seg_teclado: int, seg_mouse: int) -> None:
        """Guarda los segundos de actividad acumulados, para no perderlos si el equipo se apaga de golpe."""
        with self._candado, self._conexion:
            _ = self._conexion.execute(SQL_ACTUALIZAR_ACTIVIDAD, (seg_teclado, seg_mouse, id_sesion))

    def cerrar_sesion(self, id_sesion: int, fin: str, tipo_cierre: str, seg_teclado: int, seg_mouse: int) -> None:
        """Cierra una sesión. `tipo_cierre` es "normal" o "inesperado"."""
        with self._candado, self._conexion:
            _ = self._conexion.execute(SQL_CERRAR_SESION, (fin, tipo_cierre, seg_teclado, seg_mouse, id_sesion))

    def cerrar_sesiones_abiertas_como_inesperadas(self) -> int:
        """Cierra como "inesperado" toda sesión que quedó abierta y devuelve cuántas eran (RNF12).

        Se llama una sola vez, cuando el servicio arranca: una sesión abierta es de un apagado brusco.
        No debe llamarla la interfaz, porque podría cerrar la sesión del servicio que sigue en marcha.
        Como fecha de fin se usa el último evento de la sesión, o su inicio si no tuvo ninguno, para no
        inventar tiempo de actividad. Cada cierre deja un incidente `apagado_inesperado`.
        """
        with self._candado, self._conexion:
            abiertas = self._todas(SQL_SESIONES_ABIERTAS)
            for fila in abiertas:
                id_sesion, fin = _entero(fila[0]), str(fila[1])
                _ = self._conexion.execute(
                    "UPDATE sesion SET fin = ?, tipo_cierre = 'inesperado' WHERE id = ?", (fin, id_sesion)
                )
                _ = self._conexion.execute(
                    SQL_INCIDENTE_DE_APAGADO,
                    (id_sesion, fin, "la sesión quedó abierta (apagado brusco o caída del servicio)",
                     "sesión cerrada al iniciar el servicio"),
                )
            return len(abiertas)

    # ---------- Eventos e incidentes ----------

    def guardar_evento(
        self, id_sesion: int, id_periferico: int, tipo_evento: str, fecha_hora: str,
        x: int | None = None, y: int | None = None,
    ) -> None:
        """Guarda un evento válido (RF8, RF13). No recibe la tecla: nunca se guarda (RNF4)."""
        with self._candado, self._conexion:
            _ = self._conexion.execute(SQL_INSERTAR_EVENTO, (id_sesion, id_periferico, tipo_evento, fecha_hora, x, y))

    def guardar_eventos(self, eventos: Iterable[EventoParaGuardar]) -> None:
        """Guarda varios eventos en una sola transacción: o entran todos o no entra ninguno."""
        filas = [(e.id_sesion, e.id_periferico, e.tipo_evento, e.fecha_hora, e.x, e.y) for e in eventos]
        with self._candado, self._conexion:
            _ = self._conexion.executemany(SQL_INSERTAR_EVENTO, filas)

    def guardar_incidente(
        self, tipo: str, fecha_hora: str, detalle: str | None = None, accion: str | None = None,
        id_sesion: int | None = None,
    ) -> None:
        """Guarda un incidente (RF9, RF10). Su detalle nunca debe contener teclas (RNF4)."""
        with self._candado, self._conexion:
            _ = self._conexion.execute(SQL_INSERTAR_INCIDENTE, (id_sesion, tipo, fecha_hora, detalle, accion))

    # ---------- Contadores de desgaste ----------

    def sumar_a_contadores(self, conteos: Iterable[Conteo]) -> None:
        """Suma cantidades a los contadores diarios en una sola transacción (RF16).

        Si el contador del día no existe, lo crea. Sirve para el guardado de cada minuto (RNF12).
        """
        filas = _filas_de_conteos(conteos)
        with self._candado, self._conexion:
            _ = self._conexion.executemany(SQL_SUMAR_A_CONTADOR, filas)

    def guardar_lote(
        self, id_sesion: int, eventos: Iterable[EventoParaGuardar], conteos: Iterable[Conteo],
        seg_teclado: int, seg_mouse: int,
    ) -> None:
        """Guarda de una vez eventos, contadores y actividad de la sesión, en una sola transacción (RNF12).

        Si algo falla no se guarda nada, así quien llama puede reintentar el lote completo sin duplicar datos.
        """
        filas_eventos = [(e.id_sesion, e.id_periferico, e.tipo_evento, e.fecha_hora, e.x, e.y) for e in eventos]
        filas_conteos = _filas_de_conteos(conteos)
        with self._candado, self._conexion:
            _ = self._conexion.executemany(SQL_INSERTAR_EVENTO, filas_eventos)
            _ = self._conexion.executemany(SQL_SUMAR_A_CONTADOR, filas_conteos)
            _ = self._conexion.execute(SQL_ACTUALIZAR_ACTIVIDAD, (seg_teclado, seg_mouse, id_sesion))

    def total_acumulado(self, id_periferico: int, tipo_conteo: str, elemento: str | None = None) -> int:
        """Suma de todos los días de un contador. Sin `elemento`, suma todos (por ejemplo, todo el teclado)."""
        with self._candado:
            if elemento is None:
                fila = self._uno(
                    "SELECT COALESCE(SUM(cantidad), 0) FROM contador_diario WHERE id_periferico = ? AND tipo_conteo = ?",
                    (id_periferico, tipo_conteo),
                )
            else:
                fila = self._uno(SQL_TOTAL_DE_UN_ELEMENTO, (id_periferico, tipo_conteo, elemento))
        return _entero(fila[0]) if fila is not None else 0

    def totales_por_elemento(self, id_periferico: int, tipo_conteo: str) -> dict[str, int]:
        """Total acumulado de cada tecla, botón o rueda. Con esto se calcula el porcentaje de uso (RF19)."""
        with self._candado:
            filas = self._todas(SQL_TOTALES_POR_ELEMENTO, (id_periferico, tipo_conteo))
        return {str(fila[0]): _entero(fila[1]) for fila in filas}

    # ---------- Configuración ----------

    def leer_configuracion(self, clave: str) -> str | None:
        """Devuelve el valor de un ajuste, o None si la clave no existe.

        El servicio la llama cada cierto tiempo para ver la orden de iniciar o detener que dejó la
        interfaz: los dos procesos se comunican solo por esta tabla (decisión de arquitectura 1).
        """
        with self._candado:
            fila = self._uno("SELECT valor FROM configuracion WHERE clave = ?", (clave,))
        return str(fila[0]) if fila is not None else None

    def escribir_configuracion(self, clave: str, valor: str) -> None:
        """Guarda un ajuste. Nunca guarda contraseñas: esas van en keyring (RNF10)."""
        with self._candado, self._conexion:
            _ = self._conexion.execute(SQL_ESCRIBIR_CONFIGURACION, (clave, valor))

    # ---------- Lecturas: periféricos y límites ----------

    def listar_perifericos(self, id_equipo: int | None = None, incluir_retirados: bool = True) -> list[ResumenPeriferico]:
        """Los periféricos con su modelo, su desgaste y su porcentaje de uso (RF16, RF17, RF18).

        id_equipo: solo los de ese equipo; None para todos (cada base de datos es de una sola PC).
        incluir_retirados: si es False, oculta los periféricos con `activo = 0`.
        Salen primero los activos y, dentro de cada grupo, por orden de creación.
        """
        with self._candado:
            filas = self._todas(SQL_LISTAR_PERIFERICOS, (id_equipo, id_equipo, int(incluir_retirados)))
            return [self._resumen_de(fila) for fila in filas]

    def obtener_periferico(self, id_periferico: int) -> ResumenPeriferico | None:
        """El detalle de un periférico, o None si no existe."""
        with self._candado:
            fila = self._uno(SQL_UN_PERIFERICO, (id_periferico,))
            return self._resumen_de(fila) if fila is not None else None

    def _resumen_de(self, fila: Fila) -> ResumenPeriferico:
        """Arma el `ResumenPeriferico` de una fila de SQL_PERIFERICOS, juntando sus límites y sus totales.

        Se llama con el candado ya tomado. Hace dos consultas por periférico; son pocos por equipo y así
        cada consulta queda simple. Los tipos de conteo salen de la unión de los que tienen límite y los que
        ya tienen algún total, para que un modelo "desconocido" (sin límites) igual muestre su desgaste.
        """
        id_periferico = _entero(fila[0])
        limites = {str(f[0]): _entero(f[1]) for f in self._todas(SQL_LIMITES_DE_UN_MODELO, (_entero(fila[2]),))}
        totales = {str(f[0]): _entero(f[1]) for f in self._todas(SQL_TOTALES_POR_TIPO, (id_periferico,))}
        usos = tuple(
            UsoDeConteo(tipo, totales.get(tipo, 0), limites.get(tipo)) for tipo in sorted(limites.keys() | totales.keys())
        )
        return ResumenPeriferico(
            id=id_periferico, id_equipo=_entero(fila[1]), id_modelo=_entero(fila[2]), etiqueta=_texto_o_none(fila[3]),
            estado_asignacion=str(fila[4]), activo=bool(_entero(fila[5])), fecha_asignacion=str(fila[6]),
            fecha_retiro=_texto_o_none(fila[7]), fabricante=str(fila[8]), modelo=str(fila[9]), tipo=str(fila[10]),
            vid=str(fila[11]), pid=str(fila[12]), usos=usos,
        )

    def limites_del_periferico(self, id_periferico: int) -> dict[str, int]:
        """Los límites de vida útil de su modelo, por tipo de conteo (RF17). Vacío si el modelo no tiene o no existe."""
        with self._candado:
            return {str(f[0]): _entero(f[1]) for f in self._todas(SQL_LIMITES_DE_UN_PERIFERICO, (id_periferico,))}

    # ---------- Lecturas: sesiones e incidentes ----------

    def listar_sesiones(self, id_equipo: int | None = None, dia: str | None = None) -> list[FilaSesion]:
        """Las sesiones, de la más reciente a la más antigua (RF12).

        dia: `AAAA-MM-DD`; solo las sesiones que empezaron ese día. Lanza ValueError si no es una fecha válida.
        """
        desde, hasta = (None, None) if dia is None else self._limites_del_dia(dia)
        with self._candado:
            filas = self._todas(SQL_LISTAR_SESIONES, (id_equipo, id_equipo, desde, desde, hasta, hasta))
        return [
            FilaSesion(
                id=_entero(f[0]), id_equipo=_entero(f[1]), inicio=str(f[2]), fin=_texto_o_none(f[3]),
                tipo_cierre=_texto_o_none(f[4]), seg_actividad_teclado=_entero(f[5]), seg_actividad_mouse=_entero(f[6]),
            )
            for f in filas
        ]

    def actividad_del_dia(self, dia: str, id_equipo: int | None = None) -> tuple[int, int]:
        """(segundos de teclado, segundos de mouse): la suma de las sesiones que empezaron ese día (RF12).

        Lanza ValueError si `dia` no es una fecha `AAAA-MM-DD` válida.
        """
        desde, hasta = self._limites_del_dia(dia)
        with self._candado:
            fila = self._uno(SQL_ACTIVIDAD_DE_SESIONES, (id_equipo, id_equipo, desde, hasta))
        return (_entero(fila[0]), _entero(fila[1])) if fila is not None else (0, 0)

    @staticmethod
    def _limites_del_dia(dia: str) -> tuple[str, str]:
        """El día y el siguiente, como texto, para filtrar `inicio >= día AND inicio < día siguiente`."""
        try:
            fecha = date.fromisoformat(dia)
        except ValueError as error:
            raise ValueError("el día debe ser una fecha AAAA-MM-DD") from error
        return fecha.isoformat(), (fecha + timedelta(days=1)).isoformat()

    def incidentes_recientes(self, limite: int = 50) -> list[FilaIncidente]:
        """Los últimos `limite` incidentes, del más reciente al más antiguo (RF9, RF10). Lanza ValueError si `limite` < 1."""
        if limite < 1:
            raise ValueError("el límite debe ser al menos 1")
        with self._candado:
            filas = self._todas(SQL_INCIDENTES_RECIENTES, (limite,))
        return [
            FilaIncidente(
                id=_entero(f[0]), id_sesion=_entero_o_none(f[1]), tipo=str(f[2]), fecha_hora=str(f[3]),
                detalle=_texto_o_none(f[4]), accion=_texto_o_none(f[5]),
            )
            for f in filas
        ]

    # ---------- Alertas ----------

    def crear_alerta(self, id_periferico: int, umbral: int, fecha_creacion: str, detalle: str | None = None) -> bool:
        """Crea una alerta `pendiente` y devuelve True; si ya existía una para ese periférico y umbral, no hace nada y devuelve False.

        Es segura de repetir: el evaluador puede llamarla cada minuto, o después de un reinicio, sin duplicar (RF19, RNF12).
        `umbral` debe ser 90 o 100; otro valor, o un periférico que no existe, lanza sqlite3.IntegrityError.
        """
        with self._candado, self._conexion:
            cursor = self._conexion.execute(SQL_CREAR_ALERTA, (id_periferico, umbral, fecha_creacion, detalle))
            return cursor.rowcount == 1

    def listar_alertas(self, estado: str | None = None) -> list[FilaAlerta]:
        """Las alertas, de la más reciente a la más antigua. `estado`: "pendiente", "enviada" o None para todas (RF19, RF20)."""
        return self._leer_alertas(SQL_ALERTAS_RECIENTES, estado)

    def alertas_pendientes(self) -> list[FilaAlerta]:
        """Las alertas sin enviar, de la más antigua a la más reciente: el orden en que el notificador debe enviarlas (RF20)."""
        return self._leer_alertas(SQL_ALERTAS_ANTIGUAS, "pendiente")

    def _leer_alertas(self, sql: str, estado: str | None) -> list[FilaAlerta]:
        """Ejecuta una de las consultas de alertas y convierte las filas. Lanza ValueError si `estado` no es válido."""
        if estado not in (None, "pendiente", "enviada"):
            raise ValueError('el estado debe ser "pendiente", "enviada" o None')
        with self._candado:
            filas = self._todas(sql, (estado, estado))
        return [
            FilaAlerta(
                id=_entero(f[0]), id_periferico=_entero(f[1]), etiqueta=_texto_o_none(f[2]), modelo=str(f[3]),
                umbral=_entero(f[4]), estado=str(f[5]), detalle=_texto_o_none(f[6]), fecha_creacion=str(f[7]),
                intentos=_entero(f[8]), fecha_ultimo_intento=_texto_o_none(f[9]), proximo_reintento=_texto_o_none(f[10]),
                ultimo_error=_texto_o_none(f[11]), fecha_envio=_texto_o_none(f[12]),
            )
            for f in filas
        ]

    def registrar_intento_de_alerta(
        self, id_alerta: int, fecha_intento: str, proximo_reintento: str | None, error: str | None,
    ) -> None:
        """Anota un intento de envío que falló: suma uno a los intentos y guarda cuándo y por qué (RF20).

        proximo_reintento: cuándo debe volver a intentarse (None si ya no se reintentará en esta sesión).
        error: el motivo, sin contraseñas ni direcciones de correo (RNF10). Lanza LookupError si la alerta no existe o ya se envió.
        """
        with self._candado, self._conexion:
            cursor = self._conexion.execute(SQL_REGISTRAR_INTENTO, (fecha_intento, proximo_reintento, error, id_alerta))
            if cursor.rowcount == 0:
                raise LookupError(f"no existe la alerta pendiente {id_alerta}")

    def marcar_alerta_enviada(self, id_alerta: int, fecha_envio: str) -> None:
        """Marca la alerta como enviada. El envío exitoso cuenta como un intento y ya no tiene próximo reintento (RF20).

        Se conserva `ultimo_error` como historial de los intentos anteriores. Lanza LookupError si la alerta no existe o ya
        estaba enviada, para que un envío doble no pase inadvertido.
        """
        with self._candado, self._conexion:
            cursor = self._conexion.execute(SQL_MARCAR_ENVIADA, (fecha_envio, fecha_envio, id_alerta))
            if cursor.rowcount == 0:
                raise LookupError(f"no existe la alerta pendiente {id_alerta}")

    # ---------- Lecturas para el análisis y los reportes ----------

    def horas_de_eventos(
        self, desde: str | None = None, hasta: str | None = None, tipo_dispositivo: str | None = None,
        incluir_liberaciones: bool = False,
    ) -> list[str]:
        """Las fechas y horas de los eventos, ordenadas: la entrada del mapa de calor y de los patrones (RF15, RF22).

        desde, hasta: rango semiabierto (ver el docstring del módulo); None es sin límite.
        tipo_dispositivo: "teclado", "mouse" o None para los dos.
        incluir_liberaciones: por defecto se omiten las teclas liberadas (ver SQL_HORAS_DE_EVENTOS).
        Lanza ValueError si una fecha no es ISO 8601. Para rangos muy largos conviene pedir por semanas.
        """
        parametros = (*_rango(desde, hasta), tipo_dispositivo, tipo_dispositivo, int(incluir_liberaciones))
        with self._candado:
            return [str(f[0]) for f in self._todas(SQL_HORAS_DE_EVENTOS, parametros)]

    def filas_de_eventos(self, desde: str | None = None, hasta: str | None = None) -> list[Fila]:
        """Filas del reporte de eventos (RF14): id, id de sesión, periférico, tipo de evento, fecha y hora, x, y.

        El periférico es su etiqueta de inventario o `ID n` si aún no la tiene. No hay columna de tecla (RNF4).
        """
        with self._candado:
            return self._todas(SQL_FILAS_DE_EVENTOS, _rango(desde, hasta))

    def filas_de_totales_diarios(self, desde: str | None = None, hasta: str | None = None) -> list[Fila]:
        """Filas del reporte de totales diarios (RF14): fecha, periférico, tipo de conteo, total del día."""
        with self._candado:
            return self._todas(SQL_FILAS_DE_TOTALES_DIARIOS, _rango(desde, hasta))

    def filas_de_contadores(self, desde: str | None = None, hasta: str | None = None) -> list[Fila]:
        """Filas del reporte de contadores (RF14): fecha, periférico, tipo de conteo, elemento y cantidad.

        El elemento es una tecla, un botón o la rueda, ya agregado por día (RF16): es el único lugar donde sale el nombre de una tecla.
        """
        with self._candado:
            return self._todas(SQL_FILAS_DE_CONTADORES, _rango(desde, hasta))

    def filas_de_alertas(self, desde: str | None = None, hasta: str | None = None) -> list[Fila]:
        """Filas del reporte de alertas (RF14): periférico, umbral, estado, intentos, fecha de creación y de envío.

        El rango se aplica a la fecha de creación de la alerta.
        """
        with self._candado:
            return self._todas(SQL_FILAS_DE_ALERTAS, _rango(desde, hasta))
