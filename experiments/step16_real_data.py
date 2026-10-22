"""Pin and acquire explicitly listed public-domain Wikisource scan/ground-truth pairs.

Only GETs to Wikimedia hosts are allowed.  Human proofreading level must be >= 3,
scan metadata must explicitly identify public domain or CC BY, and every frozen artifact
gets a SHA-256.  The corpus is independent from the existing book references and gold.
The saved HTML/wikitext is the authority; plain text remains a derived, reviewable view.
"""

import argparse
import hashlib
import json
import re
import shutil
import stat
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = (
    "BookConverterOCRResearch/0.1 (read-only public-domain transcription audit)"
)
COPYRIGHT_POLICY = "https://wikisource.org/wiki/Wikisource:Copyright_policy"
CACHE = ROOT / ".cache/step16/wikimedia"


def fetch(url):
    host = urlparse(url).hostname or ""
    if not (
        host.endswith(".wikisource.org")
        or host
        in {
            "wikisource.org",
            "commons.wikimedia.org",
            "upload.wikimedia.org",
            "thumb.wikimedia.org",
        }
    ):
        raise ValueError("Only Wikimedia source hosts are allowed")
    cache = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ".bin")
    if cache.exists():
        return cache.read_bytes()
    request = Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(2)
    for attempt in range(2):
        try:
            response = urlopen(request, timeout=60)
            break
        except HTTPError as error:
            if error.code != 429 or attempt:
                raise
            delay = min(60, max(30, int(error.headers.get("Retry-After", 30))))
            print(f"Wikimedia rate limit; respecting {delay}s cooldown", flush=True)
            time.sleep(delay)
    with response:
        length = int(response.headers.get("Content-Length", 0))
        if length > 32_000_000:
            raise ValueError(
                "Unexpectedly large response; only individual page scans are allowed"
            )
        if shutil.disk_usage(ROOT).free - max(length, 32_000_000) < 5_000_000_000:
            raise ValueError("Download would breach the 5 GB disk reserve")
        payload = response.read(32_000_001)
    if len(payload) > 32_000_000:
        raise ValueError("Individual source response exceeds 32 MB limit")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(payload)
    return payload


def api(wiki, **params):
    url = f"https://{wiki}/w/api.php?" + urlencode(
        {"format": "json", "formatversion": 2, **params}
    )
    result = json.loads(fetch(url))
    if "error" in result:
        raise ValueError(result["error"])
    return result


def save(path, data, readonly=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, bytes):
        data = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"Refusing to overwrite frozen source data: {path}")
    if not path.exists():
        path.write_bytes(data)
    if readonly:
        path.chmod(stat.S_IREAD)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def inspect(row):
    if "raw_revision" in row:
        revision = row["raw_revision"]["query"]["pages"][0]["revisions"][0]
        return row.copy(), revision["slots"]["main"]["content"]
    wiki, title = row["wiki"], row["title"]
    revision_query = api(
        wiki,
        action="query",
        prop="revisions",
        titles=title,
        rvprop="ids|timestamp|content",
        rvslots="main",
    )
    page = revision_query["query"]["pages"][0]
    revision = page["revisions"][0]
    wikitext = revision["slots"]["main"]["content"]
    quality = re.search(r'<pagequality\s+level="([0-4])"', wikitext)
    quality = int(quality.group(1)) if quality else None
    file_title = "File:" + title.split(":", 1)[1].rsplit("/", 1)[0]
    number = int(title.rsplit("/", 1)[1])
    file_query = api(
        wiki,
        action="query",
        prop="imageinfo",
        titles=file_title,
        iiprop="timestamp|url|sha1|size|extmetadata",
        iiurlwidth=1920,
        iiurlparam=f"page{number}-1920px",
    )
    file_page = file_query["query"]["pages"][0]
    info = file_page.get("imageinfo", [{}])[0]
    metadata = info.get("extmetadata", {})
    short = metadata.get("LicenseShortName", {}).get("value", "")
    copyrighted = metadata.get("Copyrighted", {}).get("value", "")
    allowed = "public domain" in short.lower() or short.lower() in {
        "cc0",
        "cc by 4.0",
        "cc by 3.0",
    }
    if not short and copyrighted == "False":
        allowed = True
    result = {
        **row,
        "revision_id": revision["revid"],
        "revision_timestamp": revision["timestamp"],
        "source_url": f"https://{wiki}/w/index.php?oldid={revision['revid']}",
        "human_proofreading_level": quality,
        "file_title": file_title,
        "page_number": number,
        "file_timestamp": info.get("timestamp"),
        "file_sha1": info.get("sha1"),
        "file_url": info.get("url"),
        "scan_url": re.sub(r"-\d+px-", "-1920px-", info.get("thumburl") or ""),
        "license_short_name": short,
        "copyrighted": copyrighted,
        "license_url": metadata.get("LicenseUrl", {}).get("value"),
        "license_page": info.get("descriptionurl"),
        "status": "eligible_for_manual_text_qa"
        if allowed and quality in {3, 4}
        else "blocked_license_or_human_proofreading_not_verified",
        "raw_revision": revision_query,
        "raw_imageinfo": file_query,
    }
    return result, wikitext


