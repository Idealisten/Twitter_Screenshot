#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./publish.sh "commit message"

What it does:
  1. Checks the JavaScript syntax.
  2. Checks for whitespace/conflict-marker diff issues.
  3. Stages all current changes.
  4. Creates one commit with the provided message.
  5. Pushes the current branch to origin.

Set SKIP_CHECKS=1 to skip syntax/diff checks.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 || -z "${1// }" ]]; then
  usage >&2
  exit 1
fi

COMMIT_MESSAGE="$1"
BRANCH="$(git branch --show-current)"

if [[ -z "$BRANCH" ]]; then
  echo "Could not determine current git branch." >&2
  exit 1
fi

if [[ -z "$(git status --short)" ]]; then
  echo "No local changes to publish."
  exit 0
fi

echo "Publishing branch: $BRANCH"
echo
echo "Changed files:"
git status --short
echo

if [[ "${SKIP_CHECKS:-0}" != "1" ]]; then
  echo "Running checks..."
  git diff --check

  if [[ -f static/app.js ]]; then
    node --check static/app.js
  fi

  echo "Checks passed."
  echo
fi

git add -A

if git diff --cached --quiet; then
  echo "No staged changes after git add."
  exit 0
fi

git commit -m "$COMMIT_MESSAGE"
git push origin "$BRANCH"

echo
echo "Published successfully:"
git log -1 --oneline
