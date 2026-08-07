#!/usr/bin/env bash
# Copyright 2026 Ranamicus Technology LLC. All rights reserved.

set -Eeuo pipefail

usage() {
  cat <<'USAGE'
Usage:
  bash scripts/exercises/apply-failure-scenario.sh [--dry-run] <scenario-id>
  bash scripts/exercises/apply-failure-scenario.sh --list
  bash scripts/exercises/apply-failure-scenario.sh --help

Applies a managed Lesson 5.6 failure scenario patch.

Options:
  --dry-run, --check  Verify that the patch can be applied, but do not modify files.
  --list             Show scenario IDs defined in exercises/5.6/scenarios.yml.
  --help             Show this help.

Safety checks:
  - Unknown scenario IDs fail before touching the working tree.
  - The working tree must be clean before applying or dry-running a known scenario.
  - The patch is checked with git apply --unidiff-zero --check before it is applied.
USAGE
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || die "Git repository root could not be resolved."
}

scenario_value() {
  local scenarios_file="$1"
  local wanted_id="$2"
  local wanted_field="$3"
  awk -v wanted_id="$wanted_id" -v wanted_field="$wanted_field" '
    function clean(value) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      gsub(/^["\047]|["\047]$/, "", value)
      return value
    }
    /^[[:space:]]*-[[:space:]]*id:[[:space:]]*/ {
      current = $0
      sub(/^[[:space:]]*-[[:space:]]*id:[[:space:]]*/, "", current)
      in_block = (clean(current) == wanted_id)
    }
    in_block {
      value = $0
      pattern = "^[[:space:]]*" wanted_field ":[[:space:]]*"
      if (value ~ pattern) {
        sub(pattern, "", value)
        print clean(value)
        found = 1
        exit
      }
    }
    END {
      if (!found) {
        exit 1
      }
    }
  ' "$scenarios_file"
}

list_scenarios() {
  local scenarios_file="$1"
  awk '
    function clean(value) {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
      gsub(/^["\047]|["\047]$/, "", value)
      return value
    }
    /^[[:space:]]*-[[:space:]]*id:[[:space:]]*/ {
      id = $0
      sub(/^[[:space:]]*-[[:space:]]*id:[[:space:]]*/, "", id)
      print clean(id)
    }
  ' "$scenarios_file"
}

ensure_clean_worktree() {
  if ! git diff --quiet; then
    die "Working tree has unstaged changes. Commit, stash, or revert them before applying a scenario."
  fi
  if ! git diff --cached --quiet; then
    die "Index has staged changes. Commit, unstage, or stash them before applying a scenario."
  fi
  if [ -n "$(git ls-files --others --exclude-standard)" ]; then
    die "Working tree has untracked files. Commit, remove, or stash them before applying a scenario."
  fi
}

dry_run=false
list_only=false
scenario_id=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    --dry-run|--check)
      dry_run=true
      shift
      ;;
    --list)
      list_only=true
      shift
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      if [ -n "$scenario_id" ]; then
        die "Only one scenario ID can be specified. first=${scenario_id} extra=$1"
      fi
      scenario_id="$1"
      shift
      ;;
  esac
done

ROOT="$(repo_root)"
cd "$ROOT"

SCENARIOS_FILE="exercises/5.6/scenarios.yml"
[ -f "$SCENARIOS_FILE" ] || die "Scenario file is missing: $SCENARIOS_FILE"

if [ "$list_only" = true ]; then
  list_scenarios "$SCENARIOS_FILE"
  exit 0
fi

[ -n "$scenario_id" ] || die "Scenario ID is required. Use --list to see available scenarios."

patch_path="$(scenario_value "$SCENARIOS_FILE" "$scenario_id" "patch" || true)"
[ -n "$patch_path" ] || die "Unknown scenario ID: ${scenario_id}. Use --list to see available scenarios."
[ -f "$patch_path" ] || die "Patch file for scenario ${scenario_id} is missing: ${patch_path}"
recovery_method="$(scenario_value "$SCENARIOS_FILE" "$scenario_id" "recovery_method" || true)"
[ -n "$recovery_method" ] || die "Recovery method for scenario ${scenario_id} is missing."

ensure_clean_worktree

if ! git apply --unidiff-zero --check "$patch_path"; then
  die "Patch cannot be applied cleanly. scenario=${scenario_id} patch=${patch_path}"
fi

if [ "$dry_run" = true ]; then
  printf 'Dry-run OK: scenario=%s patch=%s\n' "$scenario_id" "$patch_path"
  printf 'Recovery method: %s\n' "$recovery_method"
  printf '\n'
  printf 'Next steps:\n'
  printf '  1. Create a scenario branch from main.\n'
  printf '  2. Apply the scenario without --dry-run.\n'
  printf '  3. Commit and push the scenario change.\n'
  printf '  4. Open a scenario Pull Request.\n'
  printf '\n'
  printf 'WARNING: Do not merge the scenario Pull Request into main.\n'
  exit 0
fi

git apply --unidiff-zero "$patch_path"

printf 'Applied scenario: %s\n' "$scenario_id"
printf 'Patch file: %s\n' "$patch_path"
printf 'Recovery method: %s\n' "$recovery_method"
printf '\n'
printf 'Next steps:\n'
printf '  1. Review the diff and confirm VERSION is 0.0.1.\n'
printf '  2. Commit and push, then open a scenario PR with target_version: 0.0.1 and required_final_stage: UT.\n'
printf '  3. Confirm the expected failure and inspect the evidence Artifact.\n'
printf '  4. Repair only the injected defect by following the Recovery method above.\n'
printf '  5. Keep Issue target_version, PR target_version, and VERSION at 0.0.1.\n'
printf '  6. Commit and push the repair, then confirm pr-ci-gate is successful.\n'
printf '  7. Close the scenario PR without merging it.\n'
printf '  8. Comment on and close the Issue, then delete the scenario branch.\n'
printf '\n'
printf 'WARNING: Do not reverse the whole scenario patch when validating recovery, because that also restores VERSION to the base version.\n'
printf 'WARNING: Do not merge the scenario Pull Request into main.\n'
