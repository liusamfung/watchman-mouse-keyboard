// Escritura de líneas en stdout, como pide el contrato: una línea por evento y vaciado inmediato.
//
// Por qué se vacía el búfer en cada línea (RNF1): el servicio de Python lee stdout en tiempo real; si el
// sistema retuviera las líneas, los eventos llegarían tarde y de golpe.
//
// Se relaciona con: usa solo la biblioteca estándar · lo usan principal.cpp (`preparar_salida`),
// simulador.cpp y raw_input_windows.cpp (`escribir_linea`). Lo que escribe lo lee servicio/gestor_subproceso.py.
#pragma once

#include <string>

namespace captura {

// Prepara stdout: en Windows evita que "\n" se convierta en "\r\n"; en los demás sistemas
// evita que el programa muera con SIGPIPE si el servicio cierra la lectura.
void preparar_salida();

// Escribe la línea más un "\n" y vacía el búfer enseguida (RNF1).
// Devuelve false si no se pudo escribir, por ejemplo porque el servicio cerró la lectura.
bool escribir_linea(const std::string& linea);

}  // namespace captura
