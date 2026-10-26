// Capturador de eventos de entrada (C++).
//
// En Windows lee el teclado y el mouse con Raw Input y escribe un evento JSON por línea en stdout.
// Con --simulado escribe eventos inventados y funciona en cualquier sistema operativo.
// No toca la base de datos: eso lo hace el servicio de Python.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "escritor.h"
#include "simulador.h"

namespace {
constexpr int CODIGO_USO_INCORRECTO = 2;

void mostrar_ayuda() {
    std::fputs(
        "Uso: captura [opciones]\n"
        "  --simulado          escribe eventos inventados (para probar sin Windows)\n"
        "  --cantidad N        con --simulado, cantidad de líneas; sin este dato no termina\n"
        "  --intervalo-ms N    con --simulado, espera entre líneas en milisegundos\n"
        "  --semilla N         con --simulado, repite la misma secuencia de eventos\n"
        "  --ayuda             muestra este texto\n",
        stderr);
}

bool leer_numero(const char* texto, long& destino) {
    char* fin = nullptr;
    const long valor = std::strtol(texto, &fin, 10);
    if (fin == texto || *fin != '\0') return false;
    destino = valor;
    return true;
}
}  // namespace

int main(int argc, char** argv) {
    bool simulado = false;
    captura::OpcionesSimulador opciones;

    for (int i = 1; i < argc; ++i) {
        const std::string argumento = argv[i];
        if (argumento == "--ayuda") {
            mostrar_ayuda();
            return 0;
        }
        if (argumento == "--simulado") {
            simulado = true;
            continue;
        }
        const bool pide_numero = argumento == "--cantidad" || argumento == "--intervalo-ms" || argumento == "--semilla";
        long valor = 0;
        if (!pide_numero || i + 1 >= argc || !leer_numero(argv[i + 1], valor)) {
            std::fputs("Opción desconocida o sin un número válido.\n", stderr);
            mostrar_ayuda();
            return CODIGO_USO_INCORRECTO;
        }
        ++i;
        if (argumento == "--cantidad") opciones.cantidad = valor;
        if (argumento == "--intervalo-ms") opciones.intervalo_ms = static_cast<int>(valor);
        if (argumento == "--semilla") opciones.semilla = static_cast<unsigned>(valor);
    }

    captura::preparar_salida();

    if (simulado) {
        return captura::ejecutar_simulador(opciones);
    }

#ifdef _WIN32
    std::fputs("La captura con Raw Input todavía no está implementada.\n", stderr);
    return CODIGO_USO_INCORRECTO;
#else
    std::fputs("La captura real solo funciona en Windows. Use --simulado para probar.\n", stderr);
    return CODIGO_USO_INCORRECTO;
#endif
}
