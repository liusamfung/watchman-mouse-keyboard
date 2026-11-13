"""Generador de una base de datos de ejemplo, para desarrollar sin Windows, sin capturador y sin un teclado real.

Uso (desde la carpeta raíz del repositorio):
    python -m pruebas.base_de_ejemplo ruta/ejemplo.db
    python -m pruebas.base_de_ejemplo ruta/ejemplo.db --hasta 2026-11-12 --dias 21 --semilla 1

Qué crea: un equipo (PC-EJEMPLO-01) con cuatro periféricos y varias semanas de uso. Sirve para programar y probar las
pantallas, los reportes y el análisis con datos que se parecen a los reales:
- TEC-0007: un teclado K120 retirado, que llegó al 100 % del límite (alertas del 90 % y del 100 % ya enviadas).
- Un teclado K120 por confirmar (sin etiqueta) al 92 %, con una alerta del 90 % pendiente: falló el envío dos veces.
- MOU-0108: un mouse B100 confirmado, con el 55 % de los clics y el 30 % de la rueda.
- Un mouse de modelo desconocido, por confirmar y sin límites (para probar ese caso).
Además: sesiones normales e inesperadas (la última, en curso), incidentes de todos los tipos y eventos repartidos por
día y hora (para que el mapa de calor se vea). El límite es por tecla o por botón, así que cada periférico tiene una tecla
(o botón) que marca su porcentaje y las demás llevan menos.

Cómo funciona: toda la base sale de una semilla (`random.Random`), así que la misma semilla, la misma fecha final y el
mismo número de días dan exactamente la misma base. Se planean primero las sesiones (qué días se trabajó), luego se reparte
el desgaste solo entre esos días y por último se escriben eventos, alertas e incidentes con las operaciones de `Repositorio`.
Los eventos son una MUESTRA reducida; los contadores son los que reflejan el desgaste real (en una PC de verdad hay
miles de eventos por día).

Seguridad: no sobrescribe cualquier archivo. Una base creada por este programa lleva la clave `base_de_ejemplo` en la tabla
`configuracion`; solo si el archivo la tiene se borra y se vuelve a crear. Cualquier otro archivo (por ejemplo, la base
real) se deja intacto y se avisa con `BaseExistente`.

Privacidad (RNF4, RNF10): nada viene de una persona. Los nombres de teclas y sus cantidades salen de los pesos fijos de
este archivo, los correos usan el dominio `.invalid` (reservado: no existe) y no hay ninguna contraseña.

Se relaciona con: usa `comun/repositorio.py` (todas las escrituras) · lo prueba `pruebas/test_base_de_ejemplo.py` y lo usan,
a mano, quienes programan `ui/`, `reportes/` y `analisis/`.
"""
import argparse
import random
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import cast

from comun.repositorio import Conteo, EventoParaGuardar, Repositorio

MARCA = "base_de_ejemplo"  # clave de `configuracion` que identifica una base creada por este programa
NOMBRE_EQUIPO = "PC-EJEMPLO-01"
DIAS_MINIMOS = 10  # con menos días no alcanza para tener un periférico retirado y otro actual

# Cuánto pesa cada tecla, botón y la rueda en el desgaste. La tecla (o botón) de mayor peso es la que marca el porcentaje.
TECLAS_PESOS: dict[str, int] = {
    "ESPACIO": 10, "E": 9, "A": 8, "O": 8, "S": 7, "N": 6, "R": 6, "I": 6, "ENTER": 5, "L": 5, "D": 5, "T": 5,
    "RETROCESO": 4, "C": 4, "U": 4, "M": 3, "P": 3, "SHIFT": 3, "TAB": 2, "F5": 1,
}
BOTONES_PESOS: dict[str, int] = {"izquierdo": 10, "derecho": 2}
RUEDA_PESOS: dict[str, int] = {"rueda": 1}

# Cuántas "acciones" hay en cada hora del día (más en la mañana y en la tarde) y qué tanto se trabaja cada día de la semana.
PESO_POR_HORA: dict[int, int] = {8: 2, 9: 5, 10: 8, 11: 9, 12: 3, 13: 2, 14: 6, 15: 9, 16: 8, 17: 4, 18: 1}
FACTOR_POR_DIA_SEMANA: tuple[float, ...] = (1.0, 1.2, 1.1, 1.0, 0.7, 0.2, 0.0)  # lunes … domingo
ACCIONES_POR_PESO = 6  # acciones por cada punto de PESO_POR_HORA, en un día con factor 1.0
HORA_ACTUAL_DE_LA_SESION_EN_CURSO = time(11, 30)

