# watchman-mouse-keyboard

Capturador y auditor de eventos de entrada (teclado y mouse) para equipos Windows, con control de desgaste de periféricos y alertas a Soporte TI.

Proyecto grupal del curso **Programación de Interfaces** (UTP), Caso 4.

**Equipo:** Liu Sam Fung (Scrum Master), Aldair Lozano, Marcos Matos y José Espinoza.

## ¿Qué hace?

El sistema se instala en cada PC de trabajo y, de forma transparente para el trabajador:

- Detecta qué teclado o mouse generó cada evento, usando su VID/PID.
- Cuenta el desgaste de cada periférico: pulsaciones por tecla, clics por botón y pasos de scroll.
- Envía un correo a Soporte TI cuando un periférico llega al **90 %** y al **100 %** de la vida útil que garantiza el fabricante.
- Guarda eventos y sesiones, genera reportes en CSV y muestra un mapa de calor del uso por hora y día.

El objetivo es prevenir fallos: que el trabajador no se quede sin teclado o mouse, y que Soporte TI no tenga que revisar cada PC a mano.

**Privacidad:** el sistema nunca guarda el orden ni la secuencia de las teclas. Solo almacena contadores agregados por día.
