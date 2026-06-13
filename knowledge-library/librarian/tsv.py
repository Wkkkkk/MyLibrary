import os


def read_rows(path, expected_header):
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].strip():
        raise ValueError(f"{path}: file is empty")
    header = lines[0].split("\t")
    if header != expected_header:
        if len(header) != len(expected_header):
            raise ValueError(
                f"{path}: header has {len(header)} cols, want {len(expected_header)}"
            )
        for i, (got, want) in enumerate(zip(header, expected_header)):
            if got != want:
                raise ValueError(
                    f"{path}: header column {i} is {got!r}, want {want!r}"
                )
    rows = []
    for i, line in enumerate(lines[1:], start=2):
        fields = line.split("\t")
        if len(fields) != len(expected_header):
            raise ValueError(
                f"{path} line {i}: {len(fields)} cols, want {len(expected_header)}"
            )
        rows.append(fields)
    return header, rows


def write_rows(path, header, rows):
    for r in rows:
        if len(r) != len(header):
            raise ValueError(f"{path}: row width {len(r)} != header {len(header)}: {r[:2]}")
        for f in r:
            if "\t" in f or "\n" in f or "\r" in f:
                raise ValueError(f"{path}: tab/newline/carriage-return inside field: {f[:50]!r}")
    out = ["\t".join(header)] + ["\t".join(r) for r in rows]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def split_multi(s):
    out = []
    for v in s.split(";"):
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def join_multi(vals):
    out = []
    for v in vals:
        if ";" in v:
            raise ValueError(f"value contains ';': {v!r}")
        if v and v not in out:
            out.append(v)
    return "; ".join(out)
