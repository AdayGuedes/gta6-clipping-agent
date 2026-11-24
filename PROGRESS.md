# PROGRESS

**Fase actual:** v1 abierta, fase 7 (instrumento de medición y corrida del juez
a K=40, alcance en [D20](docs/DECISIONS.md)) implementada y en PR. Las fases 5 y
6 están fusionadas y cerradas (PR #7 y #8). El v0 está cerrado: la prueba con un VOD real de
8:34:30 ([nota de la fase 4](docs/sessions/2026-11-19-fase-4.md)) dio 0
candidatos y 0/10 clips de referencia, porque el chat de ese directo es
demasiado plano para el umbral ×1,5 (máximo ×1,31). El detector (ventana
deslizante de 60 s, top-K y línea base global) queda decidido en
[D15](docs/DECISIONS.md) y D20.

## Fases v0

- [x] Fase 0 estructura y docs (2026-11-17, [nota](docs/sessions/2026-11-17-fase-0.md))
- [x] Fase 1 modelos e ingesta desde ficheros locales
      (transcripción y chat en JSON/CSV -> interfaces internas)
      (2026-11-17, [nota](docs/sessions/2026-11-17-fase-1.md))
- [x] Fase 2 generador de candidatos por picos de chat
      (2026-11-17, [nota](docs/sessions/2026-11-17-fase-2.md))
- [x] Fase 3 juez LLM tras una interfaz (Gemini, tier gratuito) y salida JSON
      validada (2026-11-19, [nota](docs/sessions/2026-11-19-fase-3.md))
- [x] Fase 4 CLI de punta a punta y prueba con datos reales
      - [x] CLI y evaluación contra clips de referencia (2026-11-19,
        [nota](docs/sessions/2026-11-19-fase-4.md))
      - [x] Prueba con un VOD real (aceptación de SPEC §10), registrada en la
        nota de sesión (2026-11-20): 0 candidatos, 0/10 clips, 0 llamadas al
        juez.

## Fases v1

- [x] Fase 5 detector revisado (D15), fusionada (PR #7)
      - [x] Ventana deslizante de 60 s, selección top-K con supresión de
        no-máximos, `DetectorConfig`, arnés de evaluación sin juez y tests
        (605 en verde). El arnés da PASS sobre el fixture de Rubius: 5/10 en
        K=20 frente a 1,84 del azar, p=0,0325
        ([nota](docs/sessions/2026-11-20-fase-5.md))
      - [x] Primera corrida del juez real sobre el fixture (2026-11-20): 0 de
        20 candidatos (12 × 429 por el límite de 5 peticiones por minuto del
        tier gratuito, 7 × 503, 1 sin transcripción). Resuelto por D16 y la
        fase 6.
- [x] Fase 6 resiliencia del juez (D16, D18), fusionada (PR #8): pacing de
      12 s, reintentos de errores transitorios con tope al `retryDelay` y
      `judge_candidates` sin reintento tras agotar transitorios (653 tests en
      verde). Con `gemini-3.8-flash` la cuota diaria (20 peticiones) se agotó
      tras 5 de 20 candidatos; con `gemini-3.5-flash-lite` (500/día, D19) la
      corrida de cierre juzgó los 19 candidatos con transcripción en 229 s, sin
      errores, y el CLI evaluó 2/10 clips de referencia con 5 momentos
      ([nota](docs/sessions/2026-11-21-fase-6.md))
- [x] Medición con una segunda VOD (DjMaRiiO, 22-nov, 2026-11-23): la línea
      base global se queda (la local pierde en las dos VODs); en K=20 sin juez
      Rubius da PASS y DjMaRiiO FAIL no fiable (4 aciertos son 2 momentos, el
      arnés cuenta por clip); con juez, 0/10 clips y 1 fallo de validación.
      Decidido en D20, que aprueba el alcance de la fase 7
      ([nota](docs/sessions/2026-11-23-validacion-djmariio.md))
- [x] Fase 7 instrumento y lectura del juez (D20), en este orden; en PR, 713
      tests en verde ([nota](docs/sessions/2026-11-24-fase-7.md)):
      - [x] Arnés por momento distinto (clips solapados o a menos de 60 s se
        fusionan) y recálculo de los dos fixtures con ambas cuentas. Por
        momento en K=20: Rubius PASS (5/9, p=0,0165), DjMaRiiO FAIL (2/8,
        p=0,3618)
      - [x] Recorte del juez con tolerancia de 2 s fuera de ventana
      - [x] Medición de la ocupación del top K por tormentas: una sola ocupa el
        25 % del top 20 de DjMaRiiO y nada de Rubius; quitarla no recupera
        aciertos@20
      - [x] Corrida del juez a K=40 con el instrumento corregido: sin evidencia
        de que ordene mejor que el detector ni que el azar (8 candidatos que
        aciertan por VOD). Decisiones pendientes en DECISIONS (Propuestas)
