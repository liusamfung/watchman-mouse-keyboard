# Diagramas de Actividades — Caso 4

```plantuml
@startuml
Alice -> Bob: hello
Bob --> Alice: hi
@enduml
```

---

## Diagrama 1 — Captura de eventos (RF1, RF4, RF5, RF6, RF7, RF11)

```plantuml
@startuml Diagrama1_CapturaEventos
title Diagrama 1 — Captura de eventos (RF1, RF4, RF5, RF6, RF7, RF11)

actor "Teclado / Mouse" as HW
participant "Módulo C++\n(bajo nivel)" as CPP
boundary "stdout" as OUT

loop mientras la captura esté activa
    HW -> CPP : evento de hardware
    activate CPP
    CPP -> CPP : identificar tipo de evento (RF1)
    alt evento de teclado
        CPP -> CPP : capturar pulsación o liberación de tecla (RF5)
    else evento de mouse
        CPP -> CPP : capturar movimiento, clic o scroll (RF6)
        CPP -> CPP : obtener coordenadas X/Y del cursor (RF7)
    end
    CPP -> CPP : serializar el evento a formato JSON (RF4)
    CPP -> OUT : escribir evento en stdout (RF4)
    deactivate CPP
end

note over CPP
  El bucle se repite hasta que el módulo
  Python solicita detener la captura (RF11)
end note
@enduml

```

---

## Diagrama 2 — Comunicación y control (RF2, RF3, RF9, RF10, RF11)

```plantuml
@startuml Diagrama2_ComunicacionControl
title Diagrama 2 — Comunicación y control (RF2, RF3, RF9, RF10, RF11)

actor Usuario
participant "Módulo Python\n(alto nivel)" as PY

Usuario -> PY : solicitar inicio de captura (RF11)
activate PY
PY -> CPP ** : ejecutar binario C++ como subproceso (RF2)
activate CPP

par lectura continua del flujo
    loop hasta que se detenga la captura
        CPP -> PY : evento (JSON por stdout)
        PY -> PY : leer flujo stdout en tiempo real (RF3)
    end
else vigilancia de caída del proceso
    loop hasta que se detenga la captura
        PY -> PY : ¿el proceso C++ finalizó inesperadamente? (RF10)
        opt sí, finalizó
            PY -> PY : registrar error de comunicación (RF9)
        end
    end
end

Usuario -> PY : solicitar detener captura (RF11)
PY -> CPP !! : detener y finalizar el subproceso C++ (RF11)
deactivate PY
@enduml

```

---

## Diagrama 3 — Procesamiento y almacenamiento (RF8, RF9, RF13)

```plantuml
@startuml Diagrama3_ProcesamientoAlmacenamiento
title Diagrama 3 — Procesamiento y almacenamiento (RF8, RF9, RF13)

participant "Módulo Python\n(alto nivel)" as PY
database "SQLite" as DB

loop mientras la captura esté activa
    PY -> PY : recibir evento JSON desde stdout (RF3)
    alt evento válido
        PY -> PY : asignar identificador único al evento (RF8)
        PY -> DB : almacenar evento (RF13)
        activate DB
        DB --> PY : ok
        deactivate DB
    else evento inválido
        PY -> DB : registrar evento inválido o erróneo (RF9)
    end
end
@enduml
```

---

## Diagrama 4 — Generación de reportes y análisis (RF12, RF14, RF15)

```plantuml
@startuml Diagrama4_ReportesAnalisis
title Diagrama 4 — Generación de reportes y análisis (RF12, RF14, RF15)

actor Usuario
participant "Módulo Python\n(alto nivel)" as PY
database "SQLite" as DB

Usuario -> PY : solicitar generación de reporte
activate PY
PY -> DB : consultar eventos almacenados
activate DB
DB --> PY : registros solicitados
deactivate DB
PY -> PY : calcular tiempo de actividad de teclado y mouse (RF12)
PY -> PY : analizar patrones de uso del teclado y mouse (RF15)
PY -> PY : generar reporte en formato CSV (RF14)
PY --> Usuario : reporte generado
deactivate PY
@enduml

```