CORREO_DE_EJEMPLO = "soporte.ti@ejemplo.invalid"  # `.invalid` está reservado: ningún buzón real lo usa
REMITENTE_DE_EJEMPLO = "alertas@ejemplo.invalid"


class BaseExistente(Exception):
    """El archivo de destino ya existe y no es una base de ejemplo creada por este programa: no se toca."""


@dataclass(frozen=True, slots=True)
class ResumenDeEjemplo:
    """Cuánto se creó. Sirve para mostrar un resumen y para las pruebas."""

    perifericos: int
    sesiones: int
    eventos: int
    alertas: int
    incidentes: int


@dataclass(frozen=True, slots=True)
class SesionPlaneada:
    """Una sesión que se va a crear. `fin` es None en la sesión en curso, que es la del último día."""

    dia: date
    inicio: datetime
    fin: datetime | None
    tipo_cierre: str | None  # normal o inesperado; None si está en curso


@dataclass(frozen=True, slots=True)
class ObjetivoDeConteo:
    """Cuánto desgaste debe alcanzar un periférico en un tipo de conteo y con qué elementos."""

    tipo_conteo: str
    pesos: dict[str, int]
    mayor_uso: int  # lo que debe llevar el elemento de mayor peso al final


@dataclass(slots=True)
class PerifericoDeEjemplo:
    """Un periférico creado, los días en que se usó y el desgaste que se le repartió por día."""

    id: int
    dias: list[date]
    por_dia: dict[tuple[str, str], list[int]]  # (tipo de conteo, elemento) -> cantidad de cada día de `dias`


def _es_de_ejemplo(ruta: Path) -> bool:
    """True si el archivo es una base SQLite con la marca de este programa. Solo la lee: no la modifica."""
    try:
        conexion = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        fila = cast(
            tuple[object, ...] | None,
            conexion.execute("SELECT valor FROM configuracion WHERE clave = ?", (MARCA,)).fetchone(),
        )
        return fila is not None
    except sqlite3.Error:  # no es una base, o no tiene la tabla `configuracion`
        return False
    finally:
        conexion.close()


def _borrar(ruta: Path) -> None:
    """Borra la base y sus archivos auxiliares de WAL (`-wal` y `-shm`)."""
    for sufijo in ("", "-wal", "-shm"):
        Path(f"{ruta}{sufijo}").unlink(missing_ok=True)


def _iso(momento: datetime, milisegundos: bool = False) -> str:
    """Fecha y hora como las guarda el repositorio: `2026-11-02T08:15:30`, o con milisegundos en los eventos."""
    return momento.isoformat(timespec="milliseconds" if milisegundos else "seconds")


def _mas_segundos(texto: str, segundos: int) -> str:
    """Suma segundos a una fecha y hora ISO 8601 y la devuelve en el mismo formato."""
    return _iso(datetime.fromisoformat(texto) + timedelta(seconds=segundos))


def _planear_sesiones(calendario: Sequence[date], azar: random.Random) -> list[SesionPlaneada]:
    """Decide qué días hubo sesión y a qué hora empezó y terminó cada una. No toca la base de datos.

    Lunes a viernes hay una sesión, y con un 15 % de probabilidad dos (el equipo se reinició a mediodía); el sábado casi
    nunca; el domingo nunca. Una sesión de cada diez termina de forma inesperada, y hay al menos una a partir del primer
    tercio del periodo. La del último día queda en curso.
    """
    sesiones: list[SesionPlaneada] = []
    primer_dia_inesperado = len(calendario) // 3
    falta_una_inesperada = True
    for posicion, dia in enumerate(calendario):
        es_ultimo = posicion == len(calendario) - 1
        dia_semana = dia.weekday()
        if not es_ultimo and (dia_semana == 6 or (dia_semana == 5 and azar.random() > 0.3)):
            continue
        inicio = datetime.combine(dia, time(8, 0)) + timedelta(minutes=azar.randint(0, 40))
        if es_ultimo:
            sesiones.append(SesionPlaneada(dia, inicio, None, None))
            continue
        if dia_semana < 5:
            fin = datetime.combine(dia, time(17, 30)) + timedelta(minutes=azar.randint(0, 60))
        else:
            fin = inicio + timedelta(hours=3)
        forzada = falta_una_inesperada and posicion >= primer_dia_inesperado and dia_semana < 5
        tipo_final = "inesperado" if forzada or azar.random() < 0.10 else "normal"
        falta_una_inesperada = falta_una_inesperada and not forzada
        if dia_semana < 5 and azar.random() < 0.15:
            mediodia = datetime.combine(dia, time(13, 0))
            sesiones.append(SesionPlaneada(dia, inicio, mediodia, "normal"))
            sesiones.append(SesionPlaneada(dia, datetime.combine(dia, time(14, 0)), fin, tipo_final))
        else:
            sesiones.append(SesionPlaneada(dia, inicio, fin, tipo_final))
    return sesiones


