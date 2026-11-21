# PROGRESS

**Fase actual:** v1 abierta. El v0 está cerrado: la prueba con un VOD real de
8:34:30 ([nota de la fase 4](docs/sessions/2026-11-19-fase-4.md)) dio 0
candidatos y 0/10 clips de referencia, porque el chat de ese directo es
demasiado plano para el umbral ×1,5 (máximo ×1,31). El detector queda decidido
en [D15](docs/DECISIONS.md). La fase 5 (ventana deslizante y top-K, con arnés
de evaluación) está implementada y en PR; falta validar el juez real sobre el
fixture, bloqueado por el límite de 5 peticiones por minuto del tier gratuito.

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

- [ ] Fase 5 detector revisado (D15)
      - [x] Ventana deslizante de 60 s, selección top-K con supresión de
        no-máximos, `DetectorConfig`, arnés de evaluación sin juez y tests
        (605 en verde). El arnés da PASS sobre el fixture de Rubius: 5/10 en
        K=20 frente a 1,84 del azar, p=0,0325
        ([nota](docs/sessions/2026-11-20-fase-5.md))
      - [ ] Primera corrida del juez real sobre el fixture (2026-11-20): 0 de
        20 candidatos (12 × 429 por el límite de 5 peticiones por minuto del
        tier gratuito, 7 × 503, 1 sin transcripción). Pendiente decisión del
        arquitecto sobre ritmo y reintentos del juez
