# PROGRESS

**Fase actual:** v0 cerrado. La prueba con un VOD real de 8:34:30 está
registrada en la [nota de la fase 4](docs/sessions/2026-11-19-fase-4.md): 0
candidatos y 0/10 clips de referencia, porque el chat de ese directo es demasiado
plano para el umbral ×1,5 (máximo ×1,31). Decisión sobre el detector pendiente
del arquitecto.

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
