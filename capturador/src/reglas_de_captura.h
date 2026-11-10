// Reglas de captura que no dependen de Windows, para poder probarlas en cualquier sistema.
// Vienen de las decisiones acordadas en docs/arquitectura/contrato-json.md.
//
// Qué hay aquí: el nombre de cada tecla (`nombre_de_tecla`), el filtro de repetición de teclas mantenidas, el
// acumulador de pasos de la rueda y el limitador de movimientos del mouse. Ninguna depende de windows.h.
//
// Privacidad (RNF4): el nombre de la tecla solo se usa en memoria y viaja por stdout hacia el contador; este
// módulo no escribe nada en ningún lado.
//
// Se relaciona con: usa docs/arquitectura/contrato-json.md (decisiones 3, 4 y 5) y la biblioteca estándar · lo
// usan reglas_de_captura.cpp, raw_input_windows.cpp (captura real), simulador.cpp y pruebas_unitarias.cpp.
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
    // Marca la tecla como suelta: la siguiente pulsación de esa tecla volverá a contar.
    void registrar_liberacion(unsigned codigo_virtual);

private:
    std::bitset<256> presionadas_;  // un bit por código virtual (VK_*): 1 = la tecla está presionada
};

// Decisión 5: pasos enteros de la rueda. Windows entrega 120 unidades por paso; algunos mouse
// entregan fracciones. Se guarda el resto hasta completar un paso entero.
class AcumuladorRueda {
public:
    static constexpr int UNIDADES_POR_PASO = 120;

    // Suma el valor que entrega Windows y devuelve los pasos enteros completados (puede ser 0 o negativo).
    int agregar(int unidades);

private:
    int resto_ = 0;  // unidades que todavía no completan un paso (entre -119 y 119)
};

// Un mouse puede mandar cientos de movimientos por segundo. Se deja pasar a lo sumo uno por intervalo,
// para no saturar stdout ni la tabla evento (RNF1, RNF6).
class LimitadorMovimiento {
public:
    // Reloj que no retrocede aunque alguien cambie la hora del sistema; la hora real del evento sale de hora_actual().
    using Reloj = std::chrono::steady_clock;

    // `intervalo`: tiempo mínimo entre dos movimientos enviados.
    explicit LimitadorMovimiento(std::chrono::milliseconds intervalo) : intervalo_(intervalo) {}

    // Recibe la hora actual (se pasa como parámetro para poder probarlo). True si el movimiento debe enviarse.
    bool permitir(Reloj::time_point ahora);

private:
    std::chrono::milliseconds intervalo_;
    Reloj::time_point ultimo_{};  // momento del último movimiento que se dejó pasar
    bool hay_ultimo_ = false;     // false hasta el primer movimiento: el primero siempre pasa
};

}  // namespace captura
