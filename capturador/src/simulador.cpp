#include "simulador.h"

#include <chrono>
#include <deque>
#include <random>
#include <string>
#include <thread>
#include <vector>

#include "escritor.h"
#include "evento.h"
#include "reglas_de_captura.h"

namespace captura {

namespace {
constexpr int ANCHO_PANTALLA = 1920;
constexpr int ALTO_PANTALLA = 1080;

// Los mismos modelos de ejemplo de docs/base-de-datos/schema.sql.
Evento evento_base(const std::string& tipo, bool es_teclado) {
    Evento evento;
    evento.tipo = tipo;
    evento.hora = hora_actual();
    evento.dispositivo = es_teclado ? "teclado" : "mouse";
    evento.vid = "046D";
    evento.pid = es_teclado ? "C31C" : "C077";
    evento.nombre = es_teclado ? "Logitech K120" : "Logitech B100";
    return evento;
}

// Letras, dígitos y algunas teclas especiales (códigos virtuales de Windows).
const std::vector<unsigned>& teclas_posibles() {
    static const std::vector<unsigned> teclas = [] {
        std::vector<unsigned> codigos;
        for (unsigned c = 0x41; c <= 0x5A; ++c) codigos.push_back(c);
        for (unsigned c = 0x30; c <= 0x39; ++c) codigos.push_back(c);
        for (const unsigned c : {0x0DU, 0x20U, 0x08U, 0x09U, 0x74U}) codigos.push_back(c);
        return codigos;
    }();
    return teclas;
}

// Genera el siguiente grupo de eventos: una pulsación produce dos (presionada y liberada).
void generar(std::mt19937& azar, std::deque<Evento>& pendientes) {
    std::uniform_real_distribution<double> suerte(0.0, 1.0);
    const double dado = suerte(azar);
    if (dado < 0.50) {
        const auto& teclas = teclas_posibles();
        std::uniform_int_distribution<std::size_t> elegir(0, teclas.size() - 1);
        Evento presionada = evento_base("tecla_presionada", true);
        presionada.tecla = nombre_de_tecla(teclas[elegir(azar)]);
        pendientes.push_back(presionada);
        pendientes.push_back(evento_base("tecla_liberada", true));
    } else if (dado < 0.80) {
        Evento movimiento = evento_base("mouse_movimiento", false);
        movimiento.x = std::uniform_int_distribution<int>(0, ANCHO_PANTALLA - 1)(azar);
        movimiento.y = std::uniform_int_distribution<int>(0, ALTO_PANTALLA - 1)(azar);
        pendientes.push_back(movimiento);
    } else if (dado < 0.92) {
        const bool izquierdo = std::uniform_int_distribution<int>(0, 1)(azar) == 0;
        pendientes.push_back(evento_base(izquierdo ? "clic_izquierdo" : "clic_derecho", false));
    } else {
        static const int opciones[] = {-3, -2, -1, 1, 2, 3};
        Evento rueda = evento_base("scroll", false);
        rueda.pasos = opciones[std::uniform_int_distribution<int>(0, 5)(azar)];
        pendientes.push_back(rueda);
    }
}
}  // namespace

int ejecutar_simulador(const OpcionesSimulador& opciones) {
    std::mt19937 azar(opciones.semilla);
    std::deque<Evento> pendientes;
    long escritas = 0;

    while (opciones.cantidad < 0 || escritas < opciones.cantidad) {
        if (pendientes.empty()) generar(azar, pendientes);
        const std::string linea = a_json(pendientes.front());
        pendientes.pop_front();
        if (!escribir_linea(linea)) return 0;  // el servicio cerró la lectura: terminar sin ruido
        ++escritas;
        if (opciones.intervalo_ms > 0) {
            std::this_thread::sleep_for(std::chrono::milliseconds(opciones.intervalo_ms));
        }
    }
    return 0;
}

}  // namespace captura
