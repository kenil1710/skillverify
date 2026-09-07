#!/usr/bin/env python3
"""
Shortens identifiers in a MINIFIED GenLayer contract. Source stays readable.

    python3 tools/mangle_names.py build/X.min.py -o build/X.min.py --map build/X.names.json

Why this exists: Bradbury refused a 59,278-byte artifact with
`BlockPubdataLimitReached`. Comments and docstrings were already stripped (the
minifier saves ~32%); what is left is mostly identifiers, and a contract that
explains itself well has long ones.

WHAT IS RENAMED
  - module-level functions and constants
  - PRIVATE contract methods (leading underscore) and their `self.` call sites
  - storage fields and @dataclass fields, with every attribute access
  - locals and parameters

WHAT IS NEVER RENAMED, and why each one would break something
  - the contract class name .............. the deploy targets it by name
  - PUBLIC method names .................. they are the ABI; the frontend and
                                           every cross-contract caller use them
  - anything used as a KEYWORD ARGUMENT .. `render(mode="text")` — the callee
                                           names the parameter, not us. Any name
                                           appearing as a kwarg ANYWHERE is
                                           excluded globally: `mode` is a local
                                           in get_leaderboard AND a kwarg here,
                                           and renaming it would corrupt the call
  - anything named in a getattr/setattr string .. `getattr(res, "status", None)`
                                           reaches a runtime object, not ours,
                                           and `status` is also a field of ours
  - imported names, builtins, foreign attributes .. `.calldata`, `.append`, `gl`
  - every string literal ................. the JSON keys views return ARE the
                                           API, and the prompts are behaviour

Names are assigned shortest-first by total byte weight, so the most frequent
identifier gets the shortest replacement.

The emitted name map is not a courtesy: `test_logic.py` runs its whole battery
against the artifact through it, which is what makes this transform verifiable
rather than merely plausible.
"""
import argparse
import ast
import io
import json
import keyword
import sys
import tokenize
from collections import Counter

# Never rename these: the runtime, the SDK, and the builtins.
RESERVED = set(dir(__builtins__)) | set(keyword.kwlist) | {
    "gl", "json", "typing", "dataclass", "allow_storage", "Address", "DynArray",
    "TreeMap", "u8", "u16", "u32", "u64", "u128", "u256", "i8", "i16", "i32",
    "i64", "bigint", "self", "Exception", "ValueError", "AttributeError",
    "isinstance", "getattr", "setattr", "hasattr", "len", "str", "int", "bool",
    "float", "list", "dict", "tuple", "set", "range", "sorted", "abs", "max",
    "min", "sum", "print", "type", "object", "True", "False", "None",
}

ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def short_names(reserved=frozenset()):
    """a, b, ... z, A, ... Z, aa, ab, ... — skipping anything reserved.

    `reserved` must contain EVERY identifier that already appears in the file,
    not merely the keywords. Handing out a name that is already in use collides
    with it, and the collision is invisible to both the parser and the linter:

        def create_market(self, question, ..., aggregator, ...):
            q = " ".join(str(question).split())   # source local, 1 char, kept
            ...                                    # `aggregator` renamed to `q`

    The assignment silently overwrote the parameter, and the market was then
    validated with the QUESTION as its aggregator. That shipped through
    `ast.parse`, through `genvm-lint check`, and was caught only by driving a
    market through the artifact end to end.
    """
    n = 1
    while True:
        idx = [0] * n
        while True:
            candidate = "".join(ALPHABET[i] for i in idx)
            if (candidate not in RESERVED and candidate not in reserved
                    and not keyword.iskeyword(candidate)):
                yield candidate
            pos = n - 1
            while pos >= 0:
                idx[pos] += 1
                if idx[pos] < len(ALPHABET):
                    break
                idx[pos] = 0
                pos -= 1
            if pos < 0:
                break
        n += 1


