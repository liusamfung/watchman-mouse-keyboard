// Modo simulado: escribe eventos inventados con el mismo formato que los reales.
// Sirve para probar el servicio y el serializador en sistemas que no son Windows.
//
// Los eventos son aleatorios (teclas, movimientos, clics y scroll) pero reproducibles con la misma semilla.
// No lee ningún dispositivo: nada de lo que escribe viene del teclado real de quien lo ejecuta (RNF4).
//
// Se relaciona con: usa evento.h, escritor.h y reglas_de_captura.h · lo usan simulador.cpp y principal.cpp
// (opción --simulado). Lo ejecutan pruebas/test_capturador_cpp.py, pruebas/test_capturador_simulado.py y, en
// Windows, pruebas/manual_windows.py.
#pragma once

namespace captura {

// Lo que se puede configurar desde la línea de comandos (--cantidad, --intervalo-ms y --semilla).
struct OpcionesSimulador {
    long cantidad = -1;     // líneas a escribir; negativo = sin fin
    int intervalo_ms = 0;   // espera entre líneas
    unsigned semilla = 0;   // misma semilla, misma secuencia (en el mismo sistema y compilador)
};

// Devuelve el código de salida del programa: 0 si terminó bien o si el servicio cerró la lectura.
int ejecutar_simulador(const OpcionesSimulador& opciones);

}  // namespace captura
