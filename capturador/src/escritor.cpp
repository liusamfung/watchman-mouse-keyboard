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
    _setmode(_fileno(stdout), _O_BINARY);
#else
    std::signal(SIGPIPE, SIG_IGN);
#endif
}

bool escribir_linea(const std::string& linea) {
    if (std::fwrite(linea.data(), 1, linea.size(), stdout) != linea.size()) return false;
    if (std::fputc('\n', stdout) == EOF) return false;
    return std::fflush(stdout) == 0;
}

}  // namespace captura
