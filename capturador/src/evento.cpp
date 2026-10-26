#include "evento.h"

#include <chrono>
#include <cstdio>
#include <ctime>

namespace captura {

namespace {
constexpr int VERSION_CONTRATO = 1;

void agregar_texto(std::string& json, const char* campo, const std::string& valor) {
    json += ",\"";
    json += campo;
    json += "\":\"";
    json += escapar_json(valor);
    json += '"';
}

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
    for (const unsigned char caracter : texto) {
        switch (caracter) {
            case '"':  salida += "\\\""; break;
            case '\\': salida += "\\\\"; break;
            case '\n': salida += "\\n"; break;
            case '\r': salida += "\\r"; break;
            case '\t': salida += "\\t"; break;
            default:
                if (caracter < 0x20) {
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
    // El orden de los campos es el del contrato.
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
