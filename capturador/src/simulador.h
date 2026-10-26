// Modo simulado: escribe eventos inventados con el mismo formato que los reales.
// Sirve para probar el servicio y el serializador en sistemas que no son Windows.
#pragma once

namespace captura {

struct OpcionesSimulador {
    long cantidad = -1;     // líneas a escribir; negativo = sin fin
    int intervalo_ms = 0;   // espera entre líneas
    unsigned semilla = 0;   // misma semilla, misma secuencia (en el mismo sistema y compilador)
};

// Devuelve el código de salida del programa: 0 si terminó bien o si el servicio cerró la lectura.
int ejecutar_simulador(const OpcionesSimulador& opciones);

}  // namespace captura