def _repartir(total: int, dias: Sequence[date], azar: random.Random) -> list[int]:
    """Reparte `total` entre los días con pesos al azar (menos los sábados). La suma es exactamente `total`."""
    pesos = [azar.uniform(0.5, 1.5) * (0.3 if dia.weekday() == 5 else 1.0) for dia in dias]
    suma = sum(pesos)
    partes = [int(total * peso / suma) for peso in pesos]
    partes[-1] += total - sum(partes)  # el resto de los redondeos va al último día, para que el total sea exacto
    return partes


def _conteos_de(id_periferico: int, dias: Sequence[date], objetivos: Sequence[ObjetivoDeConteo],
                azar: random.Random) -> tuple[list[Conteo], dict[tuple[str, str], list[int]]]:
    """Los contadores diarios de un periférico, y la cantidad de cada día por (tipo de conteo, elemento).

    El elemento de mayor peso termina con `mayor_uso` exacto; los demás, con la parte que les toca según su peso.
    """
    conteos: list[Conteo] = []
    por_dia: dict[tuple[str, str], list[int]] = {}
    for objetivo in objetivos:
        peso_maximo = max(objetivo.pesos.values())
        for elemento, peso in objetivo.pesos.items():
            partes = _repartir(round(objetivo.mayor_uso * peso / peso_maximo), dias, azar)
            por_dia[(objetivo.tipo_conteo, elemento)] = partes
            for dia, cantidad in zip(dias, partes, strict=True):
                if cantidad > 0:
                    conteos.append(Conteo(id_periferico, dia.isoformat(), objetivo.tipo_conteo, elemento, cantidad))
    return conteos, por_dia


def _dia_de_cruce(partes: Sequence[int], valor: float) -> int:
    """La posición del primer día en que lo acumulado llega a `valor`. Si nunca llega, el último día."""
    acumulado = 0
    for posicion, cantidad in enumerate(partes):
        acumulado += cantidad
        if acumulado >= valor:
            return posicion
    return len(partes) - 1


def _eventos_de(sesion: SesionPlaneada, id_sesion: int, id_teclado: int, id_mouse: int,
                azar: random.Random) -> list[EventoParaGuardar]:
    """Una muestra de eventos de la sesión, más en las horas de mayor uso (para que el mapa de calor tenga forma).

    Cada pulsación genera dos eventos (presionada y liberada), como en el capturador real; el resto son movimientos del
    mouse, clics y pasos de la rueda. Los eventos no llevan la tecla (RNF4): en la base no hay dónde guardarla.
    """
    fin = sesion.fin or datetime.combine(sesion.dia, HORA_ACTUAL_DE_LA_SESION_EN_CURSO)
    factor = FACTOR_POR_DIA_SEMANA[sesion.dia.weekday()]
    eventos: list[EventoParaGuardar] = []
    for hora in range(sesion.inicio.hour, fin.hour + 1):
        desde = max(sesion.inicio, datetime.combine(sesion.dia, time(hora)))
        hasta = min(fin, datetime.combine(sesion.dia, time(hora)) + timedelta(hours=1))
        milisegundos = int((hasta - desde).total_seconds() * 1000)
        if milisegundos <= 0:
            continue
        acciones = round(PESO_POR_HORA.get(hora, 1) * ACCIONES_POR_PESO * max(factor, 0.1) * (milisegundos / 3_600_000)
                         * azar.uniform(0.7, 1.3))
        for _ in range(acciones):
            momento = desde + timedelta(milliseconds=azar.randrange(milisegundos))
            suerte = azar.random()
            if suerte < 0.40:
                eventos.append(EventoParaGuardar(id_sesion, id_teclado, "tecla_presionada", _iso(momento, True)))
                suelta = momento + timedelta(milliseconds=azar.randint(40, 120))
                eventos.append(EventoParaGuardar(id_sesion, id_teclado, "tecla_liberada", _iso(suelta, True)))
            elif suerte < 0.70:
                eventos.append(EventoParaGuardar(id_sesion, id_mouse, "mouse_movimiento", _iso(momento, True),
                                                 azar.randint(0, 1919), azar.randint(0, 1079)))
            elif suerte < 0.90:
                tipo = "clic_izquierdo" if azar.random() < 0.85 else "clic_derecho"
                eventos.append(EventoParaGuardar(id_sesion, id_mouse, tipo, _iso(momento, True)))
            else:
                eventos.append(EventoParaGuardar(id_sesion, id_mouse, "scroll", _iso(momento, True)))
    return eventos


