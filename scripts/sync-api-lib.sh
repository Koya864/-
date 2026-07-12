#!/bin/sh
# tools/launchguard/ の診断ロジックを Vercel 用の api/_lib/ に同期する。
# 編集は必ず tools/launchguard/ 側で行うこと。
set -e
cd "$(dirname "$0")/.."
cp tools/launchguard/scan.py tools/launchguard/urlscan.py api/_lib/
echo "synced: tools/launchguard/{scan,urlscan}.py -> api/_lib/"
