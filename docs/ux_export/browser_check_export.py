import sys, time, json, requests
from playwright.sync_api import sync_playwright
R=sys.argv[1]; B="http://127.0.0.1:8783"
A="b919e59e0c41d19b"; C="965d78af65efc4c4"
log=[]
def ok(name, cond):
    log.append((name, bool(cond))); print(("PASS " if cond else "FAIL ")+name)
with sync_playwright() as p:
    br=p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    def page(role, name):
        ctx=br.new_context(viewport={"width":1280,"height":1000})
        ctx.add_init_script(f"localStorage.setItem('reviewer','{name}');localStorage.setItem('role','{role}');")
        pg=ctx.new_page(); errs=[]; pg.on("pageerror", lambda e: errs.append(str(e))); pg._errs=errs; return pg
    pg=page("manager","Tester")
    # 1. blocked book: summary, lossless block, override download
    pg.goto(f"{B}/#/job/{A}/export"); pg.wait_for_selector("[data-testid=export-all]")
    pg.wait_for_selector("[data-testid=summary]")
    ok("summary shows FAIL", "FAIL" in pg.inner_text("[data-testid=summary]"))
    ok("summary reason in plain words", "lossless" in pg.inner_text("[data-testid=summary]").lower())
    pg.screenshot(path=f"{R}/shots/01_export_top_fail.png", full_page=True)
    # download blocked -> confirm dialog (manager)
    dialogs=[]
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    with pg.expect_download() as dl:
        pg.click(f"[data-testid=export-history] a[href$='/exports/4/formats/daisy3/delivery.zip']")
    ok("manager sees warning then downloads", dialogs and "Download it anyway" in dialogs[-1])
    pg.wait_for_timeout(800); pg.reload(); pg.wait_for_selector("[data-testid=export-history] table")
    txt=pg.inner_text("[data-testid=export-history]")
    ok("history records override by Tester", "downloaded anyway" in txt and "Tester" in txt)
    pg.screenshot(path=f"{R}/shots/02_download_history.png", full_page=True)
    # reviewer is told only a manager can
    rv=page("reviewer","Rita"); msgs=[]
    rv.on("dialog", lambda d: (msgs.append(d.message), d.accept()))
    rv.goto(f"{B}/#/job/{A}/export"); rv.wait_for_selector("[data-testid=export-history] table")
    try: rv.click("[data-testid=export-history] a[href$='/exports/4/formats/daisy3/delivery.zip']")
    except Exception as e: print(e)
    rv.wait_for_timeout(1000)
    ok("reviewer blocked with plain message", msgs and "Only a manager" in msgs[-1])
    # 2. export all on the two-format book with progress per format
    pg2=page("manager","Tester"); pg2.goto(f"{B}/#/job/{C}/export"); pg2.wait_for_selector("[data-testid=export-all]")
    ok("summary on existing export", pg2.locator("[data-testid=summary]").count()==1)
    pg2.check("[data-testid=override]") if pg2.locator("[data-testid=override]:visible").count() else None
    pg2.evaluate("(e)=>{const l=e.closest('label');l.style.display='block';l.hidden=false}", pg2.query_selector("[data-testid=override]"))
    pg2.check("[data-testid=override]")
    pg2.click("[data-testid=export-all]")
    pg2.wait_for_selector("[data-testid=progress-docbook]")
    pg2.wait_for_selector("[data-testid=progress-docbook]:has-text('working'), [data-testid=progress-epub]:has-text('working')", timeout=120000)
    pg2.screenshot(path=f"{R}/shots/03_progress_per_format.png", full_page=True)
    pg2.wait_for_selector("[data-testid=problems], [data-testid=no-problems]", timeout=240000)
    pg2.wait_for_selector("[data-testid=download-epub]")
    ok("both formats listed after run", pg2.locator("[data-testid=download-zip]").count()==1 and pg2.locator("[data-testid=download-epub]").count()==1)
    ok("problems link to review/browse", pg2.locator("[data-testid=problems] a[href*='review']").count()>0)
    pg2.screenshot(path=f"{R}/shots/04_result_problems.png", full_page=True)
    href=pg2.locator("[data-testid=problems] a[href*='mode=browse']").first.get_attribute("href")
    pg2.goto(f"{B}/{href}"); pg2.wait_for_timeout(2500)
    ok("problem link opens Browse page", "mode=browse" in pg2.url and pg2.locator("[data-testid=error]").count()==0)
    pg2.screenshot(path=f"{R}/shots/05_problem_link_browse.png")
    ok("no page errors", not pg._errs and not pg2._errs)
    br.close()
bad=[n for n,c in log if not c]; print("FAILED:",bad); sys.exit(1 if bad else 0)
