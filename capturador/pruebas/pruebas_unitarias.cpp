// Pruebas unitarias del núcleo portable del capturador. Sin bibliotecas externas (RNF7).
// Devuelve 0 si todo pasa y 1 si algo falla; cada fallo se muestra en stderr.
#include <chrono>
#include <cstdio>
#include <regex>
#include <string>

#include "evento.h"
#include "reglas_de_captura.h"

namespace {
int fallos = 0;
int verificaciones = 0;

#define VERIFICAR(condicion)                                                           \
    do {                                                                               \
        ++verificaciones;                                                              \
        if (!(condicion)) {                                                            \
            ++fallos;                                                                  \
            std::fprintf(stderr, "FALLÓ %s:%d: %s\n", __FILE__, __LINE__, #condicion); \
        }                                                                              \
    } while (0)

using captura::Evento;

Evento evento_de_ejemplo(const std::string& tipo, const std::string& dispositivo) {
    Evento evento;
    evento.tipo = tipo;
    evento.hora = "2026-10-25T21:14:03.482";
    evento.dispositivo = dispositivo;
    evento.vid = "046D";
    evento.pid = dispositivo == "teclado" ? "C31C" : "C077";
    return evento;
}

void prueba_json_de_una_pulsacion() {
    Evento evento = evento_de_ejemplo("tecla_presionada", "teclado");
    evento.nombre = "Logitech K120";
    evento.tecla = "E";
    VERIFICAR(captura::a_json(evento) ==
              R"({"v":1,"tipo":"tecla_presionada","hora":"2026-10-25T21:14:03.482","dispositivo":"teclado",)"
              R"("vid":"046D","pid":"C31C","nombre":"Logitech K120","tecla":"E"})");
}

void prueba_json_omite_los_campos_sin_valor() {
    const Evento clic = evento_de_ejemplo("clic_izquierdo", "mouse");
    VERIFICAR(captura::a_json(clic) ==
              R"({"v":1,"tipo":"clic_izquierdo","hora":"2026-10-25T21:14:03.482","dispositivo":"mouse",)"
              R"("vid":"046D","pid":"C077"})");
}

void prueba_json_de_movimiento_y_scroll() {
    Evento movimiento = evento_de_ejemplo("mouse_movimiento", "mouse");
    movimiento.x = -300;  // con varios monitores el cursor puede tener coordenadas negativas
    movimiento.y = 40;
    VERIFICAR(captura::a_json(movimiento).find(R"("x":-300,"y":40})") != std::string::npos);

    Evento rueda = evento_de_ejemplo("scroll", "mouse");
    rueda.pasos = -3;
    VERIFICAR(captura::a_json(rueda).find(R"("pasos":-3})") != std::string::npos);
}

void prueba_escapar_json() {
    VERIFICAR(captura::escapar_json("a\"b") == "a\\\"b");
    VERIFICAR(captura::escapar_json("a\\b") == "a\\\\b");
    VERIFICAR(captura::escapar_json("a\nb\tc\rd") == "a\\nb\\tc\\rd");
    VERIFICAR(captura::escapar_json(std::string(1, '\x01')) == "\\u0001");
    VERIFICAR(captura::escapar_json("camión") == "camión");  // UTF-8 sin cambios
}

void prueba_formato_de_la_hora() {
    const std::regex formato(R"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3})");
    VERIFICAR(std::regex_match(captura::hora_actual(), formato));
}

void prueba_nombres_de_tecla() {
    VERIFICAR(captura::nombre_de_tecla(0x45) == "E");
    VERIFICAR(captura::nombre_de_tecla(0x35) == "5");
    VERIFICAR(captura::nombre_de_tecla(0x74) == "F5");
    VERIFICAR(captura::nombre_de_tecla(0x87) == "F24");
    VERIFICAR(captura::nombre_de_tecla(0x0D) == "ENTER");
    VERIFICAR(captura::nombre_de_tecla(0x20) == "ESPACIO");
    VERIFICAR(captura::nombre_de_tecla(0x08) == "RETROCESO");
    VERIFICAR(captura::nombre_de_tecla(0x65) == "NUM_5");
    VERIFICAR(captura::nombre_de_tecla(0xE5) == "VK_E5");  // código sin nombre
}

void prueba_todos_los_nombres_cumplen_el_contrato() {
    // El contrato pide mayúsculas, sin espacios y de 1 a 20 caracteres.
    for (unsigned codigo = 0; codigo < 256; ++codigo) {
        const std::string nombre = captura::nombre_de_tecla(codigo);
        bool valido = !nombre.empty() && nombre.size() <= 20;
        for (const char c : nombre) {
            if (c == ' ' || (c >= 'a' && c <= 'z')) valido = false;
        }
        if (!valido) std::fprintf(stderr, "nombre inválido para el código %u\n", codigo);
        VERIFICAR(valido);
    }
}

void prueba_filtro_de_repeticion() {
    captura::FiltroRepeticion filtro;
    VERIFICAR(filtro.es_pulsacion_nueva(0x41));    // A presionada
    VERIFICAR(!filtro.es_pulsacion_nueva(0x41));   // repetición automática
    VERIFICAR(!filtro.es_pulsacion_nueva(0x41));   // otra repetición
    VERIFICAR(filtro.es_pulsacion_nueva(0x42));    // otra tecla distinta sí cuenta
    filtro.registrar_liberacion(0x41);
    VERIFICAR(filtro.es_pulsacion_nueva(0x41));    // después de soltarla, una pulsación nueva
    VERIFICAR(!filtro.es_pulsacion_nueva(0x42));   // B sigue presionada
    VERIFICAR(filtro.es_pulsacion_nueva(0x1000));  // código fuera de rango: no se filtra
    VERIFICAR(filtro.es_pulsacion_nueva(0x1000));
}

void prueba_acumulador_de_rueda() {
    captura::AcumuladorRueda rueda;
    VERIFICAR(rueda.agregar(120) == 1);
    VERIFICAR(rueda.agregar(-120) == -1);
    VERIFICAR(rueda.agregar(240) == 2);
    VERIFICAR(rueda.agregar(60) == 0);   // medio paso: se guarda
    VERIFICAR(rueda.agregar(60) == 1);   // completa el paso
    VERIFICAR(rueda.agregar(30) == 0);
    VERIFICAR(rueda.agregar(30) == 0);
    VERIFICAR(rueda.agregar(30) == 0);
    VERIFICAR(rueda.agregar(30) == 1);   // cuatro fracciones de 30 hacen un paso
    VERIFICAR(rueda.agregar(-60) == 0);
    VERIFICAR(rueda.agregar(-60) == -1);
}

void prueba_limitador_de_movimiento() {
    using std::chrono::milliseconds;
    const auto inicio = captura::LimitadorMovimiento::Reloj::now();
    captura::LimitadorMovimiento limitador(milliseconds(100));
    VERIFICAR(limitador.permitir(inicio));                          // el primero siempre pasa
    VERIFICAR(!limitador.permitir(inicio + milliseconds(10)));
    VERIFICAR(!limitador.permitir(inicio + milliseconds(99)));
    VERIFICAR(limitador.permitir(inicio + milliseconds(100)));      // se cumplió el intervalo
    VERIFICAR(!limitador.permitir(inicio + milliseconds(150)));     // se cuenta desde el último enviado
    VERIFICAR(limitador.permitir(inicio + milliseconds(200)));
}
}  // namespace

int main() {
    prueba_json_de_una_pulsacion();
    prueba_json_omite_los_campos_sin_valor();
    prueba_json_de_movimiento_y_scroll();
    prueba_escapar_json();
    prueba_formato_de_la_hora();
    prueba_nombres_de_tecla();
    prueba_todos_los_nombres_cumplen_el_contrato();
    prueba_filtro_de_repeticion();
    prueba_acumulador_de_rueda();
    prueba_limitador_de_movimiento();

    std::printf("%d verificaciones, %d fallos\n", verificaciones, fallos);
    return fallos == 0 ? 0 : 1;
}