def plain_text(parsed_html):
    tree = html.fromstring(parsed_html)
    bodies = tree.xpath(
        "//*[contains(concat(' ',normalize-space(@class),' '),' pagetext ')]"
    )
    if len(bodies) != 1:
        raise ValueError(
            "Expected one Wikisource pagetext element; manual parser check required"
        )
    body = bodies[0]
    for node in body.xpath(
        ".//*[contains(concat(' ',normalize-space(@class),' '),' mw-editsection ')]"
    ):
        node.drop_tree()
    return " ".join(body.text_content().split()) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "experiments/test_data/step16_real_scans"
    )
    parser.add_argument(
        "--audit-out", type=Path, default=ROOT / "experiments/out/step16/real_data"
    )
    args = parser.parse_args()
    candidates = json.loads(args.manifest.read_text("utf-8"))
    reports = []
    for row in candidates:
        try:
            result, wikitext = inspect(row)
            print(
                json.dumps(
                    {
                        k: result[k]
                        for k in (
                            "id",
                            "human_proofreading_level",
                            "license_short_name",
                            "status",
                        )
                    }
                ),
                flush=True,
            )
            if args.download and result["status"] == "eligible_for_manual_text_qa":
                parsed = api(
                    row["wiki"],
                    action="parse",
                    oldid=result["revision_id"],
                    prop="text",
                )
                rendered = parsed["parse"]["text"]
                data_root = args.out / row["id"]
                files = [
                    save(data_root / "page.jpg", fetch(result["scan_url"]), True),
                    save(data_root / "transcription.wikitext", wikitext, True),
                    save(data_root / "transcription.html", rendered, True),
                    save(data_root / "transcription.txt", plain_text(rendered), True),
                ]
                result["files"] = files
                result["ground_truth_basis"] = (
                    "Human-proofread faithful transcription of public-domain source; "
                    "modern editorial content is excluded from truth and requires manual QA. "
                    "No machine OCR output was used as ground truth."
                )
                result["copyright_policy"] = COPYRIGHT_POLICY
                result["status"] = "downloaded_pending_manual_text_qa"
                save(data_root / "source.json", result, True)
            reports.append(result)
        except (ValueError, OSError, KeyError, IndexError) as error:
            reports.append(
                {
                    **row,
                    "status": "blocked",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            print(json.dumps({"id": row["id"], "error": str(error)}), flush=True)
        time.sleep(0.1)
    args.audit_out.mkdir(parents=True, exist_ok=True)
    path = args.audit_out / (
        "download_manifest.json" if args.download else "source_audit.json"
    )
    path.write_text(
        json.dumps(reports, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n"
    )


if __name__ == "__main__":
    main()
