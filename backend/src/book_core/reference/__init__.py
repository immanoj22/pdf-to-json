"""Reference-pair evidence: reading reference XML and aligning it to retained PDF tokens.

Reference XML is evidence, not infallible truth. Element names live only in this package and in
derived-gold provenance; the core model never contains them. Nothing here edits the span store,
the text ledger or any layout output.
"""
