# Sesión 2026-11-23 · Segunda VOD de validación (DjMaRiiO, 22-nov)

Fase de medición. No hay cambios de código en `src/`, `tests/` ni `examples/`.
Los fixtures y los scripts de medición viven fuera del repo, en
`~/djmariio-run` (igual que `~/rubius-run`).

## Datos

- **VOD:** `2937369237`, directo del 22-nov-2026, 37.082 s (10 h 18 min), título
  «DIA 4 GTA 6 MODO HISTORIA…» (por fecha es el día 5; el 21-nov también se
  titula «DIA 4»). El encargo hablaba de ~8 h 45: la duración real es otra, y
  el VOD lo identifica la fecha, sin ambigüedad (un solo VOD ese día).
- **Referencia (`reference.json`):** los 10 clips más vistos cuyo vídeo es ese
  VOD, con `start_s` = offset del clip y `end_s` = offset + duración. Salieron
  10 utilizables, así que no hizo falta el orden de reserva (día 4, día 3).
  Dos clips creados ese día apuntaban a VODs antiguos y se descartaron. Vistas
  de 903 a 37: referencia débil. Offsets (s): 4.785, 8.874, 28.016, 4.781,
  34.757, 17.764, 5.643, 4.815, 20.172, 6.562. Tres clips (4.781, 4.785, 4.815)
  son el mismo momento, así que hay 8 momentos distintos.
- **Chat:** TwitchDownloaderCLI 1.56.5 con el vigilante de bloqueo (terminó en
  1,5 min al primer intento) -> `chat.json` canónico: 40.490 mensajes (2
  descartados por vacíos), de 22 s a 37.086 s, 0 minutos vacíos, máximo 15
  msg/s (el mismo tope que en Rubius, F1 de D15). Unos 3,7k mensajes por hora
  frente a 28-38k en Rubius.
- **Audio:** yt-dlp `Audio_Only`, bucle fail-loud, 950.937.088 B, 37.082 s
  (coincide con el VOD), 1 intento, unos 18 min.
- **Transcripción:** faster-whisper `small` int8 en CPU con la detección de
  bucles de `transcribe2.py` desde 0 s. 6.588 segmentos de 270 s a 37.062 s,
  41 bucles detectados y recortados, 0 rangos saltados, 4,5 h de CPU. Huecos
  mayores: 446 s (en 274 s), 386 s (20.741 s), 356 s (1.440 s), 293 s, 270 s,
  260 s. Ningún candidato quedó sin transcripción.
- **Cómo se obtuvo la referencia.** La API GraphQL pública de Twitch dio los
  VODs y los metadatos de cada clip (vídeo y offset); la paginación de la
  lista de clips falló con `IntegrityCheckFailed` y se paró ahí, sin rodeos.
  La lista ordenada por vistas se cargó en el navegador
  (`/djmariio/clips?range=7d`, 522 clips capturados) y se filtró por fecha de
  creación; un clip del VOD podía crearse después del directo, así que se
  resolvieron también los creados hasta el 23-nov (ninguno era de este VOD).

## Diagnóstico del chat (funciones del proyecto)

| | Rubius | DjMaRiiO |
| --- | --- | --- |
| Mensajes | 271.042 | 40.490 |
| Mediana msg/min (línea base) | 542 | 49 |
| Media msg/min | 527 | 65,5 |
| Multiplicador máximo | ×1,42 | ×13,78 |
| p99 del multiplicador | ×1,27 | ×10,29 |
| Mínimo de los 20 candidatos | ×1,27 | ×4,10 |

Este chat no es plano: es el caso contrario (poco volumen y muy a ráfagas).

## Arnés sin juez

Configuración fija (ventana 60 s, mediana global, separación 120 s, semilla 0,
2000 pruebas). Barra: aciertos@20 sobre el azar con p<0,05.

| K | Rubius | azar | p | DjMaRiiO | azar | p |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 3/10 | 0,46 | 0,0145 | 0/10 | 0,37 | 1,0000 |
| 10 | 4/10 | 0,94 | 0,0155 | 0/10 | 0,73 | 1,0000 |
| 20 | 5/10 | 1,84 | 0,0325 | 4/10 | 1,49 | 0,1019 |
| 40 | 7/10 | 3,50 | 0,0390 | 8/10 | 2,88 | 0,0060 |

**Veredicto en K=20: Rubius PASS, DjMaRiiO FAIL.**

