"""Client profiles: YAML files validated against ``profile.schema.json``.

A profile file may extend a parent (``extends``); objects merge key by key, lists and
scalars replace. The merged profile gets the schema defaults. Every problem is reported
with the file, line, field path and, for misspelt fields, a suggestion.
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import json
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from .paths import profiles_root

ID_PLACEHOLDERS = frozenset({"chapter", "part", "level", "n", "num", "k"})
ID_FIELDS = (
    "part",
    "chapter",
    "appendix",
    "section",
    "section_title_role",
    "sidebar",
    "sidebar_title_role",
    "table",
    "table_title_role",
    "continued_figure",
    "bibliography",
    "bibliography_entry",
)


@dataclass(frozen=True)
class Problem:
    file: str
    line: int | None
    path: str
    message: str
    suggestion: str | None = None

    def __str__(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        text = f"{where}: {self.path or '(top)'}: {self.message}"
        return f"{text} Did you mean {self.suggestion!r}?" if self.suggestion else text


class ProfileError(ValueError):
    def __init__(self, problems: list[Problem]):
        self.problems = problems
        super().__init__("\n".join(str(p) for p in problems))


@dataclass
class Profile:
    """A resolved profile: merged values with defaults, and where it came from."""

    name: str
    version: str
    date: str
    data: dict[str, Any]
    file: Path
    file_sha256: str
    chain: list[dict[str, str]] = field(default_factory=list)  # this file first, then parents

    @property
    def resolved_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.data).encode("utf-8")).hexdigest()

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    def identity(self) -> dict[str, Any]:
        return {
            "profile": self.name,
            "version": self.version,
            "date": self.date,
            "file": self.file.name,
            "file_sha256": self.file_sha256,
            "resolved_sha256": self.resolved_sha256,
            "chain": self.chain,
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def load_schema(name: str = "profile.schema.json") -> dict[str, Any]:
    return json.loads((profiles_root() / "schema" / name).read_text("utf-8"))


# --------------------------------------------------------------------------- YAML with lines


def _line_map(text: str, file: str) -> tuple[Any, dict[tuple, int], list[Problem]]:
    """Parse YAML; return the data, a map from key path to line, and duplicate-key problems."""
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
        data = yaml.load(text, Loader=yaml.SafeLoader)  # noqa: S506 (SafeLoader)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark else None
        raise ProfileError([Problem(file, line, "", f"not valid YAML: {exc}")]) from exc
    lines: dict[tuple, int] = {}
    problems: list[Problem] = []

    def walk(n, path: tuple):
        if n is None:
            return
        lines.setdefault(path, n.start_mark.line + 1)
        if isinstance(n, yaml.MappingNode):
            seen = set()
            for key, value in n.value:
                k = key.value
                if k in seen:
                    problems.append(
                        Problem(
                            file, key.start_mark.line + 1, _dotted(path + (k,)), "duplicate field"
                        )
                    )
                seen.add(k)
                lines[path + (k,)] = key.start_mark.line + 1
                walk(value, path + (k,))
        elif isinstance(n, yaml.SequenceNode):
            for i, value in enumerate(n.value):
                walk(value, path + (i,))

    walk(node, ())
    return data, lines, problems


def _dotted(path) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _line_for(lines: dict[tuple, int], path: tuple) -> int | None:
    path = tuple(path)
    while path not in lines and path:
        path = path[:-1]
    return lines.get(path)


# --------------------------------------------------------------------------- schema helpers


def _resolve(schema: dict, root: dict) -> dict:
    while isinstance(schema, dict) and "$ref" in schema:
        ref = schema["$ref"]
        target: Any = root
        for part in ref.lstrip("#/").split("/"):
            target = target[part]
        merged = {k: v for k, v in schema.items() if k != "$ref"}
        schema = {**target, **merged}
    return schema


def _subschema(schema: dict, root: dict, key) -> dict | None:
    schema = _resolve(schema, root)
    if isinstance(key, int):
        items = schema.get("items")
        return _resolve(items, root) if isinstance(items, dict) else None
    props = schema.get("properties", {})
    if key in props:
        return _resolve(props[key], root)
    extra = schema.get("additionalProperties")
    return _resolve(extra, root) if isinstance(extra, dict) else None


def apply_defaults(data: Any, schema: dict, root: dict) -> Any:
    schema = _resolve(schema, root)
    if isinstance(data, dict):
        for key, sub in schema.get("properties", {}).items():
            sub = _resolve(sub, root)
            if key not in data and "default" in sub:
                data[key] = copy.deepcopy(sub["default"])
        for key in list(data):
            sub = _subschema(schema, root, key)
            if sub is not None:
                data[key] = apply_defaults(data[key], sub, root)
    elif isinstance(data, list):
        sub = _subschema(schema, root, 0)
        if sub is not None:
            return [apply_defaults(v, sub, root) for v in data]
    return data


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        out = {k: copy.deepcopy(v) for k, v in base.items()}
        for k, v in override.items():
            out[k] = deep_merge(out[k], v) if k in out else copy.deepcopy(v)
        return out
    return copy.deepcopy(override)


def _schema_problems(
    data: Any, schema: dict, file: str, lines: dict, partial: bool
) -> list[Problem]:
    validator = jsonschema.Draft202012Validator(schema)
    problems = []
    for err in sorted(validator.iter_errors(data), key=lambda e: [str(p) for p in e.path]):
        path = tuple(err.absolute_path)
        if partial and err.validator == "required" and path:
            continue
        if err.validator == "additionalProperties":
            sub = _resolve(err.schema, schema)
            allowed = sorted(sub.get("properties", {}))
            extras = (
                sorted(set(err.instance) - set(allowed)) if isinstance(err.instance, dict) else []
            )
            for extra in extras:
                close = difflib.get_close_matches(extra, allowed, n=1, cutoff=0.6)
                problems.append(
                    Problem(
                        file,
                        _line_for(lines, path + (extra,)),
                        _dotted(path + (extra,)),
                        f"unknown field (allowed here: {', '.join(allowed)})",
                        close[0] if close else None,
                    )
                )
            continue
        if err.validator == "enum":
            close = difflib.get_close_matches(
                str(err.instance), [str(v) for v in err.validator_value], n=1, cutoff=0.6
            )
            problems.append(
                Problem(
                    file,
                    _line_for(lines, path),
                    _dotted(path),
                    f"{err.instance!r} is not one of {err.validator_value}",
                    close[0] if close else None,
                )
            )
            continue
        problems.append(Problem(file, _line_for(lines, path), _dotted(path), err.message))
    return problems


def _semantic_problems(data: dict, schema: dict, file: str, lines: dict) -> list[Problem]:
    """Checks the schema cannot state: regexes compile, id patterns use known placeholders."""
    problems: list[Problem] = []
    regex_def = schema["$defs"]["regex"]

    def walk(value, sub, path):
        if sub is None:
            return
        is_regex = isinstance(sub, dict) and sub.get("$ref") == "#/$defs/regex"
        resolved = _resolve(sub, schema)
        if (is_regex or resolved is regex_def) and isinstance(value, str):
            try:
                re.compile(value)
            except re.error as exc:
                problems.append(
                    Problem(
                        file,
                        _line_for(lines, path),
                        _dotted(path),
                        f"regular expression does not compile: {exc}",
                    )
                )
            return
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, _raw_subschema(resolved, k), path + (k,))
        elif isinstance(value, list):
            items = resolved.get("items") if isinstance(resolved, dict) else None
            for i, v in enumerate(value):
                walk(v, items, path + (i,))

    def _raw_subschema(resolved, key):
        props = resolved.get("properties", {}) if isinstance(resolved, dict) else {}
        if key in props:
            return props[key]
        extra = resolved.get("additionalProperties") if isinstance(resolved, dict) else None
        return extra if isinstance(extra, dict) else None

    walk(data, schema, ())
    ids = data.get("ids", {}) if isinstance(data.get("ids"), dict) else {}
    patterns = [(("ids", k), ids.get(k)) for k in ID_FIELDS]
    for i, kind in enumerate(data.get("figures", {}).get("kinds", []) or []):
        if isinstance(kind, dict):
            patterns += [(("figures", "kinds", i, k), kind.get(k)) for k in ("id", "title_role")]
    for path, pattern in patterns:
        if not isinstance(pattern, str):
            continue
        try:
            names = {f for _, f, _, _ in string.Formatter().parse(pattern) if f is not None}
        except ValueError as exc:
            problems.append(
                Problem(file, _line_for(lines, path), _dotted(path), f"bad pattern: {exc}")
            )
            continue
        unknown = sorted(names - ID_PLACEHOLDERS)
        if unknown:
            close = difflib.get_close_matches(unknown[0], sorted(ID_PLACEHOLDERS), n=1)
            problems.append(
                Problem(
                    file,
                    _line_for(lines, path),
                    _dotted(path),
                    f"unknown placeholder(s) {unknown}; allowed {sorted(ID_PLACEHOLDERS)}",
                    "{" + close[0] + "}" if close else None,
                )
            )
    from ..rules import RULES

    for name, option in (data.get("book_options") or {}).items():
        rule = option.get("rule") if isinstance(option, dict) else None
        if rule and rule not in RULES:
            problems.append(
                Problem(
                    file,
                    _line_for(lines, ("book_options", name, "rule")),
                    f"book_options.{name}.rule",
                    f"unknown rule {rule!r}",
                )
            )
    return problems


# --------------------------------------------------------------------------- loading


def read_profile_file(path: Path) -> tuple[dict, dict, bytes]:
    raw = path.read_bytes()
    file = path.name
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProfileError([Problem(file, None, "", f"not UTF-8 text: {exc}")]) from exc
    data, lines, problems = _line_map(text, file)
    if not isinstance(data, dict):
        raise ProfileError([Problem(file, 1, "", "a profile is a mapping of fields")])
    schema = load_schema()
    problems += _schema_problems(data, schema, file, lines, partial=False)
    problems += _semantic_problems(data, schema, file, lines)
    if problems:
        raise ProfileError(problems)
    return data, lines, raw


def resolve_parent(name: str, child: Path, roots: list[Path]) -> Path:
    candidates = [child.parent / f"{name}.yaml"] + [r / f"{name}.yaml" for r in roots]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ProfileError([Problem(child.name, None, "extends", f"parent profile {name!r} not found")])


def load_profile(path: Path | str, roots: list[Path] | None = None) -> Profile:
    """Load, merge with parents, apply defaults and validate a profile file."""
    path = Path(path)
    roots = roots if roots is not None else [profiles_root()]
    chain: list[tuple[Path, dict, bytes]] = []
    seen: set[Path] = set()
    current = path
    while True:
        resolved = current.resolve()
        if resolved in seen:
            raise ProfileError([Problem(current.name, None, "extends", "profile extends itself")])
        seen.add(resolved)
        data, _lines, raw = read_profile_file(current)
        chain.append((current, data, raw))
        parent = data.get("extends")
        if not parent:
            break
        current = resolve_parent(parent, current, roots)
    merged: dict = {}
    for _, data, _ in reversed(chain):
        merged = deep_merge(merged, data)
    top = chain[0][1]
    for key in ("profile", "version", "date"):  # never inherited
        merged[key] = top[key]
    merged.pop("extends", None)
    merged["extends"] = top.get("extends")
    schema = load_schema()
    merged = apply_defaults(merged, schema, schema)
    problems = _schema_problems(merged, schema, path.name, {}, partial=False)
    if problems:
        raise ProfileError(problems)
    return Profile(
        name=merged["profile"],
        version=merged["version"],
        date=merged["date"],
        data=merged,
        file=path,
        file_sha256=hashlib.sha256(chain[0][2]).hexdigest(),
        chain=[
            {
                "profile": d["profile"],
                "version": d["version"],
                "file": p.name,
                "sha256": hashlib.sha256(r).hexdigest(),
            }
            for p, d, r in chain
        ],
    )


def validate_profile_file(path: Path | str, roots: list[Path] | None = None) -> list[Problem]:
    try:
        load_profile(path, roots)
    except ProfileError as exc:
        return exc.problems
    return []
