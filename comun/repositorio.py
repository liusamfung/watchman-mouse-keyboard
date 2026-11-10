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

Se relaciona con: usa `docs/base-de-datos/schema.sql` (tablas, restricciones y PRAGMA) y la variable de
entorno CAPTURADOR_RUTA_DB · lo usan `servicio/guardador.py`, `servicio/sesion.py`, `servicio/contador.py`
(a través de `Conteo` y `EventoParaGuardar`), la futura interfaz `ui/` y las pruebas de `pruebas/`.
"""
import os
import sqlite3
import sys
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
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
