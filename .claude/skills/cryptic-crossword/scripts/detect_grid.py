#!/usr/bin/env python3
"""
Detect the black/white pattern of a crossword grid from an image.

Reading a blocked grid by eye is error-prone (it's easy to misplace a black square),
so this samples the actual pixels. Given the grid's bounding box and size it classifies
each cell as black (#) or white (.), then reports two sanity checks you should trust:
  - 180-degree rotational symmetry (nearly all published cryptics have it)
  - an ASCII rendering you can eyeball against the source image

Usage:
  python detect_grid.py IMAGE [--bbox L,T,R,B] [--size N]

If --bbox is omitted it auto-detects the largest dense square (the grid). Auto-detect
is a best guess; if the ASCII/symmetry look wrong, pass an explicit --bbox (pixel
coordinates of the grid's outer edges) and/or --size (default 15).

Prints JSON to stdout: {"n","bbox","black","symmetric"}. The black pattern is not a
spoiler, so it's safe to print; the solution is produced later and must not be.
"""
import sys, json, argparse
import numpy as np
from PIL import Image
from scipy import ndimage


def autodetect_bbox(a):
    """The grid's black squares + gridline lattice form one big connected dark region;
    clue letters are small separate blobs. So the largest connected dark component's
    bounding box is the grid."""
    dark = a < 128
    lbl, num = ndimage.label(dark)
    if num == 0:
        return 0, 0, a.shape[1], a.shape[0]
    sizes = ndimage.sum(dark, lbl, range(1, num + 1))
    biggest = int(np.argmax(sizes)) + 1
    ys, xs = np.where(lbl == biggest)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def sample(a, L, T, R, B, N):
    cw, ch = (R - L) / N, (B - T) / N
    grid = []
    for r in range(N):
        row = ''
        for c in range(N):
            cx, cy = L + (c + 0.5) * cw, T + (r + 0.5) * ch
            x0, x1 = int(cx - cw * 0.28), int(cx + cw * 0.28)
            y0, y1 = int(cy - ch * 0.28), int(cy + ch * 0.28)
            patch = a[max(0, y0):y1, max(0, x0):x1]
            row += '#' if (patch.size and patch.mean() < 128) else '.'
        grid.append(row)
    return grid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--bbox', help='L,T,R,B pixel coords of the grid outer edges')
    ap.add_argument('--size', type=int, default=15)
    args = ap.parse_args()

    a = np.array(Image.open(args.image).convert('L'))
    if args.bbox:
        L, T, R, B = (int(x) for x in args.bbox.split(','))
    else:
        L, T, R, B = autodetect_bbox(a)

    N = args.size
    grid = sample(a, L, T, R, B, N)
    symmetric = all(grid[r][c] == grid[N - 1 - r][N - 1 - c]
                    for r in range(N) for c in range(N))

    print(json.dumps({"n": N, "bbox": [L, T, R, B], "black": grid,
                      "symmetric": symmetric}))
    # human-readable rendering to stderr so it doesn't pollute the JSON on stdout
    print(f"\nDetected grid {N}x{N}  bbox={L},{T},{R},{B}  symmetric={symmetric}",
          file=sys.stderr)
    for row in grid:
        print(row, file=sys.stderr)
    if not symmetric:
        print("\nWARNING: not 180-degree symmetric — bbox/size is probably off, "
              "or this grid genuinely breaks symmetry. Verify against the image.",
              file=sys.stderr)


if __name__ == '__main__':
    main()
