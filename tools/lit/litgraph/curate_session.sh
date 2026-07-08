#!/usr/bin/env bash
# curate_session.sh — the command ttyd runs for each terminal pane in the curation cockpit
# (docs/2026-07-09-curation-cockpit-design.md §5). Given a citekey (from ttyd's --url-arg, i.e.
# the iframe's ?arg=<citekey>), drop into that paper's persistent Claude Code session: one hidden
# dir per paper, seeded once with a curation preamble, resumed thereafter. No tmux, no lingering
# process — persistence is the transcript on disk, so nothing accumulates but files.
#
# The launcher sets three env vars (cwd is only the resume key; instructions reach the session via
# the seed prompt, since CURATION.md lives in the code repo but curation runs against the data repo):
#   LIT_SESSIONS   dir holding the per-paper session folders (gitignored)
#   LIT_DATA_ROOT  the data repo (curated/, pdfs/) — passed to lit as --root
#   LIT_DOCS       the code repo root, where CURATION.md lives
set -euo pipefail

key="${1:-}"
[[ "$key" =~ ^[A-Za-z0-9]+$ ]] || { echo "usage: curate_session.sh <citekey>"; exit 2; }
sess="${LIT_SESSIONS:?set LIT_SESSIONS}"
data="${LIT_DATA_ROOT:?set LIT_DATA_ROOT}"
docs="${LIT_DOCS:?set LIT_DOCS}"

dir="$sess/$key"
mkdir -p "$dir"
cd "$dir"

if [[ -e .seeded ]]; then
  exec claude --continue
else
  : > .seeded
  exec claude "We are curating $key. Data root: $data (pass --root there to every lit command). \
Read $docs/CURATION.md and follow its four-pass protocol — one pass at a time, explain your \
reading and discuss before tokenizing into curated/$key.yaml. Mark passages in my PDF pane with: \
lit focus $key --quote \"<verbatim sentence>\". Pick up from wherever curated/$key.yaml leaves off."
fi
