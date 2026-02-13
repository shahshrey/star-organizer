#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "================================================"
echo " Star Organizer — Live Integration Test"
echo " (organizes 5 repos, organize-only, no sync)"
echo "================================================"
echo ""

echo "1. Running with --test-limit 5 --organize-only --no-interactive"
echo "   This will fetch 5 starred repos and categorize them."
echo "   No GitHub lists will be created or modified."
echo ""

python -m star_organizer --test-limit 5 --organize-only --no-interactive

echo ""
echo "2. Checking output file..."
if [ -f organized_stars.json ]; then
    echo "   ✓ organized_stars.json exists"
    CATS=$(python -c "import json; d=json.load(open('organized_stars.json','r',encoding='utf-8')); print(len(d))")
    REPOS=$(python -c "import json; d=json.load(open('organized_stars.json','r',encoding='utf-8')); print(sum(len(v.get('repos',[])) for v in d.values()))")
    echo "   ✓ Categories: $CATS"
    echo "   ✓ Repos categorized: $REPOS"
else
    echo "   ✗ organized_stars.json not found"
    exit 1
fi

echo ""
echo "3. Running preview mode..."
python -c "
import sys
sys.path.insert(0, '.')
from star_organizer.display import print_categories_table
from star_organizer.store import load_organized_stars
data = load_organized_stars('organized_stars.json')
print_categories_table(data)
"

echo ""
echo "================================================"
echo " Live test complete!"
echo "================================================"
