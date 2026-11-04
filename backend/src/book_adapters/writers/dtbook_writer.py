"""NIMAS / DTBook writer: DTBook 2005-3 file, OPF package, images, title/copyright PDF."""

from __future__ import annotations

from pathlib import Path

from lxml import etree

from ..formats import dtbook as dt
from ..formats import nimas
from ..formats.markup import serialize
from .base import Delivery
from .formatwriter import FormatWriter


class DtbookWriter(FormatWriter):
    name = "dtbook"
    root_pattern = "{isbn}_nimas"

    def make_tree(self):
        conv = dt.DtbookConverter(self.src, self.cfg)
        return conv.build(), conv

    def build(self, delivery: Delivery) -> None:
        cfg, src = self.cfg, self.src
        root, conv = self.make_tree()
        isbn = self.isbn
        nimas_cfg = cfg["nimas"]
        main = nimas_cfg["dtbook_file"].format(isbn=isbn)
        delivery.files[main] = self.document(
            root, conv.math_used, src.language(cfg["metadata"]["language"])
        )
        delivery.main_file = main
        delivery.spine = [main]
        delivery.split_files = {main: "dtbook"}
        delivery.anchors = delivery.anchors
        delivery.dtbook_math = conv.math_used
        delivery.notes = conv.notes
        if nimas_cfg["enabled"]:
            self.package(delivery, main, isbn)

    def document(self, root, math: bool, lang: str) -> bytes:
        text = serialize(
            root, dt.BLOCK, prefixes={dt.MATHML_NS: "m"}, declared=frozenset({dt.MATHML_NS})
        )
        ns = f' xmlns="{dt.NS}"' + (f' xmlns:m="{dt.MATHML_NS}"' if math else "")
        text = text.replace("<dtbook", f'<dtbook{ns} version="2005-3" xml:lang="{lang}"', 1)
        subset = f" {dt.MATH_SUBSET}" if math else ""
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<!DOCTYPE dtbook PUBLIC "{dt.PUBLIC_ID}" "{dt.SYSTEM_ID}"{subset}>\n'
        )
        return (head + text + "\n").encode("utf-8")

    # ------------------------------------------------------------------ NIMAS package

    def package(self, delivery: Delivery, main: str, isbn: str):
        src, cfg, settings = self.src, self.cfg, self.ctx.settings.data
        n = cfg["nimas"]
        uid = (
            settings.get("isbn")
            or "urn:content-sha256:"
            + ((src.book.data["metadata"].get("content_sha256") or "")[:16])
        )
        title = src.title_text()
        language = src.language(cfg["metadata"]["language"])
        publisher = settings.get("publisher") or cfg["metadata"]["publisher"]
        rights = settings.get("rights") or cfg["metadata"]["rights"]
        date = settings.get("publication_date")
        dc = [("Identifier", uid), ("Title", title or "TITLE_TO_SUPPLY")]
        for p in src.people():
            if p.name:
                dc.append(("Creator", p.name))
        for name, value in (("Publisher", publisher), ("Date", date)):
            if value:
                dc.append((name, value))
            else:
                self.to_supply(f"NIMAS dc:{name}", "not in the book settings or the profile")
        dc += [("Format", n["format"]), ("Language", language)]
        if rights:
            dc.append(("Rights", rights))
        else:
            self.to_supply("NIMAS dc:Rights", "not in the book settings or the profile")
        if settings.get("isbn"):
            dc.append(("Source", f"urn:isbn:{settings['isbn']}"))
        else:
            self.to_supply("NIMAS dc:Source", "the ISBN of the print source (never guessed)")
        x = []
        if settings.get("edition"):
            x.append(("nimas-SourceEdition", settings["edition"]))
        else:
            self.to_supply("nimas-SourceEdition", "edition not in the book settings")
        if date:
            x.append(("nimas-SourceDate", date))
        manifest = [("dtbook", main, "text/xml")]
        for k, job in enumerate(sorted(delivery_images(self, delivery), key=lambda j: j.name), 1):
            ext = Path(job.name).suffix.lower()
            manifest.append(
                (
                    f"img{k}",
                    f"{cfg['images_folder']}/{job.name}",
                    "image/png" if ext == ".png" else "image/jpeg",
                )
            )
        pdf = self.title_copyright(delivery, n)
        if pdf:
            manifest.append(("titlecopyright", pdf, "application/pdf"))
        pkg = n["package_file"].format(isbn=isbn)
        delivery.files[pkg] = nimas.opf_bytes({"dc": dc, "x": x, "uid": uid}, manifest, ["dtbook"])
        delivery.package_file = pkg
        delivery.split_files[pkg] = "opf"

    def title_copyright(self, delivery: Delivery, n: dict) -> str | None:
        book = self.ctx.book
        kinds = set(n["title_copyright_sections"])
        pages = sorted(
            {
                p
                for s in (book.data.get("navigation") or {}).get("sections") or []
                if s["kind"] in kinds
                for p in range(s["first_page"], s["last_page"] + 1)
            }
        )
        source = self.ctx.options.get("source_pdf")
        name = n["title_copyright_file"].format(isbn=self.isbn)
        if not pages:
            self.to_supply("title/copyright PDF", "the converter found no title or copyright page")
            return None
        if not source or not Path(source).is_file():
            self.to_supply(
                "title/copyright PDF",
                f"the source PDF was not given (pages {pages[0]}-{pages[-1]} would be cut from it)",
            )
            return None
        delivery.files[name] = nimas.cut_pages(source, pages)
        delivery.title_copyright_pages = pages
        return name


def delivery_images(writer, delivery):
    return writer.src.writer.images


_ = etree
