// Captura real con Raw Input (RF1, RF5, RF6, RF7). Solo se compila en Windows.
//
// Raw Input, y no un gancho global como SetWindowsHookEx, entrega junto a cada evento el dispositivo
// que lo generó, y con eso se saca el VID/PID para contar el desgaste de cada periférico.
//
// Cómo funciona: crea una ventana oculta que solo recibe mensajes, registra el teclado y el mouse con
// RIDEV_INPUTSINK para recibir los eventos aunque otra ventana tenga el foco, y en cada mensaje WM_INPUT lee
// el evento, averigua qué dispositivo lo generó (VID/PID de su ruta), lo convierte en un `Evento` y escribe su
// línea JSON en stdout. El teclado pasa por el filtro de repetición; la rueda, por el acumulador; el mouse,
// por el limitador de movimientos (ver reglas_de_captura.h).
//
// Privacidad (RNF4): el nombre de la tecla solo viaja por stdout hacia el contador del servicio. Aquí no se
// guarda ni se escribe en ningún archivo ni en stderr. RNF11: la ventana no se ve ni aparece en la barra de tareas.
//
// Se relaciona con: usa windows.h (Raw Input), escritor.h, evento.h y reglas_de_captura.h · lo usa principal.cpp
// (a través de raw_input_windows.h). No se prueba con pruebas automáticas: se prueba a mano en Windows con
// docs/pruebas-en-windows.md y pruebas/manual_windows.py.
#ifdef _WIN32

#include "raw_input_windows.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>

#include <chrono>
#include <cstdio>
#include <cwctype>
#include <string>
#include <unordered_map>
#include <vector>

#include "escritor.h"
#include "evento.h"
#include "reglas_de_captura.h"

