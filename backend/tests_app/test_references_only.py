"""Document type "References only": the whole PDF is one reference list (one bibliography part,
no chapter or heading detection), exported as the tail reference XML; the uncertain references
are review items. Also the structured-references option of the BITS/JATS profiles in the app."""

from __future__ import annotations

import io
import zipfile

import pytest

from .conftest import make_pdf, wait_state


def upload(client, pages=3):
    return client.put("/api/jobs?filename=refs.pdf", content=make_pdf(pages)).json()


def refs_job(client):
    job = upload(client)
    r = client.put(f"/api/jobs/{job['id']}/profile", json={"ref": "tail", "document_type": "references_only"})
    assert r.status_code == 200 and r.json()["document_type"] == "references_only", r.text
    assert client.post(f"/api/jobs/{job['id']}/convert").status_code == 200
    return wait_state(client, job["id"], {"converted", "failed"})


def test_the_type_fixes_the_parts_and_they_are_confirmed_by_the_type(client):
    job = refs_job(client)
    assert job["state"] == "converted"
    parts = client.get(f"/api/jobs/{job['id']}/parts").json()
    assert parts["references_only"] and parts["problems"] == []
    assert parts["parts"]["bibliography"] == {"first": 1, "last": 3}
    assert parts["parts"]["body"] is None and parts["confirmed"] is True
    again = client.put(f"/api/jobs/{job['id']}/parts", json={"parts": parts["parts"], "who": "A"})
    assert again.status_code == 409 and again.json()["code"] == "parts_fixed"


def test_the_type_is_chosen_before_the_conversion_only(client):
    job = upload(client)
    jid = job["id"]
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": "tail", "document_type": "nonsense"}).status_code == 400
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": "tail", "document_type": "references_only"}).status_code == 200
    back = client.put(f"/api/jobs/{jid}/profile", json={"ref": "tail", "document_type": "book"}).json()
    assert back["document_type"] == "book"
    assert client.get(f"/api/jobs/{jid}/parts/plan").json()["planned"] is False  # the fixed parts are gone
    client.put(f"/api/jobs/{jid}/profile", json={"ref": "tail", "document_type": "references_only"})
    assert client.post(f"/api/jobs/{jid}/convert").status_code == 200
    wait_state(client, jid, {"converted"})
    late = client.put(f"/api/jobs/{jid}/profile", json={"ref": "tail", "document_type": "book"})
    assert late.status_code == 409 and late.json()["code"] == "too_late"


def test_no_isbn_title_or_authors_are_asked_only_the_options(client):
    jid = refs_job(client)["id"]
    d = client.get(f"/api/jobs/{jid}/details").json()
    assert d["references_only"] and d["confirmed"] and "accents" in d["options"]
    assert d["details"]["options"]["accents"] == "sample-mapping"
    ok = client.put(f"/api/jobs/{jid}/details", json={"options": {"accents": "strip"}})
    assert ok.status_code == 200, ok.text
    assert client.get(f"/api/jobs/{jid}/details").json()["details"]["options"]["accents"] == "strip"


def test_the_uncertain_references_are_review_items(client):
    jid = refs_job(client)["id"]
    items = client.get(f"/api/jobs/{jid}/review").json()["items"]
    refs = [i for i in items if i["kind"] == "reference"]
    assert refs and "[4]" in refs[0]["reason"] and refs[0]["unit"]


def test_the_export_is_the_reference_list_and_no_other_format(client):
    jid = refs_job(client)["id"]
    client.put(f"/api/jobs/{jid}/details", json={"options": {"accents": "strip"}})
    other = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": ["docbook"]})
    assert other.status_code == 400 and other.json()["code"] == "format_not_supported"
    r = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": ["tail"]})
    assert r.status_code == 200, r.text
    res = r.json()
    qc = res["other_qc"]["tail"]
    assert qc["verdict"] in ("pass", "warn") and qc["dtd"]["errors"] == 0
    assert (qc["lossless"]["missing"], qc["lossless"]["extra"]) == (0, 0)
    z = client.get(f"/api/jobs/{jid}/exports/1/formats/tail/delivery.zip")
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert any(n.endswith("/tail.xml") for n in names)
    xml = zipfile.ZipFile(io.BytesIO(z.content)).read(next(n for n in names if n.endswith("tail.xml")))
    assert b'refcount="5"' in xml and b"Zivkovic" in xml  # the accent option of the details


@pytest.mark.parametrize("profile", ["jaypee_v3", "bits_base"])
def test_a_full_book_can_export_its_reference_list_as_tail(client, converted, profile):
    jid = converted["id"]
    assert client.put(f"/api/jobs/{jid}/profile", json={"ref": profile}).status_code == 200
    client.put(f"/api/jobs/{jid}/details", json={"isbn": "978-0-306-40615-7", "title": "T", "options": {}})
    r = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": ["tail"]})
    assert r.status_code == 200, r.text
    assert r.json()["other_qc"]["tail"]["dtd"]["errors"] == 0


def test_the_structured_references_option_is_offered_for_bits_and_jats(client):
    for ref in ("bits_base", "jats_base", "tribo_bits"):
        options = client.get(f"/api/profile-options?ref={ref}").json()["options"]
        assert options["structured_references"]["type"] == "boolean"


def test_a_flagged_reference_is_corrected_in_the_review_and_the_file_follows(client):
    jid = refs_job(client)["id"]
    review = client.get(f"/api/jobs/{jid}/review").json()
    item = next(i for i in review["items"] if i["kind"] == "reference")
    assert item["editor"] == "reference" and item["current"]["full_text"].startswith("[4]\nHarlan")
    fixed = "[4]\nHarlan JR. Crops and man. Agron J 1992; 5(1): 10-5."
    body = {"who": "Asha", "key": item["key"], "item_kind": "reference", "action": "fix", "note": "",
            "fix": {"op": "edit_text", "unit": item["unit"], "text": fixed},
            "item": {"kind": "reference", "reason": item["reason"]}}  # fmt: skip
    assert client.post(f"/api/jobs/{jid}/decisions", json=body).status_code == 200
    assert client.get(f"/api/jobs/{jid}/review").json()["stale"] is True  # the list is older than the change
    review = client.post(f"/api/jobs/{jid}/review/refresh").json()  # Refresh makes it again
    assert review["stale"] is False
    after = review["items"]
    left = [i for i in after if i["kind"] == "reference" and not i.get("resolved")]
    assert not left, [(i["reason"], i.get("decision")) for i in left]  # the flag is gone
    r = client.post(f"/api/jobs/{jid}/export", json={"who": "A", "formats": ["tail"]})
    assert r.status_code == 200, r.text
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/jobs/{jid}/exports/1/formats/tail/delivery.zip").content))
    xml = z.read(next(n for n in z.namelist() if n.endswith("tail.xml"))).decode("ascii")
    assert "<ref-sourcetitle>Agron J</ref-sourcetitle>" in xml and "Madison" not in xml
    assert r.json()["other_qc"]["tail"]["lossless"]["missing"] == 0
