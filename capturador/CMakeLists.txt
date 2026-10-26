# Capturador de eventos de entrada (C++17). Genera captura.exe en Windows.
# Uso:  cmake -S capturador -B capturador/build   y luego   cmake --build capturador/build --config Release
cmake_minimum_required(VERSION 3.16)
project(capturador LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(MSVC)
    # Enlaza el runtime de C++ dentro del programa: así no hace falta instalar nada en cada PC.
    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    add_compile_options(/W4 /WX /utf-8)
else()
    add_compile_options(-Wall -Wextra -Wpedantic -Werror)
endif()

# Núcleo que no depende de Windows: JSON, reglas de captura y escritura en stdout.
add_library(nucleo STATIC
    src/evento.cpp
    src/reglas_de_captura.cpp
    src/escritor.cpp
    src/simulador.cpp
)
target_include_directories(nucleo PUBLIC src)

add_executable(captura src/principal.cpp)
target_link_libraries(captura PRIVATE nucleo)

# La captura real con Raw Input solo existe en Windows.
if(WIN32)
    target_sources(captura PRIVATE src/raw_input_windows.cpp)
    target_link_libraries(captura PRIVATE user32)
endif()

# Pruebas unitarias: se ejecutan con  ctest --test-dir capturador/build -C Release
enable_testing()
add_executable(pruebas_unitarias pruebas/pruebas_unitarias.cpp)
target_link_libraries(pruebas_unitarias PRIVATE nucleo)
add_test(NAME unitarias COMMAND pruebas_unitarias)
