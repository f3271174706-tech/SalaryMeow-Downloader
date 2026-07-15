#!/usr/bin/env bash
set -euo pipefail

download_dir="${DOUYIN_DOWNLOADS_DIR:-/var/lib/douyin-downloader/downloads}"
max_age_minutes="${DOUYIN_CLEANUP_MAX_AGE_MINUTES:-15}"

if [[ "$download_dir" != /* || "$download_dir" == "/" || ! "$max_age_minutes" =~ ^[0-9]+$ ]]; then
  echo "Refusing unsafe cleanup configuration" >&2
  exit 2
fi

mkdir -p -- "$download_dir"
deleted=$(find "$download_dir" -xdev -type f -mmin "+$max_age_minutes" -print -delete | wc -l)
echo "Removed $deleted stale download file(s) from $download_dir"
