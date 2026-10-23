"""Step 17 Part 1: seeded candidate pages for the added real scans (Chinese, Greek, Arabic).

For each listed Wikisource index (books chosen from the wikis' proofread-quality
categories: modern print, prose, no tables), the page titles at human proofreading level 3
or 4 are listed from the quality categories, and pages are drawn with a fixed seed
(``1700:<index>``), skipping the first pages of the file (covers, title pages). The
candidates are written in the ``step16_real_data`` manifest format; that script then
checks the licence and proofreading level of each page and downloads the eligible ones
(read-only test data).

Usage: python step17_real_candidates.py [--per-book N]
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "experiments")]
import step16_real_data as data

OUT = ROOT / "experiments/out/step17/real_data"
QUALITY = {
    "zh.wikisource.org": ("Page", ["已核对", "已校对"]),
    "el.wikisource.org": ("Σελίδα", ["Εγκρίθηκε", "Έχει γίνει τυπογραφικός έλεγχος"]),
    "ar.wikisource.org": ("صفحة", ["تم التحقق منها", "صححت"]),
}
# (id prefix, language, script label, wiki, index file name)
BOOKS = [
    (
        "zhs_report2017",
        "chi_sim",
        "Han (Simplified), horizontal",
        "zh.wikisource.org",
        "2017年政府工作报告.pdf",
    ),
    (
        "zhs_npc2018",
        "chi_sim",
        "Han (Simplified), horizontal",
        "zh.wikisource.org",
        "中华人民共和国全国人民代表大会常务委员会公报2018年特刊.pdf",
    ),
    (
        "zhs_court2021",
        "chi_sim",
        "Han (Simplified), horizontal",
        "zh.wikisource.org",
        "广东省高级人民法院（2021）粤民终1035号民事判决书.pdf",
    ),
    (
        "zht_cites1973",
        "chi_tra",
        "Han (Traditional), handwritten vertical",
        "zh.wikisource.org",
        (
            "Convention on International Trade in Endangered Species of Wild Fauna and Flora "
            "(CN-Text, 1973).pdf"
        ),
    ),
    (
        "zht_jiangxi",
        "chi_tra",
        "Han (Traditional), vertical print",
        "zh.wikisource.org",
        "NLC416-16jh002840-86952 江西學童智力測驗總報告.pdf",
    ),
    (
        "zht_renjian",
        "chi_tra",
        "Han (Traditional), vertical print",
        "zh.wikisource.org",
        "NCL-002426211 人間詞話.pdf",
    ),
    (
        "zht_latinguide",
        "chi_tra",
        "Han (Traditional), horizontal print",
        "zh.wikisource.org",
        "CADAL07016328 中國話寫法拉丁化指南.djvu",
    ),
    (
        "ell_fek2014",
        "ell",
        "Greek, monotonic, table pages",
        "el.wikisource.org",
        "ΦΕΚ Β 699 - 20.03.2014.pdf",
    ),
    (
        "ell_fek2008",
        "ell",
        "Greek, monotonic, two columns",
        "el.wikisource.org",
        "ΦΕΚ Α 120 - 27.06.2008.pdf",
    ),
    (
        "ell_fek2020",
        "ell",
        "Greek, monotonic",
        "el.wikisource.org",
        "ΦΕΚ 2084 - 30.05.2020.pdf",
    ),
    (
        "ell_axiotis",
        "ell",
        "Greek, polytonic",
        "el.wikisource.org",
        "Διηγήματα (Αξιώτης).pdf",
    ),
    (
        "ell_plori",
        "ell",
        "Greek, polytonic",
        "el.wikisource.org",
        "Λόγια της πλώρης (1924).djvu",
    ),
    (
        "ell_vizyinos",
        "ell",
        "Greek, polytonic",
        "el.wikisource.org",
        "Athides Aurai Georgios Vizyinos.djvu",
    ),
    (
        "ara_abbasid",
        "ara",
        "Arabic",
        "ar.wikisource.org",
        "محاضرات في تاريخ الدولة العباسية.pdf",
    ),
    (
        "ara_fadlan",
        "ara",
        "Arabic",
        "ar.wikisource.org",
        (
            "رسالة ابن فضلان في وصف الرحلة إلى بلاد الترك والخزر والروس والصقالبة سنة 309هـ 921م "
            "(ت. سامي الدهان) - أحمد بن فضلان.pdf"
        ),
    ),
    (
        "ara_mustalah",
        "ara",
        "Arabic",
        "ar.wikisource.org",
        "مصطلح التاريخ (الطبعة الثالثة).pdf",
    ),
    (
        "ara_muhandisin",
        "ara",
        "Arabic",
        "ar.wikisource.org",
        "أعلام المهندسين في الإسلام (الطبعة الأولى).pdf",
    ),
    (
        "ara_gibran1914",
        "ara",
        "Arabic",
        "ar.wikisource.org",
        "دمعة وابتسامة (1914) - جبران خليل جبران.pdf",
    ),
]
SKIP_FIRST = 4  # covers and title pages


def proofread_pages(wiki, index):
    namespace, categories = QUALITY[wiki]
    prefix = f"{namespace}:{index}/"
    found = set()
    for category in categories:
        cont = {}
        while True:
            result = data.api(wiki, action="query", list="categorymembers",
                              cmtitle="Category:" + category, cmlimit=500,
                              cmstartsortkeyprefix=index, **cont)  # fmt: skip
            members = result["query"]["categorymembers"]
            for member in members:
                if member["title"].startswith(prefix):
                    found.add(member["title"])
            beyond = members and not any(index in m["title"] for m in members[-5:])
            if "continue" not in result or beyond:
                break
            cont = {"cmcontinue": result["continue"]["cmcontinue"]}
    return sorted(found, key=lambda t: int(t.rsplit("/", 1)[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-book", type=int, default=3)
    args = parser.parse_args()
    rows, listing = [], {}
    for prefix, language, script, wiki, index in BOOKS:
        titles = [t for t in proofread_pages(wiki, index)
                  if int(t.rsplit("/", 1)[1]) > SKIP_FIRST]  # fmt: skip
        listing[prefix] = len(titles)
        chosen = random.Random(f"1700:{index}").sample(
            titles, min(args.per_book, len(titles))
        )
        for title in sorted(chosen, key=lambda t: int(t.rsplit("/", 1)[1])):
            number = title.rsplit("/", 1)[1]
            rows.append({"id": f"{prefix}_{number}", "language": language, "script": script,
                         "wiki": wiki, "title": title})  # fmt: skip
        print(prefix, len(titles), "proofread pages", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidates.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n",
                                         "utf-8", newline="\n")  # fmt: skip
    (OUT / "candidate_listing.json").write_text(json.dumps(listing, indent=2) + "\n", "utf-8",
                                                newline="\n")  # fmt: skip


if __name__ == "__main__":
    main()
