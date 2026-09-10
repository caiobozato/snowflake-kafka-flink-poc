#!/bin/sh
# Render the diagram outputs from the SVG sources.
#
#   docs/pipeline.png   static, 2x, for slides and documents
#   docs/pipeline.gif   animated, for anywhere that will not play SVG
#
# Needs rsvg-convert on the host (brew install librsvg). GIF assembly runs in a
# container so nothing has to be installed locally.
set -e
cd "$(dirname "$0")"

python3 generate_diagram.py

echo "rendering pipeline.png"
rsvg-convert -w 3200 pipeline.svg -o pipeline.png

echo "rendering GIF frames"
rm -rf frames/png && mkdir -p frames/png
for f in frames/frame_*.svg; do
  rsvg-convert -w 1200 "$f" -o "frames/png/$(basename "$f" .svg).png"
done

echo "assembling pipeline.gif"
docker run --rm -v "$PWD:/work" -w /work python:3.12-slim sh -c '
  pip install --quiet --no-cache-dir Pillow >/dev/null &&
  python - <<PY
from pathlib import Path
from PIL import Image

paths = sorted(Path("frames/png").glob("frame_*.png"))
frames = [Image.open(p).convert("RGB") for p in paths]
# A shared adaptive palette keeps the flat brand colours from dithering.
palette = frames[0].quantize(colors=64, method=Image.MEDIANCUT)
frames = [f.quantize(palette=palette) for f in frames]
frames[0].save(
    "pipeline.gif", save_all=True, append_images=frames[1:],
    duration=70, loop=0, optimize=True, disposal=2,
)
print(f"pipeline.gif: {len(frames)} frames")
PY
'

rm -rf frames/png
ls -lh pipeline.png pipeline.gif
