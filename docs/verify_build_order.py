#!/usr/bin/env python3
"""verify_build_order.py — BUILD.md must point at things that exist.

BUILD.md is the only hand-written document in this repo that talks about all the
others: it names their checkpoints, their section numbers and their scripts. That
makes it the most likely thing here to rot, because renumbering a checkpoint in
radar-hardware.md leaves no trace anywhere else.

So it gets checked, like the drawings and the netlist do. Four rules:

  1. every relative link resolves to a file or directory that exists,
  2. every "Checkpoint N" resolves to a real checkpoint in the document BUILD.md
     was last talking about (the nearest document linked above it, within the
     same phase) — which is also how a reader resolves it,
  3. every "SS N" section reference resolves to a heading in that same document,
  4. every repo script named in a shell block exists.

It also prints the checkpoints BUILD.md does NOT gate on, so gaps are visible
rather than silent. That is a report, not a failure: not every checkpoint has to
be a phase gate.

    python3 verify_build_order.py        # exit 0 only if every reference resolves
"""
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = ROOT / "BUILD.md"

DOCS = ["docs/radar-hardware.md", "docs/radar-software.md",
        "docs/drone-hardware.md", "docs/drone-software.md"]

FAIL = []
def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def checkpoints(path):
    """{number: first line of the checkpoint} for one document."""
    out = {}
    for m in re.finditer(r"\*\*Checkpoint\s+(\d+)", (ROOT / path).read_text()):
        out.setdefault(int(m.group(1)), True)
    return out


def sections(path):
    """Numbered headings, including the ### subsections (2a, 2b, 2c ...)."""
    return {m.group(1) for m in
            re.finditer(r"^#{2,3}\s+(\d+[a-z]?)\.", (ROOT / path).read_text(), re.M)}


def main():
    if not BUILD.exists():
        sys.exit("BUILD.md is missing")
    text = BUILD.read_text()
    cps = {d: checkpoints(d) for d in DOCS}
    secs = {d: sections(d) for d in DOCS}

    # 1. links
    links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
    for t in links:
        if t.startswith(("http", "#", "mailto")):
            continue
        check((ROOT / t.split("#")[0]).exists(), f"BUILD.md links to {t}, which does not exist")

    # 2 + 3. checkpoints and section numbers, against the nearest document above
    phase, current, cited = None, None, {d: set() for d in DOCS}
    for line in text.splitlines():
        if line.startswith("## "):
            phase, current = line[3:].strip(), None
        for t in re.findall(r"\]\(([^)]+)\)", line):
            if t in DOCS:
                current = t
        # "Checkpoint 7", "Checkpoints 2, 4, 5 and 7", "Checkpoints 1 through 5"
        for m in re.finditer(r"Checkpoint[s]?\s+(\d+(?:\s*(?:,|and|through)\s*\d+)*)", line):
            raw = m.group(1)
            nums = [int(x) for x in re.findall(r"\d+", raw)]
            if "through" in raw and len(nums) == 2:
                nums = list(range(nums[0], nums[1] + 1))
            if current is None:
                check(False, f"[{phase}] 'Checkpoint {raw.strip()}' with no document named above it")
                continue
            for n in nums:
                check(n in cps[current],
                      f"[{phase}] Checkpoint {n} does not exist in {current} "
                      f"(it has {sorted(cps[current])})")
                cited[current].add(n)
        if current:
            for m in re.finditer(r"§\s*(\d+[a-z]?)", line):
                check(m.group(1) in secs[current],
                      f"[{phase}] {current} has no section {m.group(1)} "
                      f"(it has {sorted(secs[current])})")

    # 4. scripts named in shell blocks
    for m in re.finditer(r"^\s*(?:python3?|cd)\s+(\S+\.py)", text, re.M):
        name = m.group(1)
        hits = list(ROOT.rglob(name))
        check(bool(hits), f"BUILD.md runs {name}, which is not in the repo")

    for f in FAIL:
        print("ERROR:", f)
    n = sum(len(v) for v in cps.values())
    print(f"{len(links)} links, {n} checkpoints across {len(DOCS)} documents")
    if FAIL:
        sys.exit(1)
    print("BUILD ORDER VERIFIED — every checkpoint, section and script it names exists")
    for d in DOCS:
        missing = sorted(set(cps[d]) - cited[d])
        if missing:
            print(f"  note: {d} checkpoints not used as a gate: {missing}")


if __name__ == "__main__":
    main()
