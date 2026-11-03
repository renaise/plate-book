# Sources

## Collection images (CC0)

The four files `examples/images/met_0*.png` are byte-identical copies of the inputs of the author's Capamari entry.
They are public-domain (CC0 1.0) objects released by The Metropolitan Museum of Art under its Open Access policy.
Each object was checked on 2026-11-02 (ET) with the Met Collection API (`/public/collection/v1/objects/<id>`
returned `isPublicDomain: true`). Originals were downloaded from the `primaryImage` URL, converted to RGB,
downscaled with Lanczos to a longest side of at most 1536 px and saved as PNG (no metadata kept).
`met_04_toy.png` is cropped above the museum's label at layout time (`crop` in `examples/book.json`); the file is not edited.

CC0 terms: https://creativecommons.org/publicdomain/zero/1.0/ ; Met Open Access policy:
https://www.metmuseum.org/policies/image-resources

| File | Object | Met object page | Original image | Original SHA-1 | License |
|---|---|---|---|---|---|
| `examples/images/met_01_hippo.png` (1151x1536, from 2899x3870 JPEG) | Hippopotamus ("William"), ca. 1961–1878 B.C.. Egypt, Middle Kingdom. Acc. no. 17.9.1 | https://www.metmuseum.org/art/collection/search/544227 | https://images.metmuseum.org/CRDImages/eg/original/DP248993.jpg | `a53d057d6842838f61be07139232e5c4adb25b8c` | CC0 1.0 (Met Open Access, `isPublicDomain: true` via the Met Collection API) |
| `examples/images/met_02_netsuke.png` (1536x1024, from 4000x2667 JPEG) | Netsuke, 18th century. Japan. Acc. no. 10.211.2273 | https://www.metmuseum.org/art/collection/search/59356 | https://images.metmuseum.org/CRDImages/as/original/LC-10_211_2273_001.jpg | `a5ea2f69ab42f61c4dad1c50d9eee08049cdb67a` | CC0 1.0 (Met Open Access, `isPublicDomain: true` via the Met Collection API) |
| `examples/images/met_03_watch.png` (1428x1536, from 3530x3797 JPEG) | Watch, ca. 1630–40. Johann Possdorfer. Acc. no. 17.190.1525 | https://www.metmuseum.org/art/collection/search/194118 | https://images.metmuseum.org/CRDImages/es/original/DP169988.jpg | `3bdc3a1571b2fec61bfcc24ec94513d155df123f` | CC0 1.0 (Met Open Access, `isPublicDomain: true` via the Met Collection API) |
| `examples/images/met_04_toy.png` (1344x1536, from 1736x1984 JPEG) | Toy, 19th century. China. Acc. no. 67.179.18a, b | https://www.metmuseum.org/art/collection/search/51363 | https://images.metmuseum.org/CRDImages/as/original/DP14311.jpg | `9d3ed27f1a31b0b6f7ab12d0e483e602084b12d7` | CC0 1.0 (Met Open Access, `isPublicDomain: true` via the Met Collection API) |

## Generated images (AI-generated)

Raw outputs of `workflows/plate-book.json`, saved unchanged from Comfy Cloud; each PNG still embeds the ComfyUI graph
and prompt that made it. Models: `qwen_image_edit_2511_fp8mixed`, `qwen_2.5_vl_7b_fp8_scaled`, `qwen_image_vae`,
Lightning 4-step LoRA on (4 steps, CFG 1, euler / simple), all Apache-2.0. Seed `20261103` for every plate.

| File | Made from | Run (ET) |
|---|---|---|
| `examples/outputs/run2/00_cover.png` | `met_01_hippo.png` | run 2, 2026-11-03 |
| `examples/outputs/run2/01_plate.png` | `met_01_hippo.png` | run 2, 2026-11-03 |
| `examples/outputs/run2/02_plate.png` | `met_02_netsuke.png` | run 2, 2026-11-03 |
| `examples/outputs/run2/03_plate.png` | `met_03_watch.png` | run 2, 2026-11-03 |
| `examples/outputs/run2/04_group.png` | run 2 plates 01, 02, 03 | run 2, 2026-11-03 |
| `examples/outputs/run1_rejected/03_plate.png` | `met_03_watch.png` + run 1 cover as image 2 (earlier graph); rejected, hippo copied in | run 1, 2026-11-03 |
| `examples/outputs/run1_rejected/04_group.png` | run 1 plates 01, 02, 03 (earlier graph); rejected, built on the bad plate 03 | run 1, 2026-11-03 |

`met_04_toy.png` was not used in either run (the workflow takes three objects); it appears only in the book's
collection chapter.
