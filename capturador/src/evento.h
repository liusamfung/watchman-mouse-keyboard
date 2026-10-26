// Evento de entrada y su conversión a JSON, según docs/arquitectura/contrato-json.md.
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
