// Captura real del teclado y del mouse con Raw Input. Solo se compila en Windows.
//
// Se relaciona con: usa raw_input_windows.cpp (la implementación) · lo usa principal.cpp, solo cuando se compila
// para Windows y no se pide --simulado. La línea JSON que escribe la lee servicio/gestor_subproceso.py.
#pragma once

namespace captura {

// Crea una ventana oculta, se registra para recibir teclado y mouse y escribe un evento JSON por línea
// en stdout hasta que el servicio cierre la lectura. Devuelve el código de salida del programa.
int ejecutar_raw_input();

}  // namespace captura
