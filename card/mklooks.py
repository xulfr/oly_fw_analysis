#!/usr/bin/env python3
"""Make C:\\OM5MOD\\LOOKS.BIN for Caduceus for OM-5 from a JSON list of films (docs/FORMATS.md).

    python3 card/mklooks.py films.json LOOKS.BIN

films.json: [{"name": "Portra 400", "hue": [12 x -7..7], "light": [12 x -7..7], "sat": [12 x -5..5],
              "wb": [A/B, G/M] or null, "contrast": -2..2, "sharpness": -2..2, "shading": -5..5,
              "shadows": -7..7, "midtones": -7..7, "highlights": -7..7}, ...]   (1 to 10 films)
Slices run clockwise from Yellow, as on the camera's colour wheel. LookLab writes the same bytes."""
import json, struct, sys, zlib

MAGIC, VERSION, MAX, REC, NAME = b'OM5F', 1, 10, 64, 16


def record(f):
    def arr(key, lo):
        v = f.get(key, [0] * 12)
        if len(v) != 12 or any(not lo <= x <= -lo for x in v):
            raise ValueError(f'{f.get("name")}: {key} needs 12 values {lo}..{-lo}')
        return v
    def one(key, lo):
        x = f.get(key, 0)
        if not lo <= x <= -lo:
            raise ValueError(f'{f.get("name")}: {key} {x} outside {lo}..{-lo}')
        return x
    r = bytearray(REC)
    r[0:36] = struct.pack('36b', *arr('hue', -7), *arr('light', -7), *arr('sat', -5))
    wb = f.get('wb')
    if wb:
        if len(wb) != 2 or any(not -7 <= x <= 7 for x in wb):
            raise ValueError(f'{f.get("name")}: wb needs [A/B, G/M], each -7..7')
        r[36:39] = struct.pack('3b', 1, *wb)
    r[41:47] = struct.pack('6b', one('contrast', -2), one('sharpness', -2), one('shading', -5),
                           one('shadows', -7), one('midtones', -7), one('highlights', -7))
    name = f.get('name', '').encode('ascii')
    if not 0 < len(name) <= 12 or any(not 32 <= c < 127 for c in name):
        raise ValueError(f'{f.get("name")!r}: a name is 1 to 12 plain characters')
    return bytes(r) + name.ljust(NAME, b'\0')


def looks_bin(films):
    if not 1 <= len(films) <= MAX:
        raise ValueError(f'1 to {MAX} films')
    body = struct.pack('<HH16x', VERSION, len(films)) + b''.join(record(f) for f in films)
    total = 12 + len(body)
    return MAGIC + struct.pack('<II', total, zlib.crc32(body)) + body


if __name__ == '__main__':
    data = looks_bin(json.load(open(sys.argv[1])))
    open(sys.argv[2], 'wb').write(data)
    print(f'{sys.argv[2]}: {len(data)} bytes')
