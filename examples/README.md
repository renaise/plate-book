# Example outputs

## Plates (Comfy Cloud)

`outputs/run2/` holds the five raw PNGs from one run of `workflows/plate-book.json` on Comfy Cloud on 2026-11-03 (ET):
Qwen-Image-Edit-2511 fp8mixed, Lightning 4-step LoRA on, seed `20261103`, inputs `images/met_01_hippo.png`,
`met_02_netsuke.png`, `met_03_watch.png`. Not edited; each PNG embeds its graph. `04_group.png` has faint white specks
in the lower black ground; they are in the raw output.

`outputs/run1_rejected/` holds two plates from the earlier run 1, kept only as a record: with the cover fed in as
image 2, plate 03 came back as the hippo instead of the watch, and the group plate was built on that bad plate.

`outputs/graph_screenshot.png`: the graph on Comfy Cloud after run 1 (browser tab bar cropped off); its previews are run 1 results.

## Video (Comfy Cloud)

`outputs/plate_book_slide.mp4`: raw output of `workflows/plate-book-video.json` (LTX-2.3 image-to-video with audio) on
Comfy Cloud, 2026-11-03 (ET), first frame `outputs/run2/04_group.png` (as `plate_group.png`), seed `20261103`, 8.04 s,
704x960, 25 fps. Unedited; embeds its graph. The first ~4.5 s hold; after ~5 s a duplicate hippo appears on the right.

`outputs/plate_book_slide_trim.mp4`: the first 4.5 s of that file, AI-generated, cut and re-encoded with
`ffmpeg -i plate_book_slide.mp4 -t 4.5 -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -c:a aac -b:a 128k -movflags +faststart -map_metadata -1 plate_book_slide_trim.mp4`.
An earlier dolly attempt (it morphed the watch) was deleted.

## Book (local, no AI)

Made on 2026-11-03 (ET) by `scripts/make_book.py` from `examples/book.json`, the four Met photos and the plates above,
and by `scripts/flipthrough.sh` (ffmpeg) for the video:

```bash
python scripts/make_book.py --spec examples/book.json --images examples --out examples/outputs
scripts/flipthrough.sh examples/outputs
```

Re-running `make_book.py` gives byte-identical `book.pdf`, `cover.png` and spreads (checked with SHA-1).

| File | What |
|---|---|
| `outputs/book.pdf` | 23 pages, 170 × 240 mm, 300 dpi. Pages are raster images (Pillow), text set from the bundled OFL fonts |
| `outputs/cover.png` | Page 1 at 150 dpi |
| `outputs/spreads/spread_00_p01.png` … `spread_11_p22-23.png` | Each spread, 2400 px wide, on a grey presentation ground |
| `outputs/book_flipthrough.mp4` | 36.5 s, 1920 × 1080: the spreads in order with short fades (ffmpeg `xfade`). Not AI-generated itself |

The pictures inside the book: four CC0 Met photographs (not AI), the five run 2 plates and one rejected run 1 plate
(chapter 04, labelled as rejected). Every generated picture says "AI-generated" in its caption. The cover, the end
plate and the "After" picture in chapter 08 are the run 2 cover plate, gradient-mapped by the script.
