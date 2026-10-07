# Especificación · App Monitoreo Sanitario Frambuesa

2026-10-07 · @Joaquín

## Resumen y alcance

Construimos una app Android (APK) para registrar y seguir enfermedades, plagas y malezas en frambuesa, con puntos georreferenciados que se pueden revisitar. El piloto corre en **El Amanecer** (196 ha plantadas, 4 equipos de riego, 40 sectores en 62 polígonos) con **2 monitores administradores**.

Entra en el piloto:

- Mapa del predio con la sectorización sector · equipo del plano DWG, polígonos separados por variedad y por partes no contiguas.
- Observaciones con GPS, hora, clima, fotos y nota, según el protocolo de cada organismo (catálogo v1: 5 enfermedades, 5 plagas, 10 malezas).
- Puntos fijos para revisitar focos, trampas con sus revisiones y un registro simple de aplicaciones.
- Panel de temporada, exportación a Excel y funcionamiento completo sin señal.
- Sincronización entre teléfonos del equipo cada minuto cuando hay señal.

Queda fuera del piloto: iPhone, otros cultivos y predios (el modelo de datos ya los admite), edición de protocolos desde la app y lectura automática del BBCH desde la app de fenología (ver Fase 2).

## Stack y decisiones técnicas

La app se escribe en Python con **Kivy + KivyMD**, el mismo stack de la app de fenología, y se compila a APK con Buildozer dentro de WSL en tu Windows. Así ambas apps hermanas comparten herramienta, forma de compilar y parte del código. No hay SDK oficial de Firebase para apps Python en el teléfono, por lo que la app guarda todo en una base local y sincroniza con Firebase por su API REST.

| Componente | Elección | Por qué |
|---|---|---|
| Lenguaje y UI | Python + Kivy + KivyMD | Igual que la app de fenología; KivyMD da componentes Material para teléfono |
| App Android | Buildozer (python-for-android) en WSL con Ubuntu | Genera el APK firmado; mismo entorno que ya usas para fenología |
| Mapa | `kivy_garden.mapview` con imagen satelital | Marcadores y polígonos del predio; guarda en disco las teselas vistas |
| GPS | `plyer.gps` con permisos de Android | Ubicación de alta precisión para el punto y el sector |
| Fotos | Cámara de Android vía `pyjnius` (intent) | Más confiable que la cámara de `plyer` en teléfonos actuales |
| Datos en el teléfono | SQLite (módulo `sqlite3`) | Fuente de verdad local: la app funciona entera sin señal |
| Inicio de sesión | Firebase Authentication por API REST, correo y contraseña creados por el administrador | Funciona en Python; Google Sign-In queda para fase 2 |
| Nube | Cloud Firestore por API REST, con `requests` | Centraliza los datos del equipo; un proceso de sincronización sube lo pendiente y baja lo nuevo |
| Fotos en la nube | Cloud Storage por API REST, subida en cola | Se comprimen con Pillow (WebP, 1600 px y miniatura) antes de subir |
| Sector por GPS | Punto-en-polígono en Python puro | Sin librerías nativas que compliquen la compilación |
| Gráficos | `kivy_garden.graph` o dibujo propio en el canvas de Kivy | Curvas de la ficha y del panel sin depender de matplotlib |
| Clima | API de Open-Meteo con `requests` | Temperatura, humedad, viento y lluvia de 24 h; se completa al sincronizar si no había señal |
| Exportar | `openpyxl` + compartir de Android | Excel por temporada, organismo o sector |
| Distribución | Firebase App Distribution | Los monitores reciben cada versión por enlace, sin Play Store |

Dos cosas se prueban al inicio de la etapa 2, antes de construir encima. Primero, el mapa sin señal: mapview guarda en disco las teselas vistas, pero ese caché no se controla (Kivy MapView); la app recorrerá una vez el predio con señal para precargarlo, si los términos de Esri lo permiten. Segundo, GPS y cámara en los teléfonos reales del equipo. Si el mapa no queda disponible sin señal, se ve la vista esquemática de los polígonos.

Tres consecuencias de usar Python que cambian el diseño respecto de la versión web:

- **Sincronización propia.** Sin el SDK de Firebase no hay caché automático ni cambios en vivo; la app consulta cambios cada 60 segundos con señal y al abrirse.
- **Cuentas por correo.** El administrador crea las cuentas de los monitores en la consola de Firebase.
- **Compilación en WSL.** El proyecto debe vivir dentro del disco de Linux de WSL, no en la carpeta de Windows, y el APK se copia de vuelta a Windows para instalarlo (Buildozer).
- **APK más pesado.** Incluye el intérprete de Python, así que la primera instalación descarga más megas.

