// Implementación de `Evento`: serializa a JSON a mano y da la hora local con milisegundos (ver evento.h).
//
// Por qué sin biblioteca de JSON: la salida es una línea con un puñado de campos fijos, y así el capturador
// no depende de nada externo (RNF7). El texto se escapa con `escapar_json`; los números van tal cual.
//
// Se relaciona con: usa evento.h y la biblioteca estándar · lo usan simulador.cpp, raw_input_windows.cpp y
// pruebas_unitarias.cpp. Su salida debe cumplir servicio/validador.py y docs/arquitectura/contrato-json.md.
#include "evento.h"

#include <chrono>
#include <cstdio>
#include <ctime>

namespace captura {

namespace {
// Versión del contrato JSON. Debe coincidir con VERSION_CONTRATO de servicio/validador.py: si no, el servicio
// rechazaría todas las líneas.
constexpr int VERSION_CONTRATO = 1;

// Agrega `,"campo":"valor"` (con el valor ya escapado) al final del JSON que se está armando.
void agregar_texto(std::string& json, const char* campo, const std::string& valor) {
    json += ",\"";
    json += campo;
    json += "\":\"";
    json += escapar_json(valor);
    json += '"';
}

// Agrega `,"campo":valor` (número sin comillas) al final del JSON que se está armando.
void agregar_entero(std::string& json, const char* campo, int valor) {
    json += ",\"";
    json += campo;
    json += "\":";
    json += std::to_string(valor);
}
}  // namespace

std::string escapar_json(const std::string& texto) {
    std::string salida;
    salida.reserve(texto.size());
    // `unsigned char` para poder comparar con 0x20 sin que los bytes de UTF-8 (mayores que 0x7F) salgan negativos.
    for (const unsigned char caracter : texto) {
        switch (caracter) {
            case '"':  salida += "\\\""; break;
            case '\\': salida += "\\\\"; break;
            case '\n': salida += "\\n"; break;
            case '\r': salida += "\\r"; break;
            case '\t': salida += "\\t"; break;
            default:
                if (caracter < 0x20) {  // el resto de caracteres de control no pueden ir sin escapar en JSON
                    char codigo[7];
                    std::snprintf(codigo, sizeof codigo, "\\u%04x", static_cast<unsigned>(caracter));
                    salida += codigo;
                } else {
                    salida += static_cast<char>(caracter);  // UTF-8 se deja tal cual
                }
        }
    }
    return salida;
}

std::string a_json(const Evento& evento) {
    // El orden de los campos es el del contrato. `nombre`, `tecla`, `x`, `y` y `pasos` solo se escriben si el
    // tipo de evento los usa (tabla "Reglas por tipo" del contrato); el servicio rechaza los que sobran o faltan.
    std::string json = "{\"v\":" + std::to_string(VERSION_CONTRATO);
    agregar_texto(json, "tipo", evento.tipo);
    agregar_texto(json, "hora", evento.hora);
    agregar_texto(json, "dispositivo", evento.dispositivo);
    agregar_texto(json, "vid", evento.vid);
    agregar_texto(json, "pid", evento.pid);
    if (evento.nombre) agregar_texto(json, "nombre", *evento.nombre);
    if (evento.tecla) agregar_texto(json, "tecla", *evento.tecla);
    if (evento.x) agregar_entero(json, "x", *evento.x);
    if (evento.y) agregar_entero(json, "y", *evento.y);
    if (evento.pasos) agregar_entero(json, "pasos", *evento.pasos);
    json += '}';
    return json;
}

std::string hora_actual() {
    using namespace std::chrono;
    const auto ahora = system_clock::now();
    const std::time_t segundos = system_clock::to_time_t(ahora);
    const auto milisegundos = duration_cast<milliseconds>(ahora.time_since_epoch()).count() % 1000;

    // Se usan las variantes que reciben el destino (`localtime_s` en Windows, `localtime_r` en el resto) porque
    // `localtime` devuelve un búfer compartido y no es seguro si dos hilos piden la hora a la vez.
    std::tm local{};
#ifdef _WIN32
    localtime_s(&local, &segundos);
#else
    localtime_r(&segundos, &local);
#endif

    char texto[32];
    std::snprintf(texto, sizeof texto, "%04d-%02d-%02dT%02d:%02d:%02d.%03d",
                  local.tm_year + 1900, local.tm_mon + 1, local.tm_mday,
                  local.tm_hour, local.tm_min, local.tm_sec, static_cast<int>(milisegundos));
    return texto;
}

}  // namespace captura
