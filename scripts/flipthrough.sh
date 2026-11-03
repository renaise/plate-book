#!/usr/bin/env bash
# Copyright 2026 Renaise Kim
# SPDX-License-Identifier: Apache-2.0
# Optional: encode the spreads made by make_book.py into a flip-through MP4 (ffmpeg, no AI).
# Usage: scripts/flipthrough.sh examples/outputs   (writes <dir>/book_flipthrough.mp4)
set -euo pipefail
dir="${1:-out}"
hold=3.5   # seconds per spread, fade included
fade=0.5
mapfile -t files < <(ls "$dir"/spreads/spread_*.png | sort)
n=${#files[@]}
inputs=(); filters=""
for i in "${!files[@]}"; do
  inputs+=(-loop 1 -t "$hold" -framerate 30 -i "${files[$i]}")
  filters+="[$i:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xE8E8E5,setsar=1,format=yuv420p[v$i];"
done
prev="v0"
for ((i = 1; i < n; i++)); do
  off=$(awk -v i="$i" -v h="$hold" -v f="$fade" 'BEGIN{printf "%.3f", i*(h-f)}')
  filters+="[$prev][v$i]xfade=transition=fade:duration=$fade:offset=$off[x$i];"
  prev="x$i"
done
ffmpeg -y -loglevel error "${inputs[@]}" -filter_complex "${filters%;}" -map "[$prev]" \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -preset slow -movflags +faststart -map_metadata -1 \
  "$dir/book_flipthrough.mp4"
echo "$n spreads -> $dir/book_flipthrough.mp4"
