#!/usr/bin/env python3
"""Convert a v0.3-era GenVM artifact to the v0.6 runner's API surface.

Six substitutions, exactly the set Sentinel migrated with. Each is verified
before and after rather than fired blind: a silent no-op here produces an
artifact that deploys and then fails at the first storage access, which is the
expensive way to find out.

The header rewrite is the one that cannot be done with a regex over the whole
file. GenVM parses the contiguous leading `#` block as the runner JSON, so the
version line and the Depends line must be the first two lines with nothing
between them and the imports.
"""
import re
import sys
from pathlib import Path

RUNNER = "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng"
HEADER = '# v0.3.0\n# { "Depends": "%s" }\n' % RUNNER

# (label, pattern, replacement). Bare-name rules are guarded with a negative
# lookbehind for `.` so a second run cannot turn gl.storage.TreeMap into
# gl.storage.gl.storage.TreeMap.
RULES = [
	("gl.Contract -> gl.contract.Contract", r"\bgl\.Contract\b", "gl.contract.Contract"),
	("gl.message_raw -> gl.message.raw", r"\bgl\.message_raw\b", "gl.message.raw"),
	("allow_storage -> gl.storage.allow", r"(?<![\w.])allow_storage\b", "gl.storage.allow"),
	("TreeMap -> gl.storage.TreeMap", r"(?<![\w.])TreeMap\b", "gl.storage.TreeMap"),
	("DynArray -> gl.storage.DynArray", r"(?<![\w.])DynArray\b", "gl.storage.DynArray"),
	# NOT on the migration list handed to this script, and MEASURED on chain:
	# v0.6 has no gl.get_contract_at. A probe deployed to studio-dev answered
	# "AttributeError: module 'genlayer' has no attribute 'get_contract_at'".
	# SkillConsumer wraps both of its cross-contract reads in `except
	# Exception` so that an unreachable oracle refunds instead of reverting —
	# which means this migration gap does NOT crash, it silently degrades every
	# lookup to "oracle unreachable" and the composability story dies quietly.
	# gl.contract.get_at is the v0.6 spelling; the same probe confirmed it
	# reads get_config and get_latest across the boundary.
	("gl.get_contract_at -> gl.contract.get_at", r"\bgl\.get_contract_at\b", "gl.contract.get_at"),
]

# gl.evm.contract_interface is UNCHANGED in v0.6 and must not be rewritten —
# only the bare gl.contract_interface moved (to gl.contract.interface). Neither
# artifact uses the bare form; the check below is here so that a future one
# cannot slip through unnoticed.
BARE_INTERFACE = r"(?<!evm\.)(?<!\w)gl\.contract_interface\b"


def convert(src: Path, dst: Path) -> int:
	text = src.read_text(encoding="utf8")
	lines = text.split("\n")

	# Drop every leading comment line — the old runner header — and put the new
	# one in its place. Anything else at the top would be read as runner JSON.
	i = 0
	while i < len(lines) and lines[i].startswith("#"):
		i += 1
	body = "\n".join(lines[i:]).lstrip("\n")

	# The v0.6 submodules (gl.storage, gl.contract) are reached through the
	# module object, which the star import does not provide. Sentinel's proven
	# order: the aliased import FIRST, then the star import.
	if not re.search(r"^import genlayer as gl$", body, re.M):
		body = "import genlayer as gl\n" + body

	out = HEADER + body
	print(f"\n{src.name} -> {dst.name}")
	total = 0
	for label, pattern, repl in RULES:
		out, n = re.subn(pattern, repl, out)
		total += n
		print(f"  {label:<42} {n} replaced")
		if n == 0:
			print(f"  !! nothing matched for {label}")
	# Nothing from the old surface may survive.
	if re.search(BARE_INTERFACE, out):
		print("  !! gl.contract_interface (bare) present — v0.6 moved it to gl.contract.interface")
		return 1
	leftovers = []
	for pattern, name in [(r"\bgl\.get_contract_at\b", "gl.get_contract_at"),
			(r"\bgl\.Contract\b", "gl.Contract"),
			(r"\bgl\.message_raw\b", "gl.message_raw"),
			(r"(?<![\w.])allow_storage\b", "allow_storage"),
			(r"(?<![\w.])TreeMap\b", "TreeMap"),
			(r"(?<![\w.])DynArray\b", "DynArray")]:
		if re.search(pattern, out):
			leftovers.append(name)
	if leftovers:
		print("  !! STILL PRESENT:", ", ".join(leftovers))
		return 1
	dst.write_text(out, encoding="utf8")
	print(f"  {total} substitutions, {len(out.encode()):,} bytes written")
	return 0


if __name__ == "__main__":
	root = Path(__file__).resolve().parent.parent
	out = root / "build" / "v06"
	out.mkdir(parents=True, exist_ok=True)
	rc = 0
	for name in ("SkillVerify", "SkillConsumer"):
		rc |= convert(root / "build" / f"{name}.min.py", out / f"{name}.v06.py")
	sys.exit(rc)
