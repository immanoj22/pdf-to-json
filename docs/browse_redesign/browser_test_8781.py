import json, requests, sys
from playwright.sync_api import sync_playwright
S = sys.argv[1]; JOB = "b919e59e0c41d19b"; BASE = "http://127.0.0.1:8781"
HEAD = "d84496298e33ce19"
def lvl():
    for u in requests.get(f"{BASE}/api/jobs/{JOB}/pages/20/units").json()["units"]:
        if u["id"] == HEAD: return u["level"]
ok = []
def check(name, cond):
    ok.append((name, bool(cond))); print(("PASS " if cond else "FAIL ") + name)
errors = []
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    c = b.new_context(viewport={"width": 1500, "height": 950})
    c.add_init_script("try{localStorage.setItem('reviewer','Tester');localStorage.setItem('role','manager')}catch(e){}")
    pg = c.new_page(); pg.on("pageerror", lambda e: errors.append(str(e))); pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.goto(f"{BASE}/#/job/{JOB}/review?mode=browse&page=20")
    pg.wait_for_selector("[data-testid=unit]", timeout=60000); pg.wait_for_timeout(800)
    row = pg.locator(f"[data-unit='{HEAD}'][data-testid=unit]")
    blk = pg.locator(f"[data-testid=blk][data-unit='{HEAD}']")
    # mouse: hover list row -> PDF box lights; hover PDF box -> row lights; click PDF box -> row active
    row.hover(); pg.wait_for_timeout(150)
    check("hover row highlights PDF block", "hot" in (blk.get_attribute("class") or ""))
    pg.mouse.move(5, 5); blk.hover(); pg.wait_for_timeout(150)
    check("hover PDF block highlights row", "hot" in (row.get_attribute("class") or ""))
    blk.click(); pg.wait_for_timeout(300)
    check("click PDF block makes row active", "active" in (row.get_attribute("class") or ""))
    check("page fits the pane width", abs(pg.locator("[data-testid=page-image]").bounding_box()["width"] - (pg.locator(".pdfpane").bounding_box()["width"] - 18 - 82)) < 40)
    # keyboard: arrows move pages, / focuses search
    pg.mouse.move(700, 700); pg.keyboard.press("ArrowRight"); pg.wait_for_timeout(500)
    check("→ goes to page 21", pg.input_value(".btool [data-testid=page-no]") == "21")
    pg.keyboard.press("ArrowLeft"); pg.wait_for_timeout(500)
    check("← goes back to page 20", pg.input_value(".btool [data-testid=page-no]") == "20")
    pg.click("[data-testid=thumb][data-page='24']"); pg.wait_for_timeout(500)
    check("thumbnail jumps to page 24", pg.input_value(".btool [data-testid=page-no]") == "24")
    pg.keyboard.press("/"); check("/ focuses search", pg.evaluate("document.activeElement.dataset.testid") == "search")
    pg.keyboard.type("carbohydrates"); pg.keyboard.press("Enter"); pg.wait_for_selector("[data-testid=search-hit]", timeout=20000)
    pg.screenshot(path=f"{S}/after_search.png")
    pg.locator("[data-testid=search-hit]").first.click(); pg.wait_for_timeout(1200)
    first = pg.locator("[data-testid=search-hit]").first
    check("search hit opens its page with the block active", pg.input_value(".btool [data-testid=page-no]") == "13" and pg.locator(".brow.active").count() == 1)
    pg.fill(".btool [data-testid=page-no]", "20"); pg.keyboard.press("Enter"); pg.wait_for_selector(f"[data-unit='{HEAD}'][data-testid=unit]"); pg.wait_for_timeout(500)
    # edit: heading level 5 -> 3, preview then confirm
    base = lvl(); row = pg.locator(f"[data-unit='{HEAD}'][data-testid=unit]")
    row.locator("[data-testid=edit-block]").click()
    panel = row.locator("[data-testid=edit-panel]")
    groups = [t.strip() for t in panel.locator("h4").all_inner_texts()]
    check("heading panel groups", groups == ["WHAT IS IT?", "NUMBER", "TITLE", "MOVE / MERGE / SPLIT"] or [g.upper() for g in groups] == ["WHAT IS IT?", "NUMBER", "TITLE", "MOVE / MERGE / SPLIT"])
    panel.locator("[data-testid=level]").select_option("3"); panel.locator("[data-testid=set-level]").click()
    pg.wait_for_selector("[data-testid=preview-line]"); pg.wait_for_timeout(200)
    check("nothing saved before Confirm", lvl() == base)
    check("one-line preview shown", "→" in pg.inner_text("[data-testid=preview-line]"))
    pg.screenshot(path=f"{S}/after_edit_preview.png")
    pg.click("[data-testid=confirm-save]"); pg.wait_for_selector("[data-testid=status]:not([hidden])"); pg.wait_for_timeout(500)
    check("saved after Confirm", lvl() == 3)
    pg.screenshot(path=f"{S}/after_saved.png")
    pg.keyboard.press("Control+z"); pg.wait_for_timeout(1500)
    check("Ctrl+Z undoes it", lvl() == base)
    # paragraph panel + Esc
    prow = pg.locator("[data-type=paragraph][data-testid=unit]").first
    prow.locator("[data-testid=edit-block]").click(); pg.wait_for_selector("[data-testid=edit-panel]")
    pg.screenshot(path=f"{S}/after_paragraph_panel.png")
    pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
    check("Esc closes the panel", pg.locator("[data-testid=edit-panel]").count() == 0)
    b.close()
print("console/page errors:", errors)
print("ALL PASS" if all(v for _, v in ok) and not errors else "SOME FAILED")
