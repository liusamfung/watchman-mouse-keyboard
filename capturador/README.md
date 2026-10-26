# Capturador (C++)

Programa que escribe un evento JSON por línea en `stdout`, con el formato de
[`docs/arquitectura/contrato-json.md`](../docs/arquitectura/contrato-json.md). No toca la base de datos: eso lo hace el servicio de Python.

## Estado

| Parte | Estado |
|---|---|
| Núcleo portable (JSON, nombres de tecla, filtro de repetición, pasos de rueda, límite de movimiento, escritura en stdout) | Hecho y probado en macOS |
| Modo `--simulado` (eventos inventados, en cualquier sistema) | Hecho |
| Captura real con Raw Input | Pendiente, solo se puede probar en Windows |

## Archivos

| Archivo | Para qué sirve |
|---|---|
| `src/evento.*` | El evento y su conversión a JSON; la hora local con milisegundos |
| `src/reglas_de_captura.*` | Nombre de la tecla, filtro de repetición (decisión 3), pasos enteros de la rueda (decisión 5) y límite de movimientos |
| `src/escritor.*` | Escribe una línea y vacía el búfer; ajusta stdout para que `\n` no cambie en Windows |
| `src/simulador.*` | Genera eventos inventados |
| `src/principal.cpp` | Lee las opciones y arranca el modo que corresponda |
| `pruebas/pruebas_unitarias.cpp` | Pruebas del núcleo, sin bibliotecas externas |

## Compilar y probar

En cualquier sistema con CMake (en Windows, con Visual Studio):

```bash
cmake -S capturador -B capturador/build
cmake --build capturador/build --config Release
ctest --test-dir capturador/build -C Release
```

Sin CMake, en macOS o Linux (es lo que usan las pruebas de Python):

```bash
c++ -std=c++17 -Icapturador/src capturador/src/*.cpp -o captura
./captura --simulado --cantidad 10 --semilla 7
```

Las pruebas de Python (`.venv/bin/python -m pytest`) compilan este programa y lo revisan con el validador real.

## Opciones

| Opción | Efecto |
|---|---|
| `--simulado` | Escribe eventos inventados en lugar de leer el teclado y el mouse |
| `--cantidad N` | Con `--simulado`, cantidad de líneas; sin este dato no termina |
| `--intervalo-ms N` | Con `--simulado`, espera entre líneas |
| `--semilla N` | Con `--simulado`, repite la misma secuencia (en el mismo sistema y compilador) |
| `--ayuda` | Muestra las opciones |

Códigos de salida: `0` terminó bien o el servicio cerró la lectura; `2` opción inválida o captura real no disponible en este sistema.
