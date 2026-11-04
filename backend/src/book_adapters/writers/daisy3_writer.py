"""DAISY 3 text-only DTB writer (see :mod:`book_adapters.formats.daisy3`)."""

from __future__ import annotations

from pathlib import Path

from ..formats import daisy3 as d3
from ..formats import nimas
from .base import Delivery
from .dtbook_writer import DtbookWriter

GENERATOR = "book-adapters daisy3"


class Daisy3Writer(DtbookWriter):
    name = "daisy3"
    root_pattern = "{isbn}_daisy3"

    def build(self, delivery: Delivery) -> None:
        cfg, src, isbn = self.cfg, self.src, self.isbn
        files = cfg["files"]
        root, conv = self.make_tree()
        uid = conv.uid()
        sync_all = d3.assign_ids(root, None)
        level1 = [e for e in root.iter() if e.tag == "level1"]
        group_of = {id(e): i for i, e in enumerate(level1, 1)}

        def group(el):
            for anc in el.iterancestors():
                if anc.tag == "level1":
                    return group_of[id(anc)]
            return 0

        sync = [(e, group(e)) for e in sync_all]
        smil_files, where, custom = d3.smil_documents(
            sync, files["dtbook"].format(isbn=isbn), uid, cfg["smil"]["split"], GENERATOR
        )
        smil_names = {k: files["smil"].format(isbn=isbn, n=k) for k, _ in smil_files}
        for el in sync_all:
            k, par = where[el.get("id")]
            el.set("smilref", f"{smil_names[k]}#{par}")
        main = files["dtbook"].format(isbn=isbn)
        lang = src.language(cfg["metadata"]["language"])
        delivery.files[main] = self.document(root, conv.math_used, lang)
        delivery.main_file = main
        delivery.spine = [main]
        delivery.split_files = {main: "dtbook"}
        for k, data in smil_files:
            delivery.files[smil_names[k]] = data
            delivery.split_files[smil_names[k]] = "smil"
        authors = [p.name for p in src.people() if p.name]
        ncx, stats = d3.ncx_bytes(
            root,
            where,
            lambda k: smil_names[k],
            uid,
            src.title_text() or "TITLE_TO_SUPPLY",
            authors,
            lang,
            GENERATOR,
            {"pagelist": cfg["ncx"]["page_list_label"]},
        )
        ncx_name = files["ncx"].format(isbn=isbn)
        delivery.files[ncx_name] = ncx
        delivery.split_files[ncx_name] = "ncx"
        manifest = [("dtbook", main, d3.MEDIA["dtbook"]), ("ncx", ncx_name, d3.MEDIA["ncx"])]
        for k, _ in smil_files:
            manifest.append((f"smil{k}", smil_names[k], d3.MEDIA["smil"]))
        if cfg["resource"]["enabled"]:
            res = files["resource"].format(isbn=isbn)
            delivery.files[res] = d3.resource_bytes(lang, cfg["resource"]["labels"])
            delivery.split_files[res] = "res"
            manifest.append(("resource", res, d3.MEDIA["res"]))
        for k, job in enumerate(sorted(conv_images(self), key=lambda j: j.name), 1):
            ext = Path(job.name).suffix.lower()
            manifest.append(
                (f"img{k}", f"{cfg['images_folder']}/{job.name}",
                 "image/png" if ext == ".png" else "image/jpeg")
            )  # fmt: skip
        pkg = files["package"].format(isbn=isbn)
        manifest.append(("package", pkg, d3.MEDIA["package"]))
        meta = self.meta(uid, lang, stats, bool(conv_images(self)))
        spine = [f"smil{k}" for k, _ in smil_files]
        delivery.files[pkg] = nimas.opf_bytes(meta, manifest, spine)
        delivery.package_file = pkg
        delivery.split_files[pkg] = "opf"
        delivery.ncx_stats = stats
        delivery.smil_files = sorted(smil_names.values())
        delivery.dtbook_math = conv.math_used

    def meta(self, uid: str, lang: str, stats: dict, images: bool) -> dict:
        settings, cfg, src = self.ctx.settings.data, self.cfg, self.src
        dc = [("Identifier", uid), ("Title", src.title_text() or "TITLE_TO_SUPPLY")]
        dc += [("Creator", p.name) for p in src.people() if p.name]
        publisher = settings.get("publisher") or cfg["metadata"]["publisher"]
        date = settings.get("publication_date")
        for name, value in (("Publisher", publisher), ("Date", date)):
            if value:
                dc.append((name, value))
            else:
                self.to_supply(
                    f"DAISY dc:{name}", "required by Z39.86-2005; not in the book settings"
                )
        dc += [("Format", "ANSI/NISO Z39.86-2005"), ("Language", lang)]
        rights = settings.get("rights") or cfg["metadata"]["rights"]
        if rights:
            dc.append(("Rights", rights))
        if settings.get("isbn"):
            dc.append(("Source", f"urn:isbn:{settings['isbn']}"))
        x = [
            ("dtb:multimediaType", "textNCX"),
            ("dtb:multimediaContent", "text,image" if images else "text"),
        ]
        if settings.get("edition"):
            x.append(("dtb:sourceEdition", settings["edition"]))
        if date:
            x.append(("dtb:sourceDate", date))
        x.append(("dtb:producer", GENERATOR))
        return {"dc": dc, "x": x, "uid": uid}


def conv_images(writer):
    return writer.src.writer.images
