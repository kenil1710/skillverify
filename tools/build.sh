#!/usr/bin/env bash
# Builds the deploy artifacts from the readable sources.
#
#   bash tools/build.sh
#
# Two stages, deliberately separate:
#   1. minify — strips comments, docstrings and blank lines
#   2. mangle — shortens identifiers, source untouched
#
# Bradbury refused a 59,278-byte comment-stripped artifact with
# BlockPubdataLimitReached in an earlier project, which is what stage 2 exists
# for. The name map it emits is not a courtesy: test_logic.py re-runs its whole
# battery against the ARTIFACT through that map, so the transform is verified
# rather than assumed. A mangle that silently merged two identifiers once
# validated every market with its own question as its aggregator, and it passed
# lint.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build

for name in SkillVerify SkillConsumer; do
  python3 tools/minify_contract.py "contracts/$name.py" -o "build/$name.premangle.py" | sed 's/^/  /'
  # The pre-mangle text is committed: the collision regression compares
  # replacement names against exactly what the mangler read, and diffing against
  # it is how a reader checks the mangle did nothing but rename.
  python3 tools/mangle_names.py "build/$name.premangle.py" \
      -o "build/$name.min.py" --map "build/$name.names.json" | sed 's/^/  /'
  python3 -c "import ast; ast.parse(open('build/$name.min.py').read())"
  "$HOME/.local/bin/genvm-lint" check "build/$name.min.py" | grep -E 'Lint passed|Validation passed' | sed 's/^/  /'
  printf "  %7d bytes  build/%s.min.py\n\n" "$(wc -c < "build/$name.min.py")" "$name"
done