def crear_base_de_ejemplo(ruta: Path, hasta: date | None = None, dias: int = 21, semilla: int = 1) -> ResumenDeEjemplo:
    """Crea (o vuelve a crear) la base de ejemplo en `ruta` y devuelve un resumen de lo que contiene.

    hasta: último día con datos; por defecto hoy. dias: cuántos días cubre, contando `hasta`. semilla: misma semilla, misma base.
    Lanza ValueError si `dias` es menor que DIAS_MINIMOS o mayor que 365, y BaseExistente si `ruta` existe y no es una
    base de ejemplo (así este programa nunca borra una base real).
    """
    if not DIAS_MINIMOS <= dias <= 365:
        raise ValueError(f"dias debe estar entre {DIAS_MINIMOS} y 365")
    if ruta.exists():
        if not _es_de_ejemplo(ruta):
            raise BaseExistente("el archivo ya existe y no es una base de ejemplo: no se sobrescribe")
        _borrar(ruta)

    ultimo_dia = hasta or date.today()
    calendario = [ultimo_dia - timedelta(days=dias - 1 - posicion) for posicion in range(dias)]
    azar = random.Random(semilla)
    sesiones = _planear_sesiones(calendario, azar)
    dias_con_sesion = sorted({sesion.dia for sesion in sesiones})
    primer_dia_del_actual = dias_con_sesion[len(dias_con_sesion) // 2]  # desde aquí se usa el teclado actual

    ruta.parent.mkdir(parents=True, exist_ok=True)
    with Repositorio(ruta) as repo:
        equipo = repo.obtener_o_crear_equipo(NOMBRE_EQUIPO)

        # ----- Periféricos. El teclado viejo se retira antes de crear el actual: si no, el repositorio los trataría
        # como la misma unidad (dos teclados idénticos comparten VID/PID).
        k120 = repo.obtener_o_crear_modelo("046D", "C31C", "teclado")
        b100 = repo.obtener_o_crear_modelo("046D", "C077", "mouse")
        desconocido = repo.obtener_o_crear_modelo("1234", "5678", "mouse")
        dias_viejo = [dia for dia in dias_con_sesion if dia < primer_dia_del_actual]
        dias_actual = [dia for dia in dias_con_sesion if dia >= primer_dia_del_actual]
        dias_nuevo = dias_con_sesion[-5:]

        viejo, _ = repo.obtener_o_crear_periferico(equipo, k120, _iso(datetime.combine(dias_viejo[0], time(8, 0))))
        repo.asignar_etiqueta(viejo, "TEC-0007")
        mouse, _ = repo.obtener_o_crear_periferico(equipo, b100, _iso(datetime.combine(dias_con_sesion[0], time(8, 0))))
        repo.asignar_etiqueta(mouse, "MOU-0108")
        repo.retirar_periferico(viejo, _iso(datetime.combine(dias_viejo[-1], time(18, 0))))
        actual, _ = repo.obtener_o_crear_periferico(equipo, k120, _iso(datetime.combine(dias_actual[0], time(8, 5))))
        nuevo, _ = repo.obtener_o_crear_periferico(equipo, desconocido, _iso(datetime.combine(dias_nuevo[0], time(10, 0))))

        # ----- Desgaste. Los límites salen de la base (los de schema.sql), no de números escritos aquí.
        limite_teclas = repo.limites_del_periferico(viejo)["pulsacion_tecla"]
        limites_mouse = repo.limites_del_periferico(mouse)
        planes: dict[int, PerifericoDeEjemplo] = {}
        for id_periferico, dias_de_uso, objetivos in (
            (viejo, dias_viejo, [ObjetivoDeConteo("pulsacion_tecla", TECLAS_PESOS, limite_teclas)]),
            (actual, dias_actual, [ObjetivoDeConteo("pulsacion_tecla", TECLAS_PESOS, round(limite_teclas * 0.92))]),
            (mouse, dias_con_sesion, [
                ObjetivoDeConteo("clic_boton", BOTONES_PESOS, round(limites_mouse["clic_boton"] * 0.55)),
                ObjetivoDeConteo("scroll_paso", RUEDA_PESOS, round(limites_mouse["scroll_paso"] * 0.30)),
            ]),
            (nuevo, dias_nuevo, [ObjetivoDeConteo("clic_boton", BOTONES_PESOS, 40)]),  # sin límites: valor absoluto
        ):
            conteos, por_dia = _conteos_de(id_periferico, dias_de_uso, objetivos, azar)
            repo.sumar_a_contadores(conteos)
            planes[id_periferico] = PerifericoDeEjemplo(id_periferico, dias_de_uso, por_dia)

        # ----- Sesiones y eventos.
        ids_de_sesion: list[int] = []
        for sesion in sesiones:
            id_sesion = repo.abrir_sesion(equipo, _iso(sesion.inicio))
            ids_de_sesion.append(id_sesion)
            referencia = sesion.fin or datetime.combine(sesion.dia, HORA_ACTUAL_DE_LA_SESION_EN_CURSO)
            segundos = max(int((referencia - sesion.inicio).total_seconds()), 0)
            seg_teclado, seg_mouse = int(segundos * azar.uniform(0.30, 0.45)), int(segundos * azar.uniform(0.20, 0.35))
            if sesion.fin is None:
                repo.actualizar_actividad_sesion(id_sesion, seg_teclado, seg_mouse)
            else:
                repo.cerrar_sesion(id_sesion, _iso(sesion.fin), sesion.tipo_cierre or "normal", seg_teclado, seg_mouse)
            teclado = viejo if sesion.dia < primer_dia_del_actual else actual
            eventos = _eventos_de(sesion, id_sesion, teclado, mouse, azar)
            if sesion.dia in dias_nuevo:  # el mouse nuevo hace unos pocos clics
                eventos += [EventoParaGuardar(id_sesion, nuevo, "clic_izquierdo",
                                              _iso(sesion.inicio + timedelta(minutes=azar.randint(5, 60), milliseconds=azar.randint(0, 999)), True))
                            for _ in range(3)]
            repo.guardar_eventos(eventos)

        # ----- Alertas. Cada una se crea el día en que la tecla más gastada cruzó el umbral.
        for id_periferico, limite_de_la_alerta in ((viejo, limite_teclas), (actual, limite_teclas)):
            plan = planes[id_periferico]
            partes = plan.por_dia[("pulsacion_tecla", "ESPACIO")]
            for umbral in (90, 100):
                if sum(partes) < limite_de_la_alerta * umbral / 100:
                    continue  # este periférico no llegó a ese umbral
                posicion = _dia_de_cruce(partes, limite_de_la_alerta * umbral / 100)
                # El último día la sesión está en curso y "ahora" son las 11:30: la alerta no puede ser de más tarde.
                horas_posibles = (9, 10) if plan.dias[posicion] == ultimo_dia else (11, 16)
                creada = _iso(datetime.combine(plan.dias[posicion], time(azar.randint(*horas_posibles), azar.randint(0, 59))))
                porcentaje = int(sum(partes[: posicion + 1]) * 100 / limite_de_la_alerta)
                _ = repo.crear_alerta(id_periferico, umbral, creada, f"ESPACIO {min(porcentaje, 100)} %")
                alerta = repo.alertas_pendientes()[-1]
                if id_periferico == viejo:  # ya enviada; la del 100 % falló una vez antes
                    if umbral == 100:
                        repo.registrar_intento_de_alerta(alerta.id, _mas_segundos(creada, 5), _mas_segundos(creada, 65),
                                                         "no se pudo conectar con el servidor de correo")
                    repo.marcar_alerta_enviada(alerta.id, _mas_segundos(creada, 70 if umbral == 100 else 3))
                else:  # sigue pendiente: falló dos veces y espera el siguiente reintento
                    repo.registrar_intento_de_alerta(alerta.id, _mas_segundos(creada, 5), _mas_segundos(creada, 65),
                                                     "no se pudo conectar con el servidor de correo")
                    repo.registrar_intento_de_alerta(alerta.id, _mas_segundos(creada, 70), _mas_segundos(creada, 370),
                                                     "no se pudo conectar con el servidor de correo")
                    repo.guardar_incidente("error_envio", _mas_segundos(creada, 5),
                                           "no se pudo enviar la alerta (intento 1)", "reintento en 1 min", None)
                    repo.guardar_incidente("error_envio", _mas_segundos(creada, 70),
                                           "no se pudo enviar la alerta (intento 2)", "reintento en 5 min", None)

        # ----- Incidentes. Cada sesión inesperada deja su apagado; el resto son caídas y líneas descartadas al azar.
        for sesion, id_sesion in zip(sesiones, ids_de_sesion, strict=True):
            if sesion.tipo_cierre == "inesperado" and sesion.fin is not None:
                repo.guardar_incidente("apagado_inesperado", _iso(sesion.fin),
                                       "la sesión quedó abierta (apagado brusco o caída del servicio)",
                                       "sesión cerrada al iniciar el servicio", id_sesion)
        tipos_de_incidente = (
            ("caida_proceso", "el capturador terminó con código 3", "relanzado en 1 s"),
            ("evento_invalido", "falta el campo hora", "línea descartada"),
            ("error_comunicacion", "la línea no es JSON válido (posición 0)", "línea descartada"),
        )
        for _ in range(12):
            sesion = azar.choice([s for s in sesiones if s.fin is not None])
            id_sesion = ids_de_sesion[sesiones.index(sesion)]
            tipo, detalle, accion = azar.choice(tipos_de_incidente)
            momento = sesion.inicio + timedelta(minutes=azar.randint(1, 240))
            repo.guardar_incidente(tipo, _iso(momento), detalle, accion, id_sesion)

        # ----- Configuración de ejemplo, sin contraseña (RNF10). La marca permite volver a crear esta base sin riesgo.
        repo.escribir_configuracion("destinatarios", CORREO_DE_EJEMPLO)
        repo.escribir_configuracion("smtp_remitente", REMITENTE_DE_EJEMPLO)
        repo.escribir_configuracion(MARCA, "1")

        return ResumenDeEjemplo(
            perifericos=len(repo.listar_perifericos()),
            sesiones=len(repo.listar_sesiones()),
            eventos=len(repo.horas_de_eventos(incluir_liberaciones=True)),
            alertas=len(repo.listar_alertas()),
            incidentes=len(repo.incidentes_recientes(1_000_000)),
        )


class Opciones(argparse.Namespace):
    """Opciones de la línea de comandos, con sus valores por defecto y tipos."""

    ruta: str = ""
    hasta: str | None = None
    dias: int = 21
    semilla: int = 1


def principal(argumentos: Sequence[str] | None = None) -> int:
    """Crea la base y muestra un resumen. Devuelve 0 si salió bien, 2 si el archivo existe y no es una base de ejemplo."""
    analizador = argparse.ArgumentParser(description="Crea una base de datos de ejemplo para desarrollar sin Windows.")
    _ = analizador.add_argument("ruta", help="archivo de la base de ejemplo (si ya existe y es de ejemplo, se vuelve a crear)")
    _ = analizador.add_argument("--hasta", help="último día con datos, AAAA-MM-DD (por defecto, hoy)")
    _ = analizador.add_argument("--dias", type=int, help=f"días que cubre, de {DIAS_MINIMOS} a 365 (por defecto 21)")
    _ = analizador.add_argument("--semilla", type=int, help="la misma semilla da la misma base (por defecto 1)")
    opciones = analizador.parse_args(argumentos, namespace=Opciones())
    try:
        resumen = crear_base_de_ejemplo(
            Path(opciones.ruta), date.fromisoformat(opciones.hasta) if opciones.hasta else None,
            opciones.dias, opciones.semilla,
        )
    except BaseExistente as error:
        print(f"No se hizo nada: {error}.", file=sys.stderr)
        return 2
    contenido = (f"{resumen.perifericos} periféricos, {resumen.sesiones} sesiones, {resumen.eventos} eventos, "
                 + f"{resumen.alertas} alertas y {resumen.incidentes} incidentes")
    print(f"Base de ejemplo creada en {opciones.ruta}: {contenido}.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
