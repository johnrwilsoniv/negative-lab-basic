#!/usr/bin/env bash
# Build the rig's pages and publish them to nlb.jrwiv.com (nginx on bunbun, behind NPM on eggo).
#
#   ./publish.sh [slot] [--wd W] [--axis A]
#
# The slot defaults to the current branch (lowercased, "/" and "_" to "-"). main is the site itself, published from
# a clean main; any other slot is a design branch's preview at nlb.jrwiv.com/<slot>/. --wd and --axis go to both
# build.py and website.py. NLB_HOST and NLB_DEST override bunbun and dev/docker/nlb-site.
set -euo pipefail
cd "$(dirname "$0")"
host=${NLB_HOST:-bunbun}
dest=${NLB_DEST:-dev/docker/nlb-site}
branch=$(git branch --show-current)
slot=$branch
if [[ $# -gt 0 && $1 != -* ]]; then slot=$1; shift; fi
slot=$(printf '%s' "$slot" | tr 'A-Z/_' 'a-z--')
if [[ $slot == main ]]; then
  [[ $branch == main ]] || { echo "publish.sh: main is published from the main branch (name another slot to preview $branch)" >&2; exit 2; }
  [[ -z $(git status --porcelain) ]] || { echo "publish.sh: commit first: main is published from a clean tree" >&2; exit 2; }
fi

uv run python build.py "$@"
uv run python website.py --slot "$slot" "$@"

# nginx runs as its own user: everything it serves must be world-readable (macOS's rsync has no --chmod)
chmod -R u=rwX,go=rX site-out deploy
ssh "$host" "mkdir -p $dest/site $dest/conf.d"
rsync -a deploy/compose.yaml "$host:$dest/"
rsync -a deploy/nginx.conf "$host:$dest/conf.d/default.conf"
rsync -a --delete "site-out/$slot/" "$host:$dest/site/$slot/"
# main also owns the site root: the home page and the icons (site-out's top-level files, not the slot folders)
if [[ $slot == main ]]; then rsync -a --exclude='*/' site-out/ "$host:$dest/site/"; fi
ssh "$host" "cd $dest && docker compose up -d --wait --quiet-pull && docker compose exec -T web nginx -s reload"

if [[ $slot == main ]]; then echo "https://nlb.jrwiv.com/"; else echo "https://nlb.jrwiv.com/$slot/"; fi
