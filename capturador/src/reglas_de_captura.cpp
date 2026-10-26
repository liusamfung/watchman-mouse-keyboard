#include "reglas_de_captura.h"

#include <cstdio>

namespace captura {

namespace {
// Códigos virtuales de Windows (winuser.h). Se escriben aquí para no depender de windows.h.
const char* nombre_especial(unsigned codigo) {
    switch (codigo) {
        case 0x08: return "RETROCESO";
        case 0x09: return "TAB";
        case 0x0D: return "ENTER";
        case 0x10: return "SHIFT";
        case 0x11: return "CTRL";
        case 0x12: return "ALT";
        case 0x13: return "PAUSA";
        case 0x14: return "BLOQ_MAYUS";
        case 0x1B: return "ESC";
        case 0x20: return "ESPACIO";
        case 0x21: return "RE_PAG";
        case 0x22: return "AV_PAG";
        case 0x23: return "FIN";
        case 0x24: return "INICIO";
        case 0x25: return "FLECHA_IZQUIERDA";
        case 0x26: return "FLECHA_ARRIBA";
        case 0x27: return "FLECHA_DERECHA";
        case 0x28: return "FLECHA_ABAJO";
        case 0x2C: return "IMPR_PANT";
        case 0x2D: return "INSERTAR";
        case 0x2E: return "SUPR";
        case 0x5B: return "WIN_IZQUIERDA";
        case 0x5C: return "WIN_DERECHA";
        case 0x5D: return "MENU";
        case 0x6A: return "NUM_MULTIPLICAR";
        case 0x6B: return "NUM_SUMAR";
        case 0x6D: return "NUM_RESTAR";
        case 0x6E: return "NUM_PUNTO";
        case 0x6F: return "NUM_DIVIDIR";
        case 0x90: return "BLOQ_NUM";
        case 0x91: return "BLOQ_DESPL";
        case 0xBA: return "OEM_1";
        case 0xBB: return "MAS";
        case 0xBC: return "COMA";
        case 0xBD: return "MENOS";
        case 0xBE: return "PUNTO";
        case 0xBF: return "OEM_2";
        case 0xC0: return "OEM_3";
        case 0xDB: return "OEM_4";
        case 0xDC: return "OEM_5";
        case 0xDD: return "OEM_6";
        case 0xDE: return "OEM_7";
        case 0xE2: return "OEM_102";
        default: return nullptr;
    }
}
}  // namespace

std::string nombre_de_tecla(unsigned codigo_virtual) {
    if (codigo_virtual >= 0x41 && codigo_virtual <= 0x5A) {  // A-Z
        return std::string(1, static_cast<char>(codigo_virtual));
    }
    if (codigo_virtual >= 0x30 && codigo_virtual <= 0x39) {  // 0-9
        return std::string(1, static_cast<char>(codigo_virtual));
    }
    if (codigo_virtual >= 0x60 && codigo_virtual <= 0x69) {  // teclado numérico
        return "NUM_" + std::to_string(codigo_virtual - 0x60);
    }
    if (codigo_virtual >= 0x70 && codigo_virtual <= 0x87) {  // F1-F24
        return "F" + std::to_string(codigo_virtual - 0x70 + 1);
    }
    if (const char* nombre = nombre_especial(codigo_virtual)) {
        return nombre;
    }
    char texto[16];
    std::snprintf(texto, sizeof texto, "VK_%02X", codigo_virtual & 0xFFU);
    return texto;
}

bool FiltroRepeticion::es_pulsacion_nueva(unsigned codigo_virtual) {
    if (codigo_virtual >= presionadas_.size()) return true;  // código fuera de rango: no se filtra
    if (presionadas_.test(codigo_virtual)) return false;
    presionadas_.set(codigo_virtual);
    return true;
}

void FiltroRepeticion::registrar_liberacion(unsigned codigo_virtual) {
    if (codigo_virtual < presionadas_.size()) presionadas_.reset(codigo_virtual);
}

int AcumuladorRueda::agregar(int unidades) {
    resto_ += unidades;
    const int pasos = resto_ / UNIDADES_POR_PASO;  // la división entera trunca hacia cero
    resto_ -= pasos * UNIDADES_POR_PASO;
    return pasos;
}

bool LimitadorMovimiento::permitir(Reloj::time_point ahora) {
    if (hay_ultimo_ && ahora - ultimo_ < intervalo_) return false;
    ultimo_ = ahora;
    hay_ultimo_ = true;
    return true;
}

}  // namespace captura