Los 4 aciertos de DjMaRiiO en K=20 salen de solo **2 candidatos**: el de 4.685 s
(×4,9, 12.º del detector) cubre tres clips (el mismo momento) y el de 34.681 s
(×4,3) cubre uno. El arnés cuenta aciertos por clip, así que un momento con
varios clips pesa varias veces. Por momentos distintos serían 2/8 (el p-valor
no se ha recalculado así).

### Variante de línea base local

Mediana móvil centrada de ±1.800 s (parámetro fijado antes de medir), recalculada
cada 30 s, suelo de 1 msg/min, ordenación por multiplicador local; mismas
ventanas, separación y azar que el arnés. Script desechable, no es código del
repo. ±900 s y ±3.600 s son sensibilidades, solo informativas.

| K=20 | global | local ±1.800 s | local ±900 s | local ±3.600 s |
| --- | --- | --- | --- | --- |
| Rubius | 5/10 (p=0,0325) | 1/10 (p=0,835) | 0/10 (p=1,0) | 2/10 (p=0,564) |
| DjMaRiiO | 4/10 (p=0,1019) | 2/10 (p=0,403) | 1/10 (p=0,743) | 2/10 (p=0,403) |

En K=40 la local con ±900 s llega a 6/10 (p=0,093) en DjMaRiiO y no supera a la
global en ninguna otra celda. **La global gana en los dos fixtures.**

## Corrida con el juez

`gemini-3.5-flash-lite` (D19), mediante `src.main.run` (la ruta real del CLI)
con la referencia, y con el juez envuelto en un registrador que anota cada
juicio. 384 s, 21 llamadas (20 candidatos y 1 reintento).

- **CLI:** 5 momentos escritos, 1 error de candidato, **0/10** clips de
  referencia detectados.
- **Error:** el candidato 10:12:35-10:14:50 (36.755 s) falló las dos veces: el
  juez devolvió el mismo inicio, 36.754,1 s, 0,9 s antes de la ventana
  (`judgment ... is outside the candidate window`).
- Los 5 momentos: 05:20:46 (83), 03:54:58 (81), 00:51:10 (75), 01:45:32 (74),
  03:57:27 (73).

### Reparto de puntuaciones de los 20 candidatos juzgados

Totales de los 20 (el de 36.755 s cuenta una vez, con su primer juicio, aunque
sea inválido): 83, 81, 75, 74, 73, 72, 72, 72, 70, 69, 69, 65, 65, 60, 60, 59,
57, 56, 45, 35.

| Componente | mín | mediana | máx | valores más repetidos |
| --- | --- | --- | --- | --- |
| reaccion_chat (código) | 28,1 | ~29 | 30 | satura |
| contexto (0-25) | 5 | 15 | 20 | 15 (×8), 18 (×7), 20 (×2) |
| novedad (0-25) | 0 | 10 | 20 | 10 (×8), 5 (×5), 15 (×3) |
| gancho (0-20) | 2 | 14 | 16 | 12 (×7), 15 (×4), 14 (×4) |

(Los recuentos de componentes salen de las 21 llamadas, con los dos juicios del
candidato de 36.755 s.) Categorías: `reaccion` 11, `otro` 8, `secreto` 2.

Orden del juez (puntuación y, a igualdad, inicio más temprano):

| Pos. | Total | Inicio (s) | Mult. | Cat. | Clips ref. | Gancho |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 83 | 19.203 | ×4,9 | secreto | | El sonido de las chanclas cambia |
| 2 | 81 | 14.065 | ×11,2 | reacción | | Acabo de hacer el golpe y se celebra |
| 3 | 75 | 3.026 | ×4,4 | reacción | | El coche con el tuning extremo |
| 4 | 74 | 6.308 | ×4,2 | reacción | | No soy machista, rolando de Lucía |
| 5 | 73 | 14.241 | ×9,7 | secreto | | Sorteo de viaje a Miami y PSN (promo) |
| 6 | 72 | 4.685 | ×4,9 | reacción | **0, 3, 7** | La tremenda locura en directo |
| 7 | 72 | 7.085 | ×5,8 | otro | | Rockstar suelta códigos (drops) |
| 8 | 72 | 27.372 | ×4,7 | reacción | | El streamer se niega a hacer un clip |
| 9 | 70 | 19.030 | ×8,5 | reacción | | Jason está guapísimo |
| 10 | 69 | 19.969 | ×8,9 | reacción | | El chat decide la siguiente misión |
| 11 | 69 | 34.681 | ×4,3 | reacción | **4** | Mira este cambio climático |
| 12-13 | 65 | 14.482 y 36.755 | | otro / reacción | | Sorteo KitKat / ¿Espera, qué? (inválido) |
| 14-15 | 60 | 14.602 y 18.836 | | otro | | Sorteo PSN / uñas a Jason |
| 16-20 | 59, 57, 56, 45, 35 | | | | | gana viaje, árbol, Manchester, inusual, subtítulos |

