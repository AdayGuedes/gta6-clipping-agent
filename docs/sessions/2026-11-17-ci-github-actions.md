# Sesión 2026-11-17 · CI con GitHub Actions (D8)

## Qué se hizo

- `.github/workflows/ci.yml`: en pull requests y pushes a `main` instala
  `requirements.txt` y ejecuta `ruff check .`, `black --check .` y
  `python -m pytest` sobre Python 3.11. No usa secretos.
- `requirements.txt` con `pydantic`, `pytest`, `ruff` y `black`.
- D8 en `docs/DECISIONS.md` y entrada en `[Unreleased]` del CHANGELOG.
- `black` reformateó una línea de `tests/test_estructura_fase0.py` para que
  `black --check .` pasara.
- README: la puesta en marcha instala `requirements.txt` y lista las mismas
  comprobaciones que el CI.

## Tests

En local, con Python 3.14.6: `ruff check .` sin avisos, `black --check .` sin
cambios pendientes y `python -m pytest` con 7 passed. Python 3.11 no está
instalado en esta máquina, así que la ejecución sobre 3.11 es la del CI de la
propia PR.

## Errores

- La primera pasada de `black --check .` falló por una línea larga del test de
  la fase 0. Se corrigió con `black`.

## Lección

Poner linter y formateador en CI antes de escribir código cuesta un
reformateo de una línea y evita descubrirlo en mitad de la fase 1.
