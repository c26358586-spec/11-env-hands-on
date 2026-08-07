#!/usr/bin/env bash
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/exercises/apply-learning-stage.sh --list
  bash scripts/exercises/apply-learning-stage.sh --check <stage>
  bash scripts/exercises/apply-learning-stage.sh <stage>
  bash scripts/exercises/apply-learning-stage.sh --help

Stages must be applied in order: 5.2, 5.3, 5.4, 5.5.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

stage_patch() {
  case "$1" in
    5.2|5.3|5.4|5.5) printf 'exercises/%s/patches/lesson.patch\n' "$1" ;;
    *) return 1 ;;
  esac
}

previous_stage() {
  case "$1" in
    5.2) printf 'public starter\n' ;;
    5.3) printf '5.2\n' ;;
    5.4) printf '5.3\n' ;;
    5.5) printf '5.4\n' ;;
  esac
}

list_stages() {
  cat <<'LIST'
5.2  Minimal PR CI and governance gate
5.3  Go quality checks and Build Artifact
5.4  Disposable UT environment lifecycle
5.5  Formal infrastructure/API tests and evidence gate
LIST
}

ensure_clean_worktree() {
  git diff --quiet || die "Working tree has unstaged changes. Commit, stash, or revert them before applying a learning stage."
  git diff --cached --quiet || die "Index has staged changes. Commit, unstage, or stash them before applying a learning stage."
  [ -z "$(git ls-files --others --exclude-standard)" ] || die "Working tree has untracked files. Commit, remove, or stash them before applying a learning stage."
}

check_patch() {
  local stage="$1"
  local patch_path="$2"

  if git apply --check "$patch_path"; then
    return 0
  fi
  if git apply -R --check "$patch_path" >/dev/null 2>&1; then
    die "Stage ${stage} appears to be applied already. Inspect git log and continue with the next stage."
  fi
  die "Stage ${stage} patch does not match the current files. Expected previous stage: $(previous_stage "$stage"). Check the stage order and git status. patch=${patch_path}"
}

check_only=false
list_only=false
stage=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --list) list_only=true; shift ;;
    --check) check_only=true; shift ;;
    -*) die "Unknown option: $1" ;;
    *)
      [ -z "$stage" ] || die "Only one stage can be specified. first=${stage} extra=$1"
      stage="$1"
      shift
      ;;
  esac
done

if [ "$list_only" = true ]; then
  [ -z "$stage" ] || die "--list does not accept a stage."
  list_stages
  exit 0
fi

[ -n "$stage" ] || die "Stage is required. Use --list to see valid stages."
patch_path="$(stage_patch "$stage" || true)"
[ -n "$patch_path" ] || die "Unknown stage: ${stage}. Valid stages are 5.2, 5.3, 5.4, and 5.5."

root="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Git repository root could not be resolved."
cd "$root"
[ -f "$patch_path" ] || die "Learning stage patch is missing: ${patch_path}"

ensure_clean_worktree
check_patch "$stage" "$patch_path"

if [ "$check_only" = true ]; then
  printf 'Check OK: stage=%s patch=%s expected_previous=%s\n' "$stage" "$patch_path" "$(previous_stage "$stage")"
  exit 0
fi

git apply "$patch_path"
if ! git diff --check; then
  git apply -R "$patch_path"
  die "Applied patch produced whitespace errors and was reverted. stage=${stage} patch=${patch_path}"
fi

printf 'Applied learning stage: %s\n' "$stage"
printf 'Patch: %s\n' "$patch_path"
printf '\n'
printf 'Next steps:\n'
printf '  1. Inspect git status and git diff.\n'
printf '  2. Run the lesson checks.\n'
printf '  3. Commit and push before the next stage.\n'
printf '\n'
printf 'Recovery before commit:\n'
printf '  git apply -R %s\n' "$patch_path"