def analyse(src: str):
    """Split every identifier into renameable and load-bearing."""
    tree = ast.parse(src)

    contract_class = None
    public_methods, private_methods = set(), set()
    storage_fields, dataclass_fields = set(), set()
    module_names = set()
    class_names = set()

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_names.add(t.id)
        elif isinstance(node, ast.ClassDef):
            class_names.add(node.name)
            bases = [ast.dump(b) for b in node.bases]
            is_contract = any("Contract" in b for b in bases)
            is_dataclass = any(
                getattr(d, "id", getattr(d, "attr", "")) == "dataclass"
                for d in node.decorator_list
            )
            if is_contract:
                contract_class = node.name
            for b in node.body:
                if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                    (dataclass_fields if is_dataclass else storage_fields).add(b.target.id)
                elif isinstance(b, ast.FunctionDef):
                    # A dunder is NEVER private in the renameable sense: the
                    # runtime calls __init__ by name, and renaming it produced
                    # `Type error: ('__init__ is absent')` at validation.
                    if b.name.startswith("__") and b.name.endswith("__"):
                        public_methods.add(b.name)
                    elif b.name.startswith("_"):
                        private_methods.add(b.name)
                    else:
                        public_methods.add(b.name)

    # Locals and parameters, from every function anywhere in the file.
    locals_ = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        args = node.args
        for group in (args.posonlyargs, args.args, args.kwonlyargs):
            for a in group:
                if a.arg != "self":
                    locals_.add(a.arg)
        if args.vararg:
            locals_.add(args.vararg.arg)
        if args.kwarg:
            locals_.add(args.kwarg.arg)
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
                locals_.add(sub.id)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                locals_.add(sub.name)
            elif isinstance(sub, ast.comprehension):
                for nm in ast.walk(sub.target):
                    if isinstance(nm, ast.Name):
                        locals_.add(nm.id)

    # ---- the exclusions, each one load-bearing -----------------------------
    kwarg_names = set()
    getattr_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    kwarg_names.add(kw.arg)
            fn = node.func
            fname = getattr(fn, "id", getattr(fn, "attr", ""))
            if fname in ("getattr", "setattr", "hasattr") and node.args:
                for a in node.args[1:2]:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str):
                        getattr_names.add(a.value)

    # Attribute names we did NOT define — `.calldata`, `.append`, `.status_code`.
    our_attrs = storage_fields | dataclass_fields | private_methods | public_methods
    foreign_attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr not in our_attrs:
            foreign_attrs.add(node.attr)

    dunders = {n for n in (module_names | private_methods | storage_fields
                           | dataclass_fields | locals_ | class_names)
               if n.startswith("__") and n.endswith("__")}

    renameable = (module_names | private_methods | storage_fields
                  | dataclass_fields | locals_) - dunders
    protected = (RESERVED | public_methods | class_names | kwarg_names
                 | getattr_names | foreign_attrs | dunders | {contract_class})
    renameable -= protected

    return {
        "renameable": renameable,
        "renameable_attrs": (storage_fields | dataclass_fields | private_methods) - protected,
        "dunders": dunders,
        "contract_class": contract_class,
        "public_methods": public_methods,
        "excluded_kwargs": kwarg_names,
        "excluded_getattr": getattr_names,
    }


def mangle(src: str):
    info = analyse(src)
    renameable = info["renameable"]
    renameable_attrs = info["renameable_attrs"]

    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))

    # Weight by total bytes so the heaviest identifier gets the shortest name.
    weight = Counter()
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME or t.string not in renameable:
            continue
        prev = toks[i - 1] if i else None
        is_attr = prev is not None and prev.type == tokenize.OP and prev.string == "."
        if is_attr and t.string not in renameable_attrs:
            continue
        weight[t.string] += len(t.string)

    # Every identifier in the file is off-limits as a replacement, including the
    # ones being renamed away: a name is only free once nothing can still refer
    # to it, and scopes overlap here.
    in_use = {t.string for t in toks if t.type == tokenize.NAME}
    gen = short_names(reserved=in_use)
    mapping = {}
    for name, _w in weight.most_common():
        new = next(gen)
        while len(new) >= len(name):          # never make an identifier longer
            mapping[name] = name
            break
        else:
            mapping[name] = new

    # Rewrite by ABSOLUTE CHARACTER OFFSET, splicing from the end backwards.
    #
    # Reassembling from tokens loses whatever the tokenizer does not emit —
    # continuation lines, exact spacing — and reconstructing it is how a
    # "minifier" silently changes a program. Splicing leaves every byte the
    # transform does not explicitly touch exactly where it was.
    line_start = [0]
    for line in src.splitlines(keepends=True):
        line_start.append(line_start[-1] + len(line))

    edits = []
    for i, t in enumerate(toks):
        if t.type != tokenize.NAME:
            continue
        text = t.string
        if text not in mapping or mapping[text] == text:
            continue
        prev = toks[i - 1] if i else None
        is_attr = prev is not None and prev.type == tokenize.OP and prev.string == "."
        if is_attr and text not in renameable_attrs:
            continue
        srow, scol = t.start
        erow, ecol = t.end
        edits.append((line_start[srow - 1] + scol, line_start[erow - 1] + ecol, mapping[text]))

    out = src
    for start, end, replacement in sorted(edits, reverse=True):
        out = out[:start] + replacement + out[end:]
    return out, {k: v for k, v in mapping.items() if k != v}, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--map", required=True, help="where to write the name map")
    a = ap.parse_args()

    src = open(a.source, encoding="utf8").read()
    result, mapping, info = mangle(src)

    # The artifact must still parse, and must still expose the ABI unchanged.
    ast.parse(result)
    after = analyse(result)
    # The invariant is that every ORIGINAL public method still exists — not that
    # the sets match. A renamed private method loses its leading underscore and
    # is then classified as public, which is cosmetic; a missing public method
    # is a broken ABI.
    missing = info["public_methods"] - after["public_methods"]
    if missing:
        print(f"REFUSING: these public methods disappeared: {sorted(missing)}", file=sys.stderr)
        return 1
    renamed_public = info["public_methods"] & set(mapping)
    if renamed_public:
        print(f"REFUSING: public methods were renamed: {sorted(renamed_public)}", file=sys.stderr)
        return 1
    if after["contract_class"] != info["contract_class"]:
        print("REFUSING: the contract class name changed", file=sys.stderr)
        return 1
    if result.split("\n")[0] != src.split("\n")[0]:
        print("REFUSING: line 1 (the runner pin) changed", file=sys.stderr)
        return 1

    open(a.output, "w", encoding="utf8").write(result)
    json.dump(mapping, open(a.map, "w"), indent=0, sort_keys=True)
    saved = len(src) - len(result)
    print(f"{a.source}  {len(src):,} bytes")
    print(f"{a.output}  {len(result):,} bytes")
    print(f"renamed {len(mapping)} identifiers, saved {saved:,} ({saved / len(src) * 100:.1f}%)")
    print(f"kept {len(info['public_methods'])} public methods and the class name intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
