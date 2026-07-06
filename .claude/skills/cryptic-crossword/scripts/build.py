#!/usr/bin/env python3
"""
Build the interactive crossword HTML from a puzzle JSON + the bundled template.

The JSON carries everything data-specific; the template carries all the UI (grid
rendering, keyboard handling, mobile clue strip, progressive hints, check/reveal).
Keeping them separate means each puzzle is just data — no need to regenerate ~750
lines of HTML by hand.

It also validates the puzzle before writing: the black pattern and solution must
agree, every entry must have a clue whose enumeration matches its length, and every
clue must map to an entry. This catches a misread grid or a wrong-length answer early
— exactly the class of bug that corrupts an interlocking solve.

Spoiler safety: this script never prints answer letters or hint text. It only reports
structure (sizes, counts, "N/N crossings consistent"). Validation errors reference
entries by number/length, never by their letters.

Usage:
  python build.py --puzzle puzzle.json --out /path/to/index.html
"""
import sys, json, argparse, os, hashlib

PLACE = {
    "__TITLE__": None, "__N__": None, "__BLACK__": None,
    "__SOLUTION__": None, "__ACROSS__": None, "__DOWN__": None, "__HINTS__": None,
    "__SAVEKEY__": None,
}


def save_key(p):
    # Unique per puzzle so each crossword gets its own localStorage bucket (no
    # answers bleeding between puzzles), yet deterministic — a rebuild of the same
    # puzzle keeps the same key, so in-progress answers survive.
    h = hashlib.sha1(json.dumps(
        [p.get('title', ''), p['black'], p['solution']],
        ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:10]
    return 'cryptic-' + h


def blk(black, r, c, n):
    return r < 0 or c < 0 or r >= n or c >= n or black[r][c] == '#'


def entries(black, n):
    """Return (across, down) dicts: number -> length, plus a numbering grid."""
    num = [[0] * n for _ in range(n)]
    k = 0
    across, down = {}, {}
    for r in range(n):
        for c in range(n):
            if blk(black, r, c, n):
                continue
            sa = blk(black, r, c - 1, n) and not blk(black, r, c + 1, n)
            sd = blk(black, r - 1, c, n) and not blk(black, r + 1, c, n)
            if sa or sd:
                k += 1
                num[r][c] = k
                if sa:
                    l = 0
                    cc = c
                    while not blk(black, r, cc, n):
                        l += 1
                        cc += 1
                    across[k] = l
                if sd:
                    l = 0
                    rr = r
                    while not blk(black, rr, c, n):
                        l += 1
                        rr += 1
                    down[k] = l
    return across, down, num


def enum_len(enu):
    # sum every digit-group in the enumeration: "(4,6)"->10, "(3,2,3)"->8, "(10)"->10
    return sum(int(g) for g in ''.join(ch if ch.isdigit() else ' ' for ch in enu).split())


def validate(p):
    n = p['n']
    black, solution = p['black'], p['solution']
    errs = []
    if len(black) != n or any(len(r) != n for r in black):
        errs.append(f"black grid is not {n}x{n}")
    if len(solution) != n or any(len(r) != n for r in solution):
        errs.append(f"solution grid is not {n}x{n}")
    if errs:
        return errs, 0
    # black cells must line up; white cells must be A-Z
    for r in range(n):
        for c in range(n):
            sb = solution[r][c] == '#'
            if sb != (black[r][c] == '#'):
                errs.append(f"black/white mismatch at row {r+1} col {c+1}")
            elif not sb and not solution[r][c].isalpha():
                errs.append(f"non-letter in solution at row {r+1} col {c+1}")
    across, down, _ = entries(black, n)
    ac = {int(k): v for k, v in p['across'].items()}
    dn = {int(k): v for k, v in p['down'].items()}
    checked = 0
    for label, ent, clues in (('across', across, ac), ('down', down, dn)):
        for num_, length in ent.items():
            if num_ not in clues:
                errs.append(f"{num_} {label}: entry has no clue")
            else:
                el = enum_len(clues[num_][1])
                if el != length:
                    errs.append(f"{num_} {label}: grid length {length} != enumeration {clues[num_][1]}")
                else:
                    checked += 1
        for num_ in clues:
            if num_ not in ent:
                errs.append(f"{num_} {label}: clue has no matching entry in the grid")
    return errs, checked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--puzzle', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--template', default=os.path.join(
        os.path.dirname(__file__), '..', 'assets', 'template.html'))
    args = ap.parse_args()

    p = json.load(open(args.puzzle))
    errs, checked = validate(p)
    if errs:
        print("VALIDATION FAILED (no HTML written):", file=sys.stderr)
        for e in errs:
            print("  - " + e, file=sys.stderr)
        sys.exit(1)

    tpl = open(args.template).read()
    subs = {
        "__TITLE__": p.get('title', 'Cryptic Crossword'),
        "__N__": str(p['n']),
        "__BLACK__": json.dumps(p['black'], ensure_ascii=False),
        "__SOLUTION__": json.dumps(p['solution'], ensure_ascii=False),
        "__ACROSS__": json.dumps(p['across'], ensure_ascii=False),
        "__DOWN__": json.dumps(p['down'], ensure_ascii=False),
        "__HINTS__": json.dumps(p.get('hints', {"across": {}, "down": {}}), ensure_ascii=False),
        "__SAVEKEY__": save_key(p),
    }
    for k, v in subs.items():
        tpl = tpl.replace(k, v)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(tpl)

    # spoiler-free summary only
    print(f"Built {p['n']}x{p['n']} crossword -> {args.out}")
    print(f"{len(p['across'])} across, {len(p['down'])} down; {checked} entries with matching enumerations.")


if __name__ == '__main__':
    main()