## Apps hermanas

Las dos apps se compilan y actualizan por separado, pero usan el mismo proyecto Firebase: comparten usuarios, predios, sectores y temporadas, y cada una tiene sus propias colecciones.

> Diagrama "arquitectura · 2 apps, 1 proyecto Firebase": disponible en el documento original (https://claude.ai/artifact/MsyJSB5BLMsmUYMmCecq4h).

En el piloto solo la app de sanidad usa Firebase; la de fenología se conecta en la fase 2, y desde ahí cada registro sanitario lee el BBCH de esa semana sin exportar nada.

## Modelo de datos en Firestore

Cada observación es un documento independiente que guarda una copia de todo su contexto (sector, variedad, BBCH, clima, versión del protocolo). Así un registro sigue siendo válido aunque después cambien los umbrales o la sectorización.

| Colección | Qué guarda | Campos clave |
|---|---|---|
| `usuarios/{uid}` | Personas (compartida con apps hermanas) | nombre, email, creadoEn |
| `predios/{predioId}` | Predio y quién accede (compartida) | nombre, cultivo, ha, centro, miembros {uid: admin / monitor} |
| `predios/{p}/sectores/{sectorId}` | Sectorización (compartida) | equipo, sector, variedad, ha, hileras, geometría como texto GeoJSON |
| `temporadas/{temporadaId}` | Temporadas (compartida) | predioId, inicio, fin, etiqueta "2026–27" |
| `catalogos/{cultivo-version}/organismos/{id}` | Protocolos y umbrales | grupo, nombre, científico, método, campos, estados, umbral {cerca, sobre, unidad}, ventana BBCH |
| `predios/{p}/puntos/{puntoId}` | Puntos fijos y trampas | tipo (fijo / trampa), lat, lng, sectorId, organismoId, último estado, última visita, activo |
| `predios/{p}/observaciones/{obsId}` | Cada registro de campo | puntoId?, organismoId, versión de catálogo, sectorId, variedad, lat, lng, precisión m, fecha-hora del teléfono y del servidor, monitorUid, bbch + fuente, clima {}, valores {}, resultado {indicador, valor, estado}, estados biológicos, fotos [], nota |
| `predios/{p}/revisionesTrampa/{id}` | Lecturas de trampa | trampaId, fecha-hora, machos, hembras, total, cambio de cebo, cambio de piso, foto |
| `predios/{p}/aplicaciones/{id}` | Aplicaciones realizadas | fecha, sectores [], producto, dosis + unidad, organismos objetivo [], nota, uid |

Reglas de diseño para Code:

- Los IDs se generan en el teléfono (UUID), para crear registros sin señal.
- Firestore no admite listas dentro de listas: la geometría va como texto GeoJSON, y la app trae una copia empaquetada en `sectores-el-amanecer.json`.
- Nada se borra físicamente: un campo `eliminado` oculta el registro y queda la auditoría (`creadoPor`, `editadoPor`, fechas).
- El objeto `clima` guarda tempC, humedad %, viento km/h, lluvia 24 h mm, fuente (api | manual), cielo y hoja mojada.

## Catálogo v1: organismos, protocolos y umbrales

El catálogo v1 es la propuesta de partida para el piloto: los umbrales son valores de referencia para ajustar con datos propios, y en el piloto solo se leen. Vive como datos (`catalogo-frambuesa-v1.json`), no en el código, para que agregar un organismo o un cultivo no requiera programar.

| Organismo | Método por punto | Indicador | Cerca | Sobre umbral | Estados | Activo en |
|---|---|---|---|---|---|---|
| Pudrición gris (*Botrytis cinerea*) | 100 flores o frutos | % incidencia | 3% | 5% | sin síntoma, lesión, esporulando, momificado | BBCH 57–89 |
| Pudrición de raíces (*Phytophthora* spp.) | 20 plantas seguidas en la hilera | % plantas sintomáticas + vigor 0–4 | 1 planta | 5% | decaimiento, marchitez, muerta | todo el año |
| Agalla del cuello (*Agrobacterium tumefaciens*) | 20 plantas, base y corona | % plantas con agalla | 1 planta | 5% | agalla joven, agalla leñosa | todo el año |
| Tizón de la caña (*Leptosphaeria* / *Didymella*) | 20 cañas | % cañas con lesión | 5% | 10% | lesión inicial, anillamiento parcial, anillamiento total | todo el año |
| Roya (*Pucciniastrum americanum*) | 50 hojas | % hojas con pústulas + severidad 0–5 | 5% | 10% | uredo (anaranjado, activo), telio (oscuro, resistencia) | BBCH 31–95 |
| Mosca de alas manchadas (*Drosophila suzukii*) | Trampa semanal (vinagre + levadura) y 30 frutos desde pinta | capturas por trampa · % frutos con larva | 1 captura | 5 capturas · cualquier larva | huevo, larva, pupa, adulto | trampa todo el año · fruta BBCH 81+ |
| Cabrito (*Aegorhinus superciliosus*) | Golpeteo de 10 plantas + revisión de cuello | adultos por 10 plantas · % plantas con daño | 1 adulto | 3 adultos | larva, adulto | todo el año, marcar borde o interior |
| Burrito (*Otiorhynchus rugosostriatus*) | Igual que cabrito, revisión nocturna o refugio | adultos por 10 plantas · % plantas con daño | 1 adulto | 3 adultos | larva, adulto | todo el año |
| Arañita bimanchada (*Tetranychus urticae*) | 25 foliolos del tercio medio, lupa 10× | % foliolos con móviles + móviles por foliolo | 7% | 10% | huevo, ninfa, adulto · depredadores sí/no | BBCH 31–95 |
| Enrollador (*Proeulia* spp.) | Trampa de feromona semanal + 25 brotes o racimos | machos por trampa · % brotes con larva | 5 machos | 10 machos · 2% brotes | huevo, larva, pupa, adulto · Biofix | BBCH 31–89 |
| Malezas (las 10 especies de la lista) | Cuadrante de 0,25 m² en hilera y entrehilera | clase de cobertura <5, 5–25, 25–50, 50–75, >75% | 5–25% | >25% o semillación | plántula, vegetativa, floración, semillación | todo el año |

Dos reglas especiales: la zarzamora (*Rubus ulmifolius*) pasa a sobre umbral con cualquier cobertura, porque es hospedera de *D. suzukii* en Chile; y en malezas el estado "semillación" fuerza sobre umbral aunque la cobertura sea baja.

## Pantallas y flujos

Son las 6 pantallas del boceto, con dos cambios acordados: el mapa queda lo más limpio posible y cada observación registra hora y clima.

1. **Mapa (inicio).** Solo polígonos, puntos, tu ubicación y el botón "+". Filtros y leyenda quedan detrás de un botón pequeño; el estado de sincronización es un punto de color en la esquina. Al tocar un punto sube una tarjeta con organismo, sector, último valor y los botones Ver historia y Revisitar.
1. **Nueva observación.** Al abrirse:
   - toma GPS de alta precisión y deduce sector · equipo · variedad por punto-en-polígono;
   - registra hora del teléfono (y la del servidor al sincronizar);
   - pide el clima a Open-Meteo con esas coordenadas (temperatura, humedad, viento, lluvia 24 h) y lo muestra editable;
   - agrega a mano cielo (despejado, nublado, lluvia) y hoja mojada sí/no, útil para Botrytis;
   - BBCH: en el piloto se elige con un selector rápido que recuerda el último valor del sector.
   Luego se elige grupo y organismo, y el formulario muestra solo los campos de su protocolo, calcula el indicador en vivo y lo compara con el umbral. Cierra con estados biológicos, fotos, nota y el interruptor "Dejar como punto fijo".
1. **Ficha del punto.** Historia del punto: curva del indicador con línea de umbral y aplicaciones superpuestas, lista de visitas con foto, monitor y BBCH, y un botón "Llévame" con distancia y rumbo hasta el punto.
1. **Trampas.** Lista por especie con última lectura, tendencia de 5 semanas y avisos de cebo o piso vencido. "Registrar revisión" pide machos, hembras, cambio de cebo y piso.
1. **Panel de temporada.** Indicadores por semana para los organismos elegidos, franja BBCH, lista de lo que está sobre umbral, registrar aplicación y exportar a Excel.
1. **Protocolos y equipo.** Catálogo de solo lectura en el piloto, lista de miembros e invitación por correo con rol.

## Reglas de negocio

El color de cada punto sale de su última observación comparada con el umbral del catálogo, salvo que lleve más de 14 días sin visita.

| Estado | Regla | Color |
|---|---|---|
| Sobre umbral | Indicador ≥ umbral, o una regla especial (semillación, zarzamora, larva en fruta) | rojo oscuro `#9E2A22` |
| Cerca del umbral | Indicador ≥ valor "cerca" y bajo el umbral | ámbar `#D69A2D` |
| Bajo umbral | Indicador bajo el valor "cerca" | verde `#3E8A57` |
| Sin visitar | Última visita hace más de 14 días (configurable) | gris `#9AA096`, con el color anterior como borde |

Otras reglas:

- Cuando un protocolo tiene dos indicadores (por ejemplo, trampa y fruta), el punto toma el peor de los dos.
- Un sector toma el peor estado de sus puntos de los últimos 14 días; así se pinta en el panel.
- Fuera de su ventana BBCH, un organismo baja al final de la lista rápida, pero se puede registrar igual.
- Trampas: aviso de cebo a los 7 días, de piso pegajoso a los 14 y de cápsula de feromona a los 30. Los tres plazos son configurables.
- Las semanas se cuentan de lunes a domingo y las temporadas se leen de la colección compartida `temporadas`, igual que en la app de fenología.
- Una aplicación se dibuja en la curva de todos los puntos de los sectores donde se aplicó.

## Sin conexión, sincronización y permisos

Todo se puede hacer sin señal; lo único que espera a la conexión es subir fotos, pedir el clima y bajar los registros de los demás.

**Sin conexión y sincronización**

- Todo se escribe primero en SQLite, con una marca `pendiente`. Un proceso en segundo plano sube lo pendiente a Firestore cuando hay señal y baja lo que otros registraron desde la última sincronización (consulta por `actualizadoEn`).
- Las observaciones solo se agregan, así que casi no hay conflictos; en ediciones gana el cambio con `actualizadoEn` más reciente.
- Las fotos se guardan comprimidas en el almacenamiento de la app y una cola las sube al volver la red. Mientras tanto la observación muestra la copia local.
- Si no hubo clima al registrar, la app lo completa después con el dato horario de Open-Meteo para esa hora y lugar, y marca la fuente.
- El indicador de sincronización muestra cuántos registros y fotos faltan por subir; la app avisa antes de cerrar sesión si queda algo pendiente.

**Roles y reglas de seguridad**

| Acción | Monitor | Administrador |
|---|---|---|
| Ver datos del predio | sí | sí |
| Crear observaciones, revisiones de trampa y puntos | sí | sí |
| Editar o anular un registro | solo propio, dentro de 24 h | cualquiera |
| Registrar aplicaciones | no | sí |
| Invitar miembros y cambiar roles | no | sí |
| Editar catálogo | no | no en el piloto |

Estas reglas se escriben en `firestore.rules` y `storage.rules`, con pruebas en el emulador de Firebase: un usuario solo lee y escribe en predios donde figura en `miembros`.

## Distribución del APK

Cada versión se compila como APK firmado y se publica en Firebase App Distribution, que manda un correo con el enlace de instalación al grupo "monitores-el-amanecer".

1. Code genera una llave de firma (keystore) una sola vez. Se guarda fuera del repositorio y con respaldo: sin ella no se puede actualizar la app instalada.
1. Para cada versión: subir `versionCode`, compilar con buildozer android release y subirlo a App Distribution con notas de cambios en español.
1. En el teléfono, la primera vez se permite "instalar apps de origen desconocido" para la app de correo o el navegador. Las versiones siguientes se instalan encima sin perder datos.
1. La app lee `config/app` en Firestore (versión mínima y última disponible) y muestra un aviso con el enlace cuando hay una versión nueva.

## Plan de trabajo en Code

Son 8 etapas; cada una termina con un APK que se instala y se prueba en terreno antes de pasar a la siguiente. En Code conviene trabajar una etapa por sesión, pegando esta especificación como `SPEC.md` en la raíz del repositorio.

1. **Base del proyecto.** Repositorio, proyecto Kivy + KivyMD con su buildozer.spec, base SQLite, conexión a Firebase por REST, inicio de sesión con correo y primer APK enviado por App Distribution.
   - Listo cuando: los 2 monitores instalan el APK desde el correo y entran con su cuenta.
1. **Mapa y sectores.** Cargar `sectores-el-amanecer.json`, mapa satelital y esquemático, GPS, deducir sector · equipo · variedad, descarga de teselas del predio.
   - Listo cuando: en 10 puntos de prueba en terreno el sector deducido coincide con el plano, y el mapa abre en modo avión.
1. **Observación desde el catálogo.** Formulario armado desde `catalogo-frambuesa-v1.json`, cálculo de indicador y estado, hora, clima, BBCH manual, fotos comprimidas y nota.
   - Listo cuando: los 20 organismos se registran de punta a punta y los cálculos tienen pruebas automáticas.
1. **Sincronización y seguridad.** Proceso de sincronización SQLite ↔ Firestore, cola de fotos, indicador de pendientes, reglas de Firestore y Storage con pruebas en el emulador.
   - Listo cuando: un registro hecho en modo avión en un teléfono aparece en el otro menos de 2 minutos después de reconectar.
1. **Puntos fijos y ficha.** Colores de estado en el mapa, tarjeta del punto, ficha con curva y visitas, botón Llévame.
   - Listo cuando: se puede volver a un foco desde el mapa y registrar la revisita sobre el mismo punto.
1. **Trampas y aplicaciones.** Alta de trampas, revisiones, avisos de cebo, piso y cápsula, registro de aplicaciones.
   - Listo cuando: una semana de lecturas de trampas reales queda registrada y con sus avisos.
1. **Panel y exportación.** Curvas semanales, franja BBCH, lista sobre umbral, Excel compartible.
   - Listo cuando: el Excel abre en el computador con una fila por observación y todas sus columnas.
1. **Piloto en terreno.** Dos semanas de uso real en El Amanecer, lista de ajustes y versión 1.0.
   - Listo cuando: los monitores dejan el registro en papel.

## Lo que debes preparar antes de empezar

Con esta lista resuelta, la etapa 1 se puede hacer en una sesión de Code.

- Cuenta Google dueña del proyecto (idealmente de la empresa, no personal) y el proyecto creado en la consola de Firebase.
- Activar el plan Blaze de pago por uso: los buckets nuevos de Cloud Storage lo exigen desde septiembre de 2024, aunque mantienen un nivel gratuito (Firebase). Poner una alerta de presupuesto baja, por ejemplo USD 5.
- Elegir región de la base de datos: `southamerica-west1` (Santiago) da menor latencia; una región de EE. UU. aprovecha mejor el nivel gratuito de Storage.
- WSL con Ubuntu y Buildozer en tu Windows, el mismo entorno donde compilas la app de fenología, con Code trabajando dentro de WSL.
- Correos de los 2 monitores y sus teléfonos Android (Android 8 o superior) a mano para probar.
- Un repositorio en GitHub para el código.
- Nombre e ícono de la app (por ejemplo, "Sanidad · El Amanecer").
- Los dos archivos de datos que te entrego con esta especificación: `sectores-el-amanecer.json` y `catalogo-frambuesa-v1.json`.
   - Completar la variedad de cada sector en `sectores-el-amanecer.json`: el plano solo la trae para el Sector 1 · Equipo 1 (Meeker y Cascade Harvest).

## Fase 2

La fase 2 conecta las apps hermanas y abre la app a más cultivos y personas.

- Migrar la app de fenología al mismo proyecto Firebase: BBCH automático en cada observación y datos compartidos con usuarios elegidos, sin exportar.
- Edición del catálogo desde la app por administradores, con versiones (v2, v3) que no alteran registros antiguos.
- Rol "monitor que solo registra" en uso y más predios o cultivos (cranberry, arándano).
- Avisos al teléfono cuando un punto pasa a sobre umbral.
- Versión para iPhone desde el mismo código (con Kivy requiere un Mac para compilar) e inicio de sesión con Google.

## Fuentes

- SAG, Instructivo técnico para el monitoreo y análisis de Drosophila suzukii
- Frutas de Chile, Guía de monitoreo y manejo de Drosophila suzukii
- U. de Valladolid, Tesis sobre monitoreo de D. suzukii en La Araucanía (cebo SAG de vinagre y levadura)
- UPL, Manual de trampas Pherocon para Proeulia
- INIA Uruguay, Manejo de trampas de feromona
- NC State Extension, Twospotted spider mite (umbral de referencia en frutilla)
- IOBC-WPRS, Arañita en frambuesa bajo túnel (umbral empírico de 10% de foliolos)
- Portalfrutícola / INIA, Cabritos en berries
- Firebase, Cambios de Cloud Storage anunciados en septiembre de 2024

- Buildozer, Instalación (Windows mediante WSL)
- Kivy, MapView (caché de teselas en disco)

Los umbrales de enfermedades, cabrito, burrito, enrollador y malezas son propuesta propia para el piloto, sin una fuente local que los respalde.
