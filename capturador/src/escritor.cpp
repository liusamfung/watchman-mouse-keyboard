// Implementación de la escritura en stdout (ver escritor.h).
//
// Cómo funciona: `preparar_salida` ajusta el comportamiento de stdout una sola vez al arrancar, y
// `escribir_linea` escribe el texto, el salto de línea y vacía el búfer, avisando con false si algo falla.
//
// Se relaciona con: usa escritor.h y la biblioteca estándar (en Windows, también <io.h> y <fcntl.h>) ·
// lo usan principal.cpp, simulador.cpp y raw_input_windows.cpp.
#include "escritor.h"

#include <cstdio>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#else
#include <csignal>
#endif

namespace captura {

void preparar_salida() {
#ifdef _WIN32
    // Modo binario: en modo texto Windows cambiaría cada "\n" por "\r\n" y el servicio vería un "\r" de más
    // al final de cada línea JSON (el contrato pide solo "\n").
    _setmode(_fileno(stdout), _O_BINARY);
#else
    // Si el servicio cierra la lectura, escribir en la tubería mataría al proceso con SIGPIPE. Se ignora la señal
    // para que `fwrite` falle y `escribir_linea` devuelva false: el capturador termina sin ruido.
    std::signal(SIGPIPE, SIG_IGN);
#endif
}

bool escribir_linea(const std::string& linea) {
    // Tres pasos que pueden fallar por separado; en cualquiera se devuelve false (ver escritor.h).
    if (std::fwrite(linea.data(), 1, linea.size(), stdout) != linea.size()) return false;
    if (std::fputc('\n', stdout) == EOF) return false;
    return std::fflush(stdout) == 0;
}

}  // namespace captura
