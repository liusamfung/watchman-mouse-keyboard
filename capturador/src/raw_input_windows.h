// Captura real del teclado y del mouse con Raw Input. Solo se compila en Windows.
#pragma once

namespace captura {

// Crea una ventana oculta, se registra para recibir teclado y mouse y escribe un evento JSON por línea
// en stdout hasta que el servicio cierre la lectura. Devuelve el código de salida del programa.
int ejecutar_raw_input();

}  // namespace captura
