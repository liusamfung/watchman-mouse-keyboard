// Reglas de captura que no dependen de Windows, para poder probarlas en cualquier sistema.
// Vienen de las decisiones acordadas en docs/arquitectura/contrato-json.md.
#pragma once

#include <bitset>
#include <chrono>
#include <string>

namespace captura {

// Nombre de la tecla para el contrato, a partir de su código virtual de Windows (VK_*).
// Siempre en mayúsculas, sin espacios y de 20 caracteres o menos. No depende del idioma
// del teclado: la barra espaciadora siempre es ESPACIO. Si no la conoce, devuelve VK_xx.
std::string nombre_de_tecla(unsigned codigo_virtual);

// Decisión 3: una tecla mantenida cuenta como una sola pulsación.
// Windows repite el evento mientras la tecla está presionada; esta clase deja pasar solo el primero.
class FiltroRepeticion {
public:
    // True si es una pulsación nueva; false si es la repetición de una tecla que ya estaba presionada.
    bool es_pulsacion_nueva(unsigned codigo_virtual);
    void registrar_liberacion(unsigned codigo_virtual);

private:
    std::bitset<256> presionadas_;
};

// Decisión 5: pasos enteros de la rueda. Windows entrega 120 unidades por paso; algunos mouse
// entregan fracciones. Se guarda el resto hasta completar un paso entero.
class AcumuladorRueda {
public:
    static constexpr int UNIDADES_POR_PASO = 120;

    // Suma el valor que entrega Windows y devuelve los pasos enteros completados (puede ser 0 o negativo).
    int agregar(int unidades);

private:
    int resto_ = 0;
};

// Un mouse puede mandar cientos de movimientos por segundo. Se deja pasar a lo sumo uno por intervalo,
// para no saturar stdout ni la tabla evento (RNF1, RNF6).
class LimitadorMovimiento {
public:
    using Reloj = std::chrono::steady_clock;

    explicit LimitadorMovimiento(std::chrono::milliseconds intervalo) : intervalo_(intervalo) {}

    // Recibe la hora actual (se pasa como parámetro para poder probarlo). True si el movimiento debe enviarse.
    bool permitir(Reloj::time_point ahora);

private:
    std::chrono::milliseconds intervalo_;
    Reloj::time_point ultimo_{};
    bool hay_ultimo_ = false;
};

}  // namespace captura
