"""Review decisions: one file per book (``decisions.json``), an append-only list of events
(who, when, what). The converter's output is never edited; the adapter run reads the book
with the *edits* among these events applied (see ``overlay``).

Events:
  decision  one per review item, the last wins (key, item_kind, action, fix, note)
  edit      a structural change from browse mode or a fix (op and its fields, source)
  revoke    undo an edit or a decision (target)
  override  an explicit override, such as exporting with alt-text placeholders
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from pathlib import Path

from .jobs import JobError, now, read_json, write_json

ACTIONS = {"accept", "fix", "skip"}
EDIT_OPS = {
    "heading_set", "heading_remove", "new_chapter", "join_next", "unjoin", "split",
    "make_list", "alt_text", "decorative", "char",
    "heading_kind", "heading_number", "heading_text", "heading_attach",
    # element changes (edit_ops)
    "list_set", "list_level", "box", "caption", "table_make", "table_text", "footnote",
    "paragraph", "chapter_authors", "question", "bibliography", "index_entries", "glossary",
    "not_content", "merge", "move", "swap_columns", "unwrap", "table_split",
}  # fmt: skip
_lock = threading.RLock()


def item_key(item: dict) -> str:
    raw = "|".join(str(item.get(k)) for k in ("source", "kind", "unit", "page", "reason"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Decisions:
    def __init__(self, job_dir: Path):
        self.path = job_dir / "decisions.json"

    def load(self) -> dict:
        return read_json(self.path, {"version": 1, "events": []})

    def _append(self, event: dict) -> dict:
        with _lock:
            data = self.load()
            event = {"id": secrets.token_hex(6), "at": now(), **event}
            data["events"].append(event)
            write_json(self.path, data)
            return event

    # ------------------------------------------------------------------ reading

    def revoked(self, data: dict | None = None) -> set[str]:
        data = data or self.load()
        return {e["target"] for e in data["events"] if e["type"] == "revoke"}

    def edits(self) -> list[dict]:
        data = self.load()
        gone = self.revoked(data)
        return [e for e in data["events"] if e["type"] == "edit" and e["id"] not in gone]

    def current(self) -> dict[str, dict]:
        """The last non-revoked decision per review item key."""
        data = self.load()
        gone = self.revoked(data)
        out: dict[str, dict] = {}
        for e in data["events"]:
            if e["type"] == "decision" and e["id"] not in gone:
                out[e["key"]] = e
        return out

    def overrides(self) -> list[dict]:
        return [e for e in self.load()["events"] if e["type"] == "override"]

    # ------------------------------------------------------------------ writing

    def decide(self, who: str, key: str, item_kind: str, action: str, fix: dict | None, note: str,
               item: dict | None = None) -> dict:  # fmt: skip
        if action not in ACTIONS:
            raise JobError(422, "The action is Accept, Fix or Skip.", "bad_action")
        if action == "fix" and not fix:
            raise JobError(422, "Say what the fix is.", "no_fix")
        if not who.strip():
            raise JobError(422, "Enter your name first, so the decision can be traced.", "no_who")
        with _lock:
            for old in self.edits():  # a new answer replaces the edits of the old one
                if old.get("source") == key:
                    self._append({"type": "revoke", "target": old["id"], "who": who})
            event = self._append(
                {
                    "type": "decision",
                    "who": who.strip(),
                    "key": key,
                    "item_kind": item_kind,
                    "action": action,
                    "fix": fix if action == "fix" else None,
                    "note": note or "",
                    "item": item,  # what was decided, kept when a fix makes the item disappear
                }
            )
            if action == "fix" and fix and fix.get("op"):
                self.edit(who, fix, source=key)
            return event

    def decide_many(self, who: str, action: str, entries: list[dict], note: str = "",
                    group: str | None = None) -> int:  # fmt: skip
        """Accept, skip or (each entry with its own ``fix``) fix many items with one read and
        one write. The events of one call share ``group`` so one Undo takes them all back."""
        if action not in ACTIONS:
            raise JobError(422, "The action is Accept, Fix or Skip.", "bad_action")
        if action == "fix" and not all((e.get("fix") or {}).get("op") in EDIT_OPS for e in entries):
            raise JobError(422, "Each item needs its own change.", "no_fix")
        if not who.strip():
            raise JobError(422, "Enter your name first, so the decision can be traced.", "no_who")
        with _lock:
            data = self.load()
            gone = self.revoked(data)
            edit_by_source = {
                e["source"]: e for e in data["events"]
                if e["type"] == "edit" and e["id"] not in gone and e.get("source")
            }  # fmt: skip
            for entry in entries:
                key = str(entry.get("key") or "")
                if not key:
                    continue
                old = edit_by_source.get(key)
                if old:  # a new answer replaces the edits of the old one
                    data["events"].append(
                        {"id": secrets.token_hex(6), "at": now(), "type": "revoke",
                         "target": old["id"], "who": who}
                    )  # fmt: skip
                data["events"].append(
                    {
                        "id": secrets.token_hex(6), "at": now(), "type": "decision",
                        "who": who.strip(),
                        "key": key, "item_kind": entry.get("item_kind") or "", "action": action,
                        "fix": entry["fix"] if action == "fix" else None,
                        "note": note or "", "item": entry.get("item"),
                        **({"group": group} if group else {}),
                    }
                )  # fmt: skip
                if action == "fix":
                    fix = {k: v for k, v in entry["fix"].items() if k not in ("id", "at", "who", "type")}
                    data["events"].append(
                        {"id": secrets.token_hex(6), "at": now(), "type": "edit", "who": who.strip(),
                         "source": key, **fix, **({"decision_group": group} if group else {})}
                    )  # fmt: skip
            write_json(self.path, data)
            return len(entries)

    def edit(self, who: str, edit: dict, source: str | None = None) -> dict:
        if edit.get("op") not in EDIT_OPS:
            raise JobError(422, "Unknown change.", "bad_edit")
        if not who.strip():
            raise JobError(422, "Enter your name first, so the change can be traced.", "no_who")
        body = {k: v for k, v in edit.items() if k not in ("id", "at", "who", "type")}
        return self._append({"type": "edit", "who": who.strip(), "source": source, **body})

    def revoke(self, who: str, target: str) -> dict:
        data = self.load()
        if not any(e["id"] == target and e["type"] in ("edit", "decision") for e in data["events"]):
            raise JobError(404, "No such decision.", "not_found")
        if target in self.revoked(data):
            raise JobError(409, "That was already undone.", "already_revoked")
        return self._append({"type": "revoke", "target": target, "who": who.strip() or "unknown"})

    def revoke_group(self, who: str, group: str) -> list[str]:
        """Take back every decision and change of one 'apply to all similar' group."""
        with _lock:
            data = self.load()
            gone = self.revoked(data)
            targets = [e["id"] for e in data["events"] if e["id"] not in gone and (
                (e["type"] == "decision" and e.get("group") == group)
                or (e["type"] == "edit" and e.get("decision_group") == group))]  # fmt: skip
            if not targets:
                raise JobError(404, "No such group of answers.", "not_found")
            for t in targets:
                data["events"].append({"id": secrets.token_hex(6), "at": now(), "type": "revoke",
                                       "target": t, "who": who.strip() or "unknown"})
            write_json(self.path, data)
            return targets

    def override(self, who: str, what: str, count: int) -> dict:
        return self._append(
            {"type": "override", "who": who.strip() or "unknown", "what": what, "count": count}
        )
