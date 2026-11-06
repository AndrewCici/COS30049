#!/usr/bin/env bash
set -euo pipefail

# Builds the submission zip from a git ref using `git archive`, so it
# contains exactly what is committed to that ref -- nothing from
# .venv/, node_modules/, local caches, *.log files or any other
# untracked or gitignored file can leak in by construction, and nothing
# that IS committed can be silently left out either (unlike a plain
# `zip -r .` over the working tree, which depends on whatever happens
# to be sitting on disk at the time).
#
# Two categories of file are deliberately excluded even though they are
# committed:
#   - Assignment 2 artefacts not needed to run or grade Assignment 3
#     (the merged training dataset archive and the training split;
#     backend/ml/data/test_split.jsonl IS kept -- Part D's evasion
#     scripts read it directly).
#   - Private team working files (the video script, demo runbook and
#     requirements checklist) that must never leave the team's own
#     machines -- see docs/REQUIREMENTS_CHECKLIST.md's history for why.
#     As of the commit this script now runs against, those files no
#     longer exist in the repository at all (removed from history, not
#     merely untracked), so this is a defensive check that catches the
#     case where one gets re-added by accident, not a live exclusion.
#
# Usage (from anywhere; cds to the repository root itself):
#   scripts/make_submission_zip.sh [ref]
# `ref` defaults to HEAD. Run `git status` first if unsure whether HEAD
# has everything expected committed -- this script warns, but does not
# fail, on uncommitted changes, since a deliberate partial build is a
# valid use too.

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

REF="${1:-HEAD}"

OUT_DIR="$REPO_ROOT/submission"
mkdir -p "$OUT_DIR"
OUT_FILE="$OUT_DIR/session-08-group-6-A3-source.zip"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARNING: the working tree has uncommitted changes; they will NOT" >&2
  echo "be in this zip, since it is built from the committed ref '$REF':" >&2
  git status --short >&2
  echo >&2
fi

rm -f "$OUT_FILE"
git archive --format=zip --output="$OUT_FILE" "$REF" -- \
  . \
  ':(exclude)dataprep/merged_dataset.csv.zip' \
  ':(exclude)backend/ml/data/train_split.jsonl'

echo "Wrote $OUT_FILE"
echo

LISTING="$(unzip -l "$OUT_FILE")"

# Must be present: the app cannot run, or the security work cannot be
# reproduced, without these.
REQUIRED_PATHS=(
  "README.md"
  "backend/models/statistical_model.joblib"
  "backend/models/statistical_model.sha256"
  "backend/ml/data/test_split.jsonl"
  "security/dos/results"
  "security/misconfig/reports"
  "security/evasion/data/confusables.txt"
  "security/evasion/results/experiment.json"
)

# Must be ABSENT: Assignment 2 artefacts deliberately excluded above, and
# private team working files that should never have been committed past
# the history cleanup -- if any of these show up, something regressed.
FORBIDDEN_PATHS=(
  "dataprep/merged_dataset.csv.zip"
  "backend/ml/data/train_split.jsonl"
  "docs/VIDEO_SCRIPT.md"
  "docs/DEMO_RUNBOOK.md"
  "docs/REQUIREMENTS_CHECKLIST.md"
  "CLAUDE.md"
  "AGENTS.md"
  ".claude/"
)

PROBLEM=0

for path in "${REQUIRED_PATHS[@]}"; do
  if ! grep -q "$path" <<<"$LISTING"; then
    echo "MISSING (should be present): $path" >&2
    PROBLEM=1
  fi
done

for path in "${FORBIDDEN_PATHS[@]}"; do
  if grep -q "$path" <<<"$LISTING"; then
    echo "PRESENT (must be absent): $path" >&2
    PROBLEM=1
  fi
done

if [[ "$PROBLEM" -eq 1 ]]; then
  echo >&2
  echo "One or more checks above failed. The zip was still written; do" >&2
  echo "not submit it until every line above is resolved." >&2
  exit 1
fi

echo "All required paths present; all forbidden paths absent."
echo "Entries: $(unzip -l "$OUT_FILE" | tail -1 | awk '{print $2}')"
echo "Size: $(du -h "$OUT_FILE" | awk '{print $1}')"
echo
echo "Full listing:"
unzip -l "$OUT_FILE"
