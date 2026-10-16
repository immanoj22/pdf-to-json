"""Prevent adapter imports and schema-specific vocabulary in the converter source."""

import ast
import re

from conftest import ROOT

# Shared concepts such as table/list/caption are universal semantic node names.
# This rejects schema-specific tag vocabulary, including short names as whole words.
TAGS = {
    "nimas",
    "dtbook",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "em",
    "pagenum",
    "imggroup",
    "level1",
    "level2",
    "level3",
    "doctitle",
    "docauthor",
    "cnxml",
    "collxml",
    "mdml",
}
# Math markup element names (Step 13): equations stay neutral evidence in the model. MathML
# is equation content (Step 13c rule), written and read by one module only; DTBook/NIMAS
# vocabulary stays out of every module.
MATH_TAGS = {
    "mrow",
    "mfrac",
    "msub",
    "msup",
    "msubsup",
    "msqrt",
    "mroot",
    "mtable",
    "mtr",
    "mtd",
    "mtext",
    "mstyle",
    "munder",
    "mover",
    "munderover",
    "mfenced",
}
MATH_MARKUP = ("book_core", "mathml", "markup.py")


def test_no_adapter_imports_or_schema_tag_names():
    for path in (ROOT / "backend/src").rglob("*.py"):
        source = path.read_text("utf-8")
        words = set(re.findall(r"[A-Za-z][A-Za-z0-9]*", source.lower()))
        assert not TAGS.intersection(words), path
        if path.parts[-3:] != MATH_MARKUP:
            assert not MATH_TAGS.intersection(words), path
        for node in ast.walk(ast.parse(source)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or "", *(alias.name for alias in node.names)]
            elif isinstance(node, ast.Call):
                modules = [
                    arg.value
                    for arg in node.args
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                ]
            assert not any("mapping" in module.split(".") for module in modules), path


def test_package_initializers_are_docstrings_only():
    for name in [
        "extraction",
        "ingestion",
        "layout",
        "model",
        "ledger",
        "evaluation",
        "mapping",
        "profiles",
    ]:
        package = ROOT / "backend/src/book_core" / name
        body = ast.parse((package / "__init__.py").read_text("utf-8")).body
        assert len(body) == 1 and isinstance(body[0], ast.Expr)
        assert isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)
        # Layout proposals start in Step 4a; adapters and profiles remain empty.
        if name in {"mapping", "profiles"}:
            assert list(package.glob("*.py")) == [package / "__init__.py"]
    assert (ROOT / "AGENTS.md").read_bytes() == (ROOT / "CLAUDE.md").read_bytes()
