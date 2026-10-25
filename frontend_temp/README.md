# Temporary local PDF upload page

This is a disposable convenience page outside Step 18. It calls the existing converter as a child process and does not import `book_core`. The server uses Python's standard library (`http.server`); the page uses plain HTML, CSS and JavaScript, with no frontend dependencies or external resources. No framework or additional package installation is needed for the page.

From the repository root, start it with:

```powershell
.venv\Scripts\python.exe -B frontend_temp\server.py
```

Open **http://127.0.0.1:8765** in a browser on this computer. Keep the server and page open until the job finishes. Use Ctrl+C in the server terminal to stop it. The layout also fits a phone-sized browser window; it is not accessible from another device.

On the AMD PC, after following [the optional AMD setup](../docs/amd_gpu.md), set
`converter_python` in `settings.json` to `../.venv-amd/Scripts/python.exe` and start
the server with `.venv-amd\Scripts\python.exe -B frontend_temp\server.py`.
Required model assets must also be provisioned in the private runtime cache
described below. There is no `npm install` step.

## Settings and limits

Edit `frontend_temp/settings.json` before starting:

```json
{
  "port": 8765,
  "max_upload_bytes": 2000000000,
  "converter_python": "../.venv/Scripts/python.exe"
}
```

`max_upload_bytes` is the maximum file size in bytes: the default is decimal **2 GB (2,000,000,000 bytes)**. The page displays the configured maximum and rejects an oversized or empty file. `port` changes the local port and printed URL. `converter_python` is resolved relative to `frontend_temp/` and must point to the existing converter environment.

Files upload in sequential **4 MiB chunks** using browser `Blob` slices. The server streams each request to disk through **64 KiB buffers**; it does not hold the full upload in memory. The progress bar advances after each accepted chunk. Before accepting an upload and during processing, the server requires a **5 GB (5,000,000,000 bytes) free-disk reserve**, in addition to the incoming file and the unreceived bytes reserved for other outstanding uploads. It refuses a request with a clear disk-space error when there is insufficient space. Conversion outputs can need additional disk space.

Cancel stops an upload or requests termination of the converter. The page waits for a terminal status before allowing another upload. Cancellation retains partial uploads, generated outputs and caches; it performs no cache cleanup.

## Conversion and results

One background worker runs conversions serially using the existing command:

```text
<converter_python> -B -m book_core run-book <job>/input.pdf --out <job>/output --cache-dir frontend_temp/runtime/cache --workers 1
```

The paths passed to the child are resolved local paths. The command uses the converter's default profile, including automatic device selection and the existing Spanish/English defaults (`spa`, `eng`). The wrapper does not change backend source, profiles or settings.

Each job lives under `frontend_temp/runtime/jobs/<id>/`. Its `status.json` persists upload progress and the `queued`, `running`, `done` or `failed` conversion status. The browser polls that file through the local API. `converter.log` captures child-process output and `command.json` records its arguments. When a job is done, the page provides downloads for:

- `book.json`, produced by the existing converter.
- `review_list.json`, a convenience export of `book.json`'s embedded `review` value. This extra export is not part of the converter's original manifest.
- `manifest.json`, produced by the existing converter.

The wrapper uses its own fresh cache under `frontend_temp/runtime/cache/`, leaving pre-existing caches untouched. If optional model extras are installed, their required assets must already be provisioned locally under `frontend_temp/runtime/cache/huggingface/`. The child runs with model-library offline settings and telemetry disabled; the page does not download model assets. Missing local assets can cause a conversion failure, explained in its log.

Restarting the server marks interrupted, nonterminal jobs as failed and retains their files. There is no upload-resume or previous-job browser interface; a page refresh does not restore the active job view.

## Local-only use

**PyMuPDF is AGPL: do not expose it to other people or a network without a licence.**

The server is hard-bound to `127.0.0.1`, with loopback `Host` and same-origin checks and a per-server token for mutations. Use the exact printed `127.0.0.1` URL. There are no external network requests, CDN assets or externally loaded scripts. Do not place this server behind a proxy, share it, or expose its port to a network.

The frontend source is tracked in Git after the Step 18 freeze. `node_modules/`,
runtime uploads/caches/outputs, process IDs, logs and generated check results stay
ignored. They are not needed in a clone and are never pushed with the source.
Work here does not require the full test suite or benchmarks.

## Files and historical local verification

The application files are `server.py`, `settings.json`, `index.html`, `style.css`, `app.js` (111 lines), and this README. Generated uploads, status files, logs, model assets, conversion caches and outputs stay in `runtime/`. Five existing model directories were copied into its private Hugging Face cache for the offline check; no packages or models were downloaded.

`smoke_check.py` passed 18 local HTTP checks, including a successful conversion of the approved **nine-page art-therapy PDF** using the default profile and all three downloads. A synthetic file of 2 GB + 1 byte checked the size limit; deterministic free-space responses checked insufficient disk space and concurrent reservations without filling the drive. The dummy and its uploaded copies were deleted after checking. No large real book, full test suite, or benchmark was run.

`check_cancel.py` passed 10 checks using the same art-therapy PDF: cancelling a queued job, terminating a running converter, persisted status and retained caches. `check_ui.js` passed eight JavaScript behavior checks with Node's built-in modules and a mocked DOM/fetch; these did not run another conversion. `smoke_results.json`, `cancel_check_results.json` and `ui_check_results.json` record the results. Browser automation was unavailable, so the responsive CSS has not had a rendered browser check.

`check_protected.py`, `protected_before.json`, `protected_check_results.json` and `protected_check.log` recorded a file-size/modification-time audit of accessible protected files during the original local frontend task. Some existing directories were unreadable in that session. Separate `prefreeze_disk_budget` work appeared under `experiments/` during that task; those files were left untouched. No protected file was edited by that temporary-page task. Generated receipts and the machine-local audit inventory remain local; the audit script requires that local inventory and is not a new-PC setup check. These historical conversions were not repeated when publishing the frontend source.
