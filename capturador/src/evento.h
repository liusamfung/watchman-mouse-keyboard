// Evento de entrada y su conversión a JSON, según docs/arquitectura/contrato-json.md.
//
// Un `Evento` guarda lo que el capturador sabe de una pulsación, un clic, un movimiento o un paso de rueda.
// `a_json` lo convierte en la línea que lee el servicio; los campos sin valor no se escriben.
//
// Se relaciona con: usa docs/arquitectura/contrato-json.md (campos y orden) · lo usan evento.cpp,
// simulador.cpp, raw_input_windows.cpp y pruebas_unitarias.cpp. La línea que produce la valida servicio/validador.py.
#pragma once

#include <optional>
#include <string>

namespace captura {

// Un evento listo para escribirse en stdout. Los campos opcionales solo se
// escriben si tienen valor (la tabla "Reglas por tipo" del contrato dice cuáles).
struct Evento {
    std::string tipo;         // tecla_presionada, tecla_liberada, mouse_movimiento, clic_izquierdo, clic_derecho o scroll
    std::string hora;         // ISO 8601 con milisegundos
    std::string dispositivo;  // teclado o mouse
    std::string vid;          // 4 dígitos hexadecimales en mayúscula
    std::string pid;
    std::optional<std::string> nombre;
    std::optional<std::string> tecla;  // solo en tecla_presionada; viaja únicamente para el contador (RNF4)
    std::optional<int> x;              // solo en mouse_movimiento
    std::optional<int> y;
    std::optional<int> pasos;          // solo en scroll
};

// Escapa un texto para ponerlo entre comillas dentro de un JSON.
std::string escapar_json(const std::string& texto);

// Devuelve el evento como una línea JSON compacta, sin salto de línea al final.
std::string a_json(const Evento& evento);

// Hora local en ISO 8601 con milisegundos, por ejemplo 2026-10-25T21:14:03.482.
std::string hora_actual();

}  // namespace captura
