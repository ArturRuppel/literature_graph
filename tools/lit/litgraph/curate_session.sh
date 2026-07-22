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

# Resume this paper's session if one exists; otherwise start it with the curation preamble.
# The `.seeded` marker skips the resume attempt on a paper's first-ever open (no "no
# conversation" flash). But the marker can go stale — written here before Claude's first
# reply is what actually persists a conversation, so a pane opened then closed too early
# leaves a marker with nothing to resume. Guard against that: if `--continue` finds nothing
# it exits non-zero, and we fall through and (re)seed rather than loop on a dead resume.
if [[ -e .seeded ]]; then
  claude --continue && exit 0
fi
: > .seeded
exec claude "We are curating $key. Data root: $data (pass --root there to every lit command). \
First read $docs/CURATION.md for the protocol, then read the paper in full and work out its \
structure on your own. Do NOT propose, summarise, list, or tokenize anything yet — when you have \
finished reading and are oriented, reply with exactly: I'm ready. — and nothing else. From then on \
we communicate through the card, one pass at a time: when I tell you to launch a pass, write that \
pass's proposed slices directly into curated/$key.yaml — that edit is your proposition, not chat \
prose. Run lit build first to confirm it validates, then tell me to reload. I'll review it in the \
card and tell you what to keep, edit, or revert before the next pass. Use lit focus $key --quote \
\"<verbatim sentence>\" to aim my PDF pane whenever we're discussing a specific passage. Pick up \
from wherever curated/$key.yaml leaves off."
