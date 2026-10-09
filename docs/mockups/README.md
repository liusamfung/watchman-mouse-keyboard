# Mockups de la interfaz (Tkinter)

Ocho pantallas para **Soporte TI** (RF23). El trabajador nunca ve ninguna. Están dibujadas con Tkinter/ttk (tema `clam`), así que la interfaz real debe parecerse a estas imágenes.

| Archivo | Pantalla | Qué hace |
|---|---|---|
| `P01_PanelPrincipal.png` | Panel principal | Estado de la captura, botones **Iniciar captura** y **Detener captura** (RF11), periféricos del equipo y alertas pendientes de envío. |
| `P02_Perifericos.png` | Periféricos | Teclados y mouse registrados en el equipo, con su desgaste frente al límite del fabricante, incluidos los retirados. |
| `P03_DetallePeriferico.png` | Detalle del periférico | Datos del periférico (etiqueta, modelo, VID:PID, límite, total acumulado) y teclas con mayor desgaste. |
| `P04_Sesiones.png` | Sesiones | Sesiones del equipo y total del día seleccionado, que es la suma de sus sesiones (RF12). |
| `P05_Analisis.png` | Análisis de uso | Mapa de calor por día y hora y patrones detectados (RF15, RF22). |
| `P06_Reportes.png` | Reportes | Opciones del reporte, vista previa y botón **Generar CSV** (RF14). |
| `P07_AlertasIncidentes.png` | Alertas e incidentes | Alertas de desgaste enviadas o pendientes, con umbral, intentos y próximo reintento (RF19, RF20), e incidentes recientes (RF9, RF10). |
| `P08_Configuracion.png` | Configuración | Límites por modelo, umbrales de aviso, destinatarios, servidor SMTP, cuenta remitente, cambio de contraseña, correo de prueba (RF18, RNF9, RNF10). |

Notas:

- Los datos que aparecen (TEC-0042, MOU-0108, PC-CONTAB-014, `soporte.ti@empresa.com`, etc.) son **de ejemplo**.
- El subtítulo de **P04** dice "desde que se enciende el equipo". El texto correcto es **"desde que se inicia sesión en Windows hasta que se apaga el equipo"**; corrígelo al implementar la pantalla.
- La contraseña del correo (P08) se guarda con `keyring` en el Administrador de credenciales de Windows, nunca en la base de datos ni en el código.
- Ninguna pantalla ejecuta SQL directamente: todas leen y escriben a través del módulo de repositorio compartido.
- Los flujos que recorren estas pantallas están en `docs/flujos/flujo-soporte-ti.puml` y `docs/flujos/flujo-trabajador.puml`.
