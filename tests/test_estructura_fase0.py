"""Fase 0: comprueba que la estructura y las reglas básicas del repo están en su sitio."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

FICHEROS = [
    "CLAUDE.md",
    "SPEC.md",
    "PROGRESS.md",
    "README.md",
    "docs/DECISIONS.md",
    ".gitignore",
    ".env.example",
    "src/__init__.py",
    "tests/__init__.py",
]

DIRECTORIOS = ["docs/sessions", "src", "tests"]


def test_existen_los_ficheros_de_la_fase_0():
    faltan = [f for f in FICHEROS if not (RAIZ / f).is_file()]
    assert faltan == []


def test_existen_los_directorios_de_la_fase_0():
    faltan = [d for d in DIRECTORIOS if not (RAIZ / d).is_dir()]
    assert faltan == []


def test_env_esta_en_gitignore():
    lineas = (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in [linea.strip() for linea in lineas]


def test_env_example_no_tiene_valores():
    lineas = (RAIZ / ".env.example").read_text(encoding="utf-8").splitlines()
    variables = [
        linea for linea in lineas if linea.strip() and not linea.startswith("#")
    ]
    assert variables, ".env.example debe declarar al menos una variable"
    for linea in variables:
        clave, separador, valor = linea.partition("=")
        assert separador == "=", f"línea sin '=': {linea!r}"
        assert valor.strip() == "", f"{clave} no debe llevar valor en .env.example"


def test_no_hay_env_real_en_el_repo():
    assert not (RAIZ / ".env").exists()


def test_claude_md_recoge_las_restricciones_duras():
    texto = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Nunca se sube ni se publica nada" in texto
    assert "agnóstico a la fuente" in texto


def test_decisions_registra_las_cuatro_decisiones():
    texto = (RAIZ / "docs" / "DECISIONS.md").read_text(encoding="utf-8")
    for decision in ("D1", "D2", "D3", "D4"):
        assert f"## {decision} ·" in texto