Los dos candidatos que aciertan caen en las posiciones 6 y 11 del juez (72 y
69), con el corte de los 5 momentos en 73: el primero se queda a un punto.

## Hallazgos para el arquitecto

1. **Mezcla de veredictos.** En K=20, Rubius PASS (p=0,0325) y DjMaRiiO FAIL
   (p=0,1019). En K=40 pasan los dos (p=0,039 y p=0,006). El detector tiene
   señal, pero no ordena bien lo que hay dentro del top 20.
2. **El p-valor no es de fiar en ninguno de los dos sentidos.** Cuenta aciertos
   por clip, y la referencia tiene clips repetidos del mismo momento (tres de
   10 aquí) y vistas bajas (37-903). Los 4 aciertos son 2 candidatos.
3. **Línea base:** la local pierde en los dos fixtures, incluso con dos
   sensibilidades. Se queda la global (D15).
4. **Picos de promoción.** Cinco de los diez primeros picos del detector
   (14.065-14.602 s, ×9,7-×13,8) son una única tormenta de chat por el sorteo
   «KitKat/Miami» de unos 9 minutos, y otros son `!drops`. El juez los puntúa
   59-81 y uno (73) entra en el top 5. Un volumen alto de mensajes repetidos
   no es un momento clipeable.
5. **`reaccion_chat` satura.** Con ×4,1 o más, los 20 candidatos dan 28-30 de
   30 puntos: no discrimina en un chat a ráfagas. En Rubius pasa lo contrario
   (×1,3 da pocos puntos). La tabla de D10 no sirve para los dos tipos de chat.
6. **El juez deja un reparto estrecho:** 11 de 20 totales entre 65 y 75, y no
   distingue bien promoción de contenido (8 `otro` entre 56 y 72).
7. **Un fallo de validación sobre 20**, por un juicio 0,9 s fuera de la
   ventana, repetido igual en el reintento.
8. **Datos y proceso:** la duración real es 10 h 18; `.env` fija
   `GEMINI_MODEL=gemini-3.8-flash` (cuota de 20 al día) y un
   `python -m src.main` sin parámetros la usaría en lugar de la de D19.

## Decisión

El arquitecto resolvió la propuesta el 2026-11-24 en
[D20](../DECISIONS.md#d20--2026-11-24--segunda-vod-de-validación-línea-base-cerrada-y-alcance-de-la-fase-7):
la línea base global se queda, el criterio de D15 no se declara ni superado ni
fallado, la saturación de `reaccion_chat` se registra sin reescalar, y la fase 7
(arnés por momento, recorte del juez, medición de tormentas y corrida con K=40)
queda aprobada en su alcance.

## Tests

No se ha tocado código. La suite completa se ejecutó al cerrar la medición, en
la rama `fase-6/resiliencia-juez`: 653 passed.

## Errores

- **Corrección de una cifra mía sobre la referencia.** En un mensaje intermedio
  dije que había tres clips de la referencia a 6.114-6.607 s. Es falso: de ese
  rango solo el de 6.562 s está en la referencia (los otros eran de la lista
  ampliada de clips, no de los 10 elegidos). Lo que sí se repite son los tres
  clips de 4.781, 4.785 y 4.815 s (4.781-4.845 s con su duración): el mismo
  momento, y la causa de que los 4 aciertos de DjMaRiiO sean 2 candidatos.
  Corregido en «Datos» y en el hallazgo 2.
- El Mac estuvo con batería las primeras 2,5 h de la transcripción y bajó al
  7 % antes de enchufarlo; el proceso no se interrumpió.

## Lección

Con 10 clips de una VOD, un p-valor por clip no distingue «detector sin señal»
de «referencia repetitiva»: hay que medir por momento antes de decidir.
