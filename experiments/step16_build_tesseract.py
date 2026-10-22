"""Build an Apache/BSD/Zlib-only Tesseract codec stack with a local compiler.

The UB and conda-forge binaries pull in GPL codec/archive dependencies. This
source build disables those optional paths; input images use PNG or PNM.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import urllib.request
import zipfile
from pathlib import Path

from step16_provision_ocr import ASSETS, OUT, ROOT, download, reserve

BUILD = ASSETS / "source_build"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "book-core-ocr-build"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def audit():
    result = {"tools": [], "sources": []}
    for name, version in (
        ("ziglang", "0.15.2"),
        ("cmake", "3.31.6"),
        ("ninja", "1.11.1.4"),
    ):
        data = json.loads(fetch(f"https://pypi.org/pypi/{name}/{version}/json"))
        wheel = next(u for u in data["urls"] if u["filename"].endswith("win_amd64.whl"))
        result["tools"].append(
            {
                "name": name,
                "version": version,
                "license": data["info"].get("license_expression")
                or data["info"].get("license"),
                **wheel,
            }
        )
    for name, repo, tag, license_name, license_file in (
        ("zlib", "madler/zlib", "v1.3.1", "Zlib", "LICENSE"),
        ("libpng", "pnggroup/libpng", "v1.6.50", "libpng-2.0", "LICENSE"),
        (
            "leptonica",
            "DanBloomberg/leptonica",
            "1.86.0",
            "BSD-2-Clause",
            "leptonica-license.txt",
        ),
        ("tesseract", "tesseract-ocr/tesseract", "5.5.3", "Apache-2.0", "LICENSE"),
    ):
        ref = json.loads(
            fetch(f"https://api.github.com/repos/{repo}/git/ref/tags/{tag}")
        )
        obj = ref["object"]
        while obj["type"] != "commit":
            obj = json.loads(fetch(obj["url"]))["object"]
        revision = obj["sha"]
        licence = fetch(
            f"https://raw.githubusercontent.com/{repo}/{revision}/{license_file}"
        )
        (OUT / f"build_{name}_LICENSE.txt").write_bytes(licence)
        result["sources"].append(
            {
                "name": name,
                "repo": repo,
                "tag": tag,
                "revision": revision,
                "license": license_name,
                "license_file": license_file,
                "url": f"https://codeload.github.com/{repo}/zip/{revision}",
            }
        )
    result["disk"] = reserve(sum(t["size"] for t in result["tools"]) + 1_300_000_000)
    (OUT / "source_build_plan.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "tools": [
                    (t["name"], t["version"], t["size"], t["license"])
                    for t in result["tools"]
                ],
                "sources": result["sources"],
                "disk": result["disk"],
            },
            indent=2,
        )
    )


def zig_direct_audit():
    metadata = json.loads(fetch("https://ziglang.org/download/index.json"))["0.15.2"][
        "x86_64-windows"
    ]
    (OUT / "zig_official_download.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


def acquire():
    plan = json.loads((OUT / "source_build_plan.json").read_text(encoding="utf-8"))
    reserve(sum(t["size"] for t in plan["tools"]) + 1_300_000_000)

    def acquire_tool(tool):
        if tool["name"] == "ziglang" and (OUT / "zig_official_download.json").exists():
            official = json.loads(
                (OUT / "zig_official_download.json").read_text(encoding="utf-8")
            )
            path = BUILD / "downloads" / official["tarball"].rsplit("/", 1)[-1]
            record = download(
                official["tarball"], path, int(official["size"]), official["shasum"]
            )
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    target = (
                        BUILD / "tools/ziglang" / Path(*Path(member.filename).parts[1:])
                    )
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))
            print("Acquired official Zig distribution", flush=True)
            return record
        path = BUILD / "downloads" / tool["filename"]
        record = download(tool["url"], path, tool["size"], tool["digests"]["sha256"])
        with zipfile.ZipFile(path) as archive:
            archive.extractall(BUILD / "tools")
        print(f"Acquired {tool['name']}", flush=True)
        return record

    def acquire_source(source):
        path = BUILD / "downloads" / f"{source['name']}-{source['revision']}.zip"
        record = download(source["url"], path)
        with zipfile.ZipFile(path) as archive:
            archive.extractall(BUILD / "sources")
        print(f"Acquired source {source['name']}", flush=True)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
        futures = [executor.submit(acquire_tool, tool) for tool in plan["tools"]]
        futures.extend(
            executor.submit(acquire_source, source) for source in plan["sources"]
        )
        manifest = [future.result() for future in futures]
    (OUT / "source_build_downloads.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Audited source stack and build tools downloaded/extracted; no compiler executed."
    )


def build():
    plan = json.loads((OUT / "source_build_plan.json").read_text(encoding="utf-8"))
    cmake = BUILD / "tools/cmake/data/bin/cmake.exe"
    ninja = BUILD / "tools/ninja/data/bin/ninja.exe"
    zig = BUILD / "tools/ziglang/zig.exe"
    prefix = BUILD / "installed"
    BUILD.mkdir(parents=True, exist_ok=True)
    toolchain = BUILD / "toolchain.cmake"
    toolchain.write_text(
        "set(CMAKE_SYSTEM_NAME Windows)\nset(CMAKE_SYSTEM_PROCESSOR AMD64)\n"
        f'set(CMAKE_C_COMPILER "{zig.as_posix()}")\nset(CMAKE_C_COMPILER_ARG1 "cc")\n'
        f'set(CMAKE_CXX_COMPILER "{zig.as_posix()}")\nset(CMAKE_CXX_COMPILER_ARG1 "c++")\n'
        f'set(CMAKE_AR "{zig.as_posix()}")\nset(CMAKE_RANLIB "{zig.as_posix()}")\n'
        'set(CMAKE_C_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")\n'
        'set(CMAKE_CXX_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")\n'
        'set(CMAKE_C_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")\n'
        'set(CMAKE_CXX_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["ZIG_GLOBAL_CACHE_DIR"] = str(BUILD / "zig-global-cache")
    environment["ZIG_LOCAL_CACHE_DIR"] = str(BUILD / "zig-local-cache")
    commands = []
    common = [
        "-G",
        "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        f"-DCMAKE_PREFIX_PATH={prefix}",
        "-DBUILD_SHARED_LIBS=OFF",
    ]
    flags = {
        "zlib": ["-DZLIB_BUILD_EXAMPLES=OFF"],
        "libpng": ["-DPNG_SHARED=OFF", "-DPNG_TESTS=OFF", "-DPNG_EXECUTABLES=OFF"],
        "leptonica": [
            "-DSW_BUILD=OFF",
            "-DBUILD_PROG=OFF",
            "-DENABLE_GIF=OFF",
            "-DENABLE_JPEG=OFF",
            "-DENABLE_TIFF=OFF",
            "-DENABLE_WEBP=OFF",
            "-DENABLE_OPENJPEG=OFF",
        ],
        "tesseract": [
            "-DSW_BUILD=OFF",
            "-DBUILD_TRAINING_TOOLS=OFF",
            "-DBUILD_TESTS=OFF",
            "-DDISABLE_ARCHIVE=ON",
            "-DDISABLE_CURL=ON",
            "-DDISABLE_TIFF=ON",
            "-DGRAPHICS_DISABLED=ON",
            "-DOPENMP_BUILD=OFF",
            "-DENABLE_PRECOMPILED_HEADERS=OFF",
            "-DENABLE_LTO=OFF",
        ],
    }
    for source in plan["sources"]:
        name = source["name"]
        directory = next(
            p
            for p in (BUILD / "sources").iterdir()
            if p.name.endswith(source["revision"])
        )
        output = BUILD / "build" / name
        steps = [
            [
                str(cmake),
                "-S",
                str(directory),
                "-B",
                str(output),
                *common,
                *flags[name],
            ],
            [str(cmake), "--build", str(output), "--parallel", "4"],
            [str(cmake), "--install", str(output)],
        ]
        for index, command in enumerate(steps):
            commands.append(command)
            log = OUT / f"build_{name}_{index}.log"
            print(f"{name}: step {index}, log {log.relative_to(ROOT)}", flush=True)
            with log.open("w", encoding="utf-8") as stream:
                subprocess.run(
                    command,
                    env=environment,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
    executable = prefix / "bin/tesseract.exe"
    version = subprocess.run(
        [str(executable), "--version"], capture_output=True, text=True, check=True
    )
    (OUT / "source_build_result.json").write_text(
        json.dumps(
            {
                "commands": commands,
                "executable": executable.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
                "version": version.stdout + version.stderr,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(version.stdout + version.stderr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("audit", "acquire", "build", "zig-direct-audit")
    )
    args = parser.parse_args()
    {
        "audit": audit,
        "acquire": acquire,
        "build": build,
        "zig-direct-audit": zig_direct_audit,
    }[args.action]()
