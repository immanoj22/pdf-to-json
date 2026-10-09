"""Schema-neutral dialect profiles for reading reference XML.

This module knows no schema. Element vocabulary arrives as profile data (the file named by
``Settings.reference_dialects``, by default backend/reference_dialects/dialects.json). It is used
only to read reference evidence and maps names to neutral reference unit kinds (heading,
paragraph, list_item, ...). The core model never contains element names; they appear only as
provenance paths in derived gold.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from book_core.reference.xml_reader import Element

SYNTHETIC_CONTAINER = "reference-fragments"


@dataclass(frozen=True)
class Dialect:
    name: str
    detect: Mapping[str, object]
    page_marker_elements: frozenset[str]
    inline_elements: frozenset[str]
    kind_of: Mapping[str, str]
    containers: frozenset[str]
    sectioning: frozenset[str]
    list_containers: frozenset[str]
    table_containers: frozenset[str]
    row_elements: frozenset[str]
    declared_heading_levels: Mapping[str, int]
    zones: Mapping[str, str]
    role_zones: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    contextual_units: Mapping[str, Mapping] = field(default_factory=dict)

    def unit_kind(self, name: str) -> str:
        return self.kind_of.get(name, "other")

    def qualifies(self, element: int, elements: Sequence[Element]) -> bool:
        """A contextual unit name counts only under the parents its profile rule allows."""
        rule = self.contextual_units.get(elements[element].name)
        if rule is None:
            return True
        allowed = getattr(self, rule["parent_in"])
        parent = elements[element].parent
        if parent is None:
            return False
        if elements[parent].name in allowed:
            return True
        grand = elements[parent].parent
        return (
            elements[parent].name in rule.get("or_via", ())
            and grand is not None
            and elements[grand].name in allowed
        )

    def element_kind(self, element: int, elements: Sequence[Element]) -> str:
        """Neutral kind of one element in context; a disqualified contextual unit is other."""
        if not self.qualifies(element, elements):
            return "other"
        return self.unit_kind(elements[element].name)

    def unit_of(self, element: int, elements: Sequence[Element]) -> int:
        """Nearest unit element, else nearest non-inline element, ancestor-or-self."""
        fallback = None
        current: int | None = element
        while current is not None:
            name = elements[current].name
            if name in self.kind_of and self.qualifies(current, elements):
                return current
            if fallback is None and name not in self.inline_elements:
                fallback = current
            current = elements[current].parent
        return fallback if fallback is not None else element

    def zone_of(self, element: int, elements: Sequence[Element]) -> str:
        """Front/body/rear/metadata from the outermost non-container ancestor."""
        for index in reversed(_chain(element, elements)):
            item = elements[index]
            if item.name in self.containers or item.name == SYNTHETIC_CONTAINER:
                continue
            roles = self.role_zones.get(item.name)
            if roles and item.attributes.get("role") in roles:
                return roles[item.attributes["role"]]
            return self.zones.get(item.name, "unknown")
        return "unknown"

    def heading_level(self, element: int, elements: Sequence[Element]) -> tuple[int | None, str]:
        """Declared level when the element name carries one, else sectioning depth."""
        name = elements[element].name
        if self.element_kind(element, elements) != "heading":
            return None, "not_heading"
        if name in self.declared_heading_levels:
            return self.declared_heading_levels[name], "declared"
        chain = _chain(element, elements)[1:]
        depth = sum(1 for index in chain if elements[index].name in self.sectioning)
        return max(depth, 1), "nesting"

    def list_membership(self, element: int, elements: Sequence[Element]) -> dict | None:
        chain = _chain(element, elements)
        lists = [index for index in chain if elements[index].name in self.list_containers]
        if not lists:
            return None
        item = next((i for i in chain if self.unit_kind(elements[i].name) == "list_item"), None)
        return {
            "list": elements[lists[0]].path,
            "depth": len(lists),
            "item": elements[item].path if item is not None else None,
        }

    def table_membership(self, element: int, elements: Sequence[Element]) -> dict | None:
        chain = _chain(element, elements)
        table = next((i for i in chain if elements[i].name in self.table_containers), None)
        if table is None:
            return None
        row = next((i for i in chain if elements[i].name in self.row_elements), None)
        cell = next((i for i in chain if self.unit_kind(elements[i].name) == "table_cell"), None)
        return {
            "table": elements[table].path,
            "row": elements[row].path if row is not None else None,
            "cell": elements[cell].path if cell is not None else None,
        }

    def matches(self, root: ET.Element) -> bool:
        rules = self.detect
        if rules.get("fallback"):
            return True
        tag = root.tag if isinstance(root.tag, str) else ""
        if any(part in tag for part in rules.get("root_namespace_contains", ())):
            return True
        if tag.rsplit("}", 1)[-1] in rules.get("root_names", ()):
            return True
        wanted = set(rules.get("contains_elements", ()))
        return bool(wanted) and any(
            isinstance(node.tag, str) and node.tag.rsplit("}", 1)[-1] in wanted
            for node in root.iter()
        )


@dataclass(frozen=True)
class DialectSet:
    dialects: tuple[Dialect, ...]
    digest: str

    def detect(self, root: ET.Element) -> Dialect:
        for dialect in self.dialects:
            if dialect.matches(root):
                return dialect
        raise ValueError("No reference dialect profile matches this XML")


def dialects_from_data(data: Mapping) -> DialectSet:
    common = data["common"]
    kind_of = {name: kind for kind, names in common["unit_kinds"].items() for name in names}
    dialects = []
    for spec in data["dialects"]:
        merged = {**common, **spec}
        dialects.append(
            Dialect(
                name=spec["name"],
                detect=spec.get("detect", {}),
                page_marker_elements=frozenset(merged["page_marker_elements"]),
                inline_elements=frozenset(merged["inline_elements"]),
                kind_of=kind_of,
                containers=frozenset(merged["containers"]),
                sectioning=frozenset(merged["sectioning"]),
                list_containers=frozenset(merged["list_containers"]),
                table_containers=frozenset(merged["table_containers"]),
                row_elements=frozenset(merged["row_elements"]),
                declared_heading_levels=dict(merged["declared_heading_levels"]),
                zones=dict(merged["zones"]),
                role_zones={k: dict(v) for k, v in merged.get("role_zones", {}).items()},
                contextual_units={
                    k: dict(v) for k, v in merged.get("contextual_units", {}).items()
                },
            )
        )
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return DialectSet(tuple(dialects), hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def load_dialects(path: Path) -> DialectSet:
    return dialects_from_data(json.loads(Path(path).read_text("utf-8")))


def _chain(element: int, elements: Sequence[Element]) -> list[int]:
    chain = []
    current: int | None = element
    while current is not None:
        chain.append(current)
        current = elements[current].parent
    return chain  # self first, root last
