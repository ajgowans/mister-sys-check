#!/bin/zsh
set -e

cd "$(dirname "$0")"

if [ -f "$HOME/.zshrc" ]; then
  source "$HOME/.zshrc"
fi

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python mistersyscheck.py

git add reports

if git diff --cached --quiet; then
  echo
  echo "No report changes to publish."
else
  git commit -m "Add MiSTer sys report $(date '+%Y-%m-%d %H:%M:%S')"
  git push
fi

echo
echo "Done. Press any key to close this window."
read -k 1