namespace captura {

namespace {

// A lo sumo un movimiento cada 100 ms (unos 10 por segundo), para no saturar stdout ni la tabla `evento`.
constexpr std::chrono::milliseconds INTERVALO_MOVIMIENTO(100);
constexpr unsigned CODIGO_SIN_TECLA = 0xFF;  // Raw Input usa 0xFF en algunas secuencias que no son una tecla
constexpr int CODIGO_ERROR_AL_REGISTRAR = 3;  // código de salida cuando no se pudo crear la ventana o registrar Raw Input

// Identifican qué dispositivos se piden a Raw Input: "página genérica" (0x01), uso 0x06 = teclado y 0x02 = mouse.
constexpr USHORT PAGINA_GENERICA = 0x01;
constexpr USHORT USO_TECLADO = 0x06;
constexpr USHORT USO_MOUSE = 0x02;

// Identifica el modelo de un periférico: 4 dígitos hexadecimales en mayúscula, o "0000" si no se pudieron leer.
struct DatosDispositivo {
    std::string vid;
    std::string pid;
};

// Estado de la captura. Hay una sola ventana, así que basta con un estado compartido.
struct Estado {
    FiltroRepeticion filtro;
    AcumuladorRueda rueda;
    LimitadorMovimiento limitador{INTERVALO_MOVIMIENTO};
    std::unordered_map<HANDLE, DatosDispositivo> dispositivos;
};
Estado estado;

// Busca en la ruta del dispositivo algo como VID_046D y devuelve los 4 dígitos, o 0000 si no los encuentra
// (teclados virtuales, de escritorio remoto o PS/2 no tienen VID/PID).
std::string buscar_codigo(const std::wstring& ruta, const std::wstring& marca) {
    const std::size_t posicion = ruta.find(marca);
    if (posicion == std::wstring::npos || ruta.size() < posicion + marca.size() + 4) return "0000";
    std::string codigo;
    for (std::size_t i = 0; i < 4; ++i) {
        const wchar_t c = ruta[posicion + marca.size() + i];
        const bool es_hexadecimal = (c >= L'0' && c <= L'9') || (c >= L'A' && c <= L'F');
        if (!es_hexadecimal) return "0000";
        codigo += static_cast<char>(c);
    }
    return codigo;
}

// Lee el VID y el PID de un dispositivo a partir de su ruta, que Windows entrega con la forma
// \\?\HID#VID_xxxx&PID_xxxx#... Si algo falla, devuelve "0000" en los dos campos (el servicio lo trata como desconocido).
DatosDispositivo leer_datos_del_dispositivo(HANDLE dispositivo) {
    const DatosDispositivo desconocido{"0000", "0000"};
    // GetRawInputDeviceInfoW se llama dos veces: la primera, con destino nulo, solo devuelve el tamaño necesario.
    UINT largo = 0;
    if (GetRawInputDeviceInfoW(dispositivo, RIDI_DEVICENAME, nullptr, &largo) != 0 || largo == 0) return desconocido;

    std::wstring ruta(largo, L'\0');
    if (GetRawInputDeviceInfoW(dispositivo, RIDI_DEVICENAME, ruta.data(), &largo) == static_cast<UINT>(-1)) {
        return desconocido;
    }
    ruta.resize(std::wcslen(ruta.c_str()));
    for (wchar_t& c : ruta) c = static_cast<wchar_t>(std::towupper(c));

    return {buscar_codigo(ruta, L"VID_"), buscar_codigo(ruta, L"PID_")};
}

// Cada dispositivo se consulta una sola vez y se recuerda.
const DatosDispositivo& datos_de(HANDLE dispositivo) {
    auto encontrado = estado.dispositivos.find(dispositivo);
    if (encontrado == estado.dispositivos.end()) {
        encontrado = estado.dispositivos.emplace(dispositivo, leer_datos_del_dispositivo(dispositivo)).first;
    }
    return encontrado->second;
}

// Crea un evento con la hora actual y los datos del dispositivo; quien lo llama completa los campos del tipo.
Evento nuevo_evento(const char* tipo, const char* dispositivo, const DatosDispositivo& datos) {
    Evento evento;
    evento.tipo = tipo;
    evento.hora = hora_actual();
    evento.dispositivo = dispositivo;
    evento.vid = datos.vid;
    evento.pid = datos.pid;
    return evento;
}

// Escribe el evento en stdout. Si ya no se puede escribir, pide cerrar el bucle de mensajes.
void emitir(const Evento& evento) {
    // Si el servicio cerró la lectura, no tiene sentido seguir capturando.
    if (!escribir_linea(a_json(evento))) PostQuitMessage(0);
}

// Convierte un evento de teclado en `tecla_presionada` o `tecla_liberada`. Una tecla mantenida cuenta una sola
// vez (decisión 3 del contrato); las liberaciones se envían todas porque no suman desgaste, solo actividad.
void procesar_teclado(const RAWKEYBOARD& teclado, const DatosDispositivo& datos) {
    const unsigned codigo = teclado.VKey;
    if (codigo == 0 || codigo == CODIGO_SIN_TECLA) return;

    const bool es_liberacion = (teclado.Flags & RI_KEY_BREAK) != 0;
    if (es_liberacion) {
        estado.filtro.registrar_liberacion(codigo);
        emitir(nuevo_evento("tecla_liberada", "teclado", datos));
    } else if (estado.filtro.es_pulsacion_nueva(codigo)) {
        Evento pulsacion = nuevo_evento("tecla_presionada", "teclado", datos);
        pulsacion.tecla = nombre_de_tecla(codigo);  // solo viaja por stdout, para el contador (RNF4)
        emitir(pulsacion);
    }
}

// Convierte un evento de mouse en cero, uno o varios eventos: clic izquierdo, clic derecho, scroll y movimiento
// pueden llegar juntos en un mismo mensaje.
void procesar_mouse(const RAWMOUSE& mouse, const DatosDispositivo& datos) {
    if ((mouse.usButtonFlags & RI_MOUSE_LEFT_BUTTON_DOWN) != 0) {
        emitir(nuevo_evento("clic_izquierdo", "mouse", datos));
    }
    if ((mouse.usButtonFlags & RI_MOUSE_RIGHT_BUTTON_DOWN) != 0) {
        emitir(nuevo_evento("clic_derecho", "mouse", datos));
    }
    if ((mouse.usButtonFlags & RI_MOUSE_WHEEL) != 0) {
        const int unidades = static_cast<SHORT>(mouse.usButtonData);  // positivo = hacia arriba
        const int pasos = estado.rueda.agregar(unidades);
        if (pasos != 0) {
            Evento rueda = nuevo_evento("scroll", "mouse", datos);
            rueda.pasos = pasos;
            emitir(rueda);
        }
    }

    // Raw Input normalmente da el desplazamiento relativo del mouse; el contrato pide la posición absoluta (decisión 4),
    // así que se consulta aparte con GetCursorPos, y solo cuando el limitador deja pasar el movimiento.
    const bool hubo_movimiento = mouse.lLastX != 0 || mouse.lLastY != 0;
    if (hubo_movimiento && estado.limitador.permitir(LimitadorMovimiento::Reloj::now())) {
        POINT punto{};
        if (GetCursorPos(&punto)) {  // posición absoluta del cursor (decisión 4)
            Evento movimiento = nuevo_evento("mouse_movimiento", "mouse", datos);
            movimiento.x = static_cast<int>(punto.x);
            movimiento.y = static_cast<int>(punto.y);
            emitir(movimiento);
        }
    }
}

// Lee el mensaje WM_INPUT y lo reparte según sea de teclado o de mouse. Si no se puede leer, lo ignora.
void procesar_entrada(HRAWINPUT manejador) {
    // GetRawInputData también se llama dos veces: la primera solo pregunta cuántos bytes se necesitan.
    UINT tamano = 0;
    if (GetRawInputData(manejador, RID_INPUT, nullptr, &tamano, sizeof(RAWINPUTHEADER)) != 0) return;

    std::vector<BYTE> memoria(tamano);
    if (GetRawInputData(manejador, RID_INPUT, memoria.data(), &tamano, sizeof(RAWINPUTHEADER)) != tamano) return;

    const RAWINPUT& entrada = *reinterpret_cast<const RAWINPUT*>(memoria.data());
    const DatosDispositivo& datos = datos_de(entrada.header.hDevice);
    if (entrada.header.dwType == RIM_TYPEKEYBOARD) {
        procesar_teclado(entrada.data.keyboard, datos);
    } else if (entrada.header.dwType == RIM_TYPEMOUSE) {
        procesar_mouse(entrada.data.mouse, datos);
    }
}

// Procedimiento de la ventana oculta: Windows lo llama por cada mensaje. Solo interesan WM_INPUT (hay un evento)
// y WM_DESTROY (cerrar el bucle); el resto lo resuelve DefWindowProc.
LRESULT CALLBACK procedimiento_de_la_ventana(HWND ventana, UINT mensaje, WPARAM wparam, LPARAM lparam) {
    if (mensaje == WM_INPUT) {
        procesar_entrada(reinterpret_cast<HRAWINPUT>(lparam));
        // Windows pide llamar a DefWindowProc después de WM_INPUT para que haga su limpieza.
    } else if (mensaje == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(ventana, mensaje, wparam, lparam);
}

}  // namespace

int ejecutar_raw_input() {
    // Pasos: 1) registrar la clase de la ventana, 2) crear la ventana oculta, 3) registrar teclado y mouse en
    // Raw Input, 4) repetir el bucle de mensajes hasta que se pida salir. Si falla un paso, termina con código 3.
    const HINSTANCE instancia = GetModuleHandleW(nullptr);

    WNDCLASSEXW clase{};
    clase.cbSize = sizeof(clase);
    clase.lpfnWndProc = procedimiento_de_la_ventana;
    clase.hInstance = instancia;
    clase.lpszClassName = L"CapturaVentanaOculta";
    if (RegisterClassExW(&clase) == 0) {
        std::fputs("No se pudo registrar la clase de la ventana oculta.\n", stderr);
        return CODIGO_ERROR_AL_REGISTRAR;
    }

    // Ventana "solo de mensajes": no se dibuja, no aparece en la barra de tareas y no se ve (RNF11).
    const HWND ventana = CreateWindowExW(0, clase.lpszClassName, L"captura", 0, 0, 0, 0, 0,
                                         HWND_MESSAGE, nullptr, instancia, nullptr);
    if (ventana == nullptr) {
        std::fputs("No se pudo crear la ventana oculta.\n", stderr);
        return CODIGO_ERROR_AL_REGISTRAR;
    }

    // RIDEV_INPUTSINK: recibir los eventos aunque esta ventana no tenga el foco, que es siempre.
    RAWINPUTDEVICE dispositivos[2]{};
    dispositivos[0].usUsagePage = PAGINA_GENERICA;
    dispositivos[0].usUsage = USO_TECLADO;
    dispositivos[0].dwFlags = RIDEV_INPUTSINK;
    dispositivos[0].hwndTarget = ventana;
    dispositivos[1].usUsagePage = PAGINA_GENERICA;
    dispositivos[1].usUsage = USO_MOUSE;
    dispositivos[1].dwFlags = RIDEV_INPUTSINK;
    dispositivos[1].hwndTarget = ventana;
    if (!RegisterRawInputDevices(dispositivos, 2, sizeof(RAWINPUTDEVICE))) {
        std::fputs("No se pudo registrar el teclado y el mouse con Raw Input.\n", stderr);
        return CODIGO_ERROR_AL_REGISTRAR;
    }

    // Bucle de mensajes: GetMessageW espera sin gastar procesador. Devuelve 0 con WM_QUIT (PostQuitMessage) y
    // un valor negativo si hay un error; en ambos casos se sale del bucle.
    MSG mensaje;
    while (GetMessageW(&mensaje, nullptr, 0, 0) > 0) {
        DispatchMessageW(&mensaje);
    }
    return 0;
}

}  // namespace captura

#endif  // _WIN32
