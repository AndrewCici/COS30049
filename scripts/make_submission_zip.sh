#!/usr/bin/env bash
set -euo pipefail

# Builds a submission zip from a git ref using `git archive`, so it
# contains exactly what is committed to that ref -- nothing from
# .venv/, node_modules/, local caches, *.log files or any other
# untracked or gitignored file can leak in by construction, and nothing
# that IS committed can be silently left out either (unlike a plain
# `zip -r .` over the working tree, which depends on whatever happens
# to be sitting on disk at the time).
#
# Usage (from anywhere; cds to the repository root itself):
#   scripts/make_submission_zip.sh [ref]
# `ref` defaults to HEAD (the current branch's tip). Run `git status`
# first if unsure whether HEAD has everything you expect committed --
# this script warns, but does not fail, on uncommitted changes, since a
# deliberate partial submission is a valid use too.

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

REF="${1:-HEAD}"
COMMIT="$(git rev-parse --short "$REF")"
BRANCH="$(git rev-parse --abbrev-ref "$REF" 2>/dev/null || echo "$REF")"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

OUT_DIR="$REPO_ROOT/submission"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/cos30049-a3-${BRANCH}-${COMMIT}-${TIMESTAMP}.zip"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: the working tree has uncommitted changes; they will NOT" >&2
  echo "be in this zip, since it is built from the committed ref '$REF':" >&2
  git status --short >&2
  echo >&2
fi

git archive --format=zip --output="$OUT_FILE" "$REF"

echo "Wrote $OUT_FILE"
echo

# A handful of large or easy-to-forget files that MUST be present for the
# app to run or for the security work to be reproducible -- catches the
# case where one of them was accidentally left out of .gitignore's
# exceptions or never got committed, before this zip is submitted.
REQUIRED_PATHS=(
  "README.md"
  "backend/models/statistical_model.joblib"
  "backend/models/statistical_model.sha256"
  "backend/ml/data/test_split.jsonl"
  "dataprep/merged_dataset.csv.zip"
  "security/dos/results"
  "security/misconfig/reports"
  "security/evasion/data/confusables.txt"
  "security/evasion/results/experiment.json"
  "docs/VIDEO_SCRIPT.md"
  "docs/DEMO_RUNBOOK.md"
)

LISTING="$(unzip -l "$OUT_FILE")"
MISSING=0
for path in "${REQUIRED_PATHS[@]}"; do
  if ! grep -q "$path" <<<"$LISTING"; then
    echo "MISSING from zip: $path" >&2
    MISSING=1
  fi
done

if [[ "$MISSING" -eq 1 ]]; then
  echo >&2
  echo "One or more required paths are missing -- see above. The zip was" >&2
  echo "still written; do not submit it until this is resolved." >&2
  exit 1
fi

echo "All required paths present."
echo "Entries: $(unzip -l "$OUT_FILE" | tail -1 | awk '{print $2}')"
echo
echo "Inspect the full contents before submitting:"
echo "  unzip -l $OUT_FILE | less"
