// Capturador de eventos de entrada (C++).
//
// En Windows lee el teclado y el mouse con Raw Input y escribe un evento JSON por línea en stdout.
// Con --simulado escribe eventos inventados y funciona en cualquier sistema operativo.
// No toca la base de datos: eso lo hace el servicio de Python.
//
// Cómo funciona: lee las opciones de la línea de comandos, deja stdout listo (`preparar_salida`) y entrega el
// control al simulador (--simulado) o, en Windows, a la captura real con Raw Input. El código de salida dice
// qué pasó: 0 = terminó bien, 2 = opciones incorrectas o captura real pedida fuera de Windows, 3 = no se pudo
// registrar Raw Input (lo devuelve raw_input_windows.cpp).
//
// Se relaciona con: usa escritor.h, simulador.h y raw_input_windows.h (solo en Windows) · lo lanza
// servicio/gestor_subproceso.py con subprocess, y las pruebas de pruebas/ y capturador/CMakeLists.txt lo compilan.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "escritor.h"
#include "simulador.h"

#ifdef _WIN32
#include "raw_input_windows.h"
#endif

namespace {
constexpr int CODIGO_USO_INCORRECTO = 2;  // opciones mal escritas, o captura real pedida fuera de Windows

// Escribe el texto de ayuda en stderr (nunca en stdout: ahí solo van líneas JSON para el servicio).
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

// Convierte `texto` en un número entero. Devuelve false si está vacío o trae caracteres que no son dígitos
// (por ejemplo "12abc"); en ese caso no modifica `destino`.
bool leer_numero(const char* texto, long& destino) {
    char* fin = nullptr;
    const long valor = std::strtol(texto, &fin, 10);
    if (fin == texto || *fin != '\0') return false;
    destino = valor;
    return true;
}
}  // namespace

int main(int argc, char** argv) {
    // Primero se leen las opciones, y solo si todas son válidas se prepara stdout y se empieza a escribir.
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
        // --cantidad, --intervalo-ms y --semilla llevan un número detrás; cualquier otra cosa es un uso incorrecto.
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

    // Debe ir antes de escribir la primera línea: cambia cómo se escribe en stdout (ver escritor.cpp).
    captura::preparar_salida();

    if (simulado) {
        return captura::ejecutar_simulador(opciones);
    }

#ifdef _WIN32
    return captura::ejecutar_raw_input();
#else
    std::fputs("La captura real solo funciona en Windows. Use --simulado para probar.\n", stderr);
    return CODIGO_USO_INCORRECTO;
#endif
}
