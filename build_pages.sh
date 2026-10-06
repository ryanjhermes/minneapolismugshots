#!/usr/bin/env bash
# Build the GitHub Pages site in docs/ from mugshots/, the CSV, and rendered reels/.
# Used by daily-scrape (nightly) and dm-check (after a removal).
set -e
rm -rf docs
mkdir -p docs/mugshots
[ -d mugshots ] && cp -r mugshots/. docs/mugshots/
echo "✅ Mugshots copied: $(ls -1 docs/mugshots/*.jpg 2>/dev/null | wc -l) files"
cp jail_roster_data.csv docs/
# Reels are served from Pages only, never committed
[ -d reels ] && cp -r reels docs/

cat > docs/index.html <<HTML
<!DOCTYPE html>
<html>
<head>
    <title>Minneapolis Mugshots Data</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>Minneapolis Jail Roster Data</h1>
    <p>Last updated: $(date)</p>
    <ul>
        <li><a href="jail_roster_data.csv">Download CSV Data</a></li>
        <li><a href="mugshots/">View Mugshots Folder</a></li>
    </ul>
</body>
</html>
HTML

{
  echo '<!DOCTYPE html>
<html>
<head>
    <title>Mugshots Directory</title>
    <meta charset="utf-8">
</head>
<body>
    <h1>Mugshots Directory</h1>
    <p>Last updated: '"$(date)"'</p>
    <ul>'
  for img in docs/mugshots/*.jpg; do
    [ -f "$img" ] && echo "        <li><a href=\"$(basename "$img")\">$(basename "$img")</a></li>"
  done
  echo '    </ul>
</body>
</html>'
} > docs/mugshots/index.html
