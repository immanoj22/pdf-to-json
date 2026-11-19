"""A chapter-licence stamp ("© year … | https://doi.org/…") is not a copyright page."""

from book_core.structure.zones import _kind

CONFIG = {"cover_pages": 2, "cover_letters": 400}


def kind(text, number=5):
    page = {"page": number, "units": [{"letters": 900, "text": text}], "letters_by_stream": {}}
    return _kind(page, "front", {}, {}, CONFIG)[0]


def test_a_page_with_only_a_licence_stamp_is_normal_front_matter():
    stamp = "© 2027 bei den Autor*innen | https://doi.org/10.1515/9783112258859-206\nDies ist ein Open-Access-Artikel."
    assert kind(stamp + "\nAdKo Adversativer Konnektor") == "front_other"


def test_the_real_imprint_page_is_still_a_copyright_page():
    assert kind("© 2027 Walter de Gruyter GmbH, Berlin\nISBN 978-3-11-225885-9") == "copyright"
    assert kind("Imprint\n© 2027 bei den Autor*innen") == "copyright"  # a © without a DOI stamp
    stamp = "© 2027 bei den Autor*innen | https://doi.org/10.1515/x-001"
    assert kind(stamp + "\nISBN 978-3-11-225885-9") == "copyright"  # the ISBN still counts
