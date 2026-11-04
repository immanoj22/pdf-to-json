# Pinned official schemas (offline validation)

Downloaded 2026-11-04, unmodified; `PINNED.json` holds the SHA-256 of every file and is
verified before each validation (`book_adapters.validate.schemas.verify_pinned`).

| Folder | What | Source | Licence |
|---|---|---|---|
| `jats1_4/` | ANSI/NISO Z39.96-2024 **JATS 1.4**, Journal Publishing DTD, MathML 3, XHTML tables (`JATS-journalpublishing1-4-mathml3.dtd`, public id `-//NLM//DTD JATS (Z39.96) Journal Publishing DTD with MathML3 v1.4 20241031//EN`) | https://public.nlm.nih.gov/projects/jats/publishing/1.4/JATS-Publishing-1-4-MathML3-DTD.zip | Public domain (header of the DTD: "This DTD is in the public domain"; do not modify or redistribute modified versions: we do not) |
| `bits2_2/` | **BITS 2.2** (JATS extension, Book Interchange Tag Set), uses JATS 1.4 modules, MathML 3 (`BITS-book2-2.dtd`) | https://public.nlm.nih.gov/projects/jats/extensions/bits/2.2/BITS-2-2-DTD.zip | Public domain (same NLM statement in the DTD header) |
| `dtbook2005_3/` | **DTBook 2005-3** (ANSI/NISO Z39.86-2005, revision 2007-12-19; the DTD NIMAS 1.1 uses) | https://www.daisy.org/z3986/2005/dtbook-2005-3.dtd | DAISY Consortium / NISO standard DTD, published for free use with no licence restriction stated in the file; used as published, unmodified |
| `mathml2/` | **MathML 2.0** DTD and entity sets, the module the DAISY specification names for maths in DTBook | https://www.w3.org/Math/DTD/mathml2/ | W3C: "Permission to use, copy, modify and distribute the MathML 2.0 DTD ... for any purpose and without fee is hereby granted in perpetuity" (copyright notice kept in the files) |

None is GPL/AGPL/non-commercial. Nothing was installed; only static DTD files are stored.
| `oeb1_2/` | **OEB 1.2 package DTD** (`oebpkg12.dtd`, `oeb12.ent`): the package file (OPF) of NIMAS 1.1 | http://openebook.org/dtds/oeb-1.2/ | The files carry no licence text. IDPF open standard (Open eBook Publication Structure 1.2), published for implementers; stored unmodified and used only to validate; **owner to confirm** |
| `daisy3/` | DAISY 3 (Z39.86-2005): NCX 2005-1, resource file 2005-1, DTB SMIL 2005-2 | https://www.daisy.org/z3986/2005/ | DAISY Consortium / NISO standard DTDs, published for free use; no licence restriction stated in the files |
