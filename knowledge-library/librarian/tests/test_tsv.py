import pytest
from librarian import tsv

def test_roundtrip(tmp_path):
    p = tmp_path / "x.tsv"
    rows = [["a/b.md", "x; y"], ["c/d.md", ""]]
    tsv.write_rows(p, ["path", "vals"], rows)
    header, got = tsv.read_rows(p, expected_header=["path", "vals"])
    assert header == ["path", "vals"] and got == rows

def test_width_enforced(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("h1\th2\nonly-one-field\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        tsv.read_rows(p, expected_header=["h1", "h2"])

def test_header_identity_checked(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("h1\toops\na\tb\n", encoding="utf-8")
    with pytest.raises(ValueError, match="oops"):
        tsv.read_rows(p, expected_header=["h1", "h2"])

def test_header_length_mismatch(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("h1\na\n", encoding="utf-8")
    with pytest.raises(ValueError):
        tsv.read_rows(p, expected_header=["h1", "h2"])

def test_crlf_read(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_bytes("h1\th2\r\na\tb\r\n".encode("utf-8"))
    header, rows = tsv.read_rows(p, expected_header=["h1", "h2"])
    assert header == ["h1", "h2"] and rows == [["a", "b"]]

def test_empty_file_raises(tmp_path):
    p = tmp_path / "x.tsv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="file is empty"):
        tsv.read_rows(p, expected_header=["h1"])
    p.write_text("\n", encoding="utf-8")
    with pytest.raises(ValueError, match="file is empty"):
        tsv.read_rows(p, expected_header=["h1"])

def test_write_rows_width_mismatch(tmp_path):
    p = tmp_path / "x.tsv"
    with pytest.raises(ValueError, match=str(p)):
        tsv.write_rows(p, ["h1", "h2"], [["only-one"]])

@pytest.mark.parametrize("bad", ["a\tb", "a\nb", "a\rb"])
def test_write_rows_rejects_control_chars(tmp_path, bad):
    p = tmp_path / "x.tsv"
    with pytest.raises(ValueError, match=str(p)):
        tsv.write_rows(p, ["h1"], [[bad]])
    assert not p.exists()

def test_write_is_atomic_no_tmp_left(tmp_path):
    p = tmp_path / "x.tsv"
    tsv.write_rows(p, ["h1"], [["a"]])
    assert p.read_text(encoding="utf-8") == "h1\na\n"
    assert list(tmp_path.iterdir()) == [p]

def test_multi():
    assert tsv.split_multi(" a;  b; a; ") == ["a", "b"]
    assert tsv.join_multi(["a", "b", "a"]) == "a; b"
    assert tsv.split_multi("") == []

def test_join_multi_rejects_semicolon():
    with pytest.raises(ValueError):
        tsv.join_multi(["a;b"])

def test_write_rows_creates_missing_parent_dir(tmp_path):
    from librarian import tsv
    target = tmp_path / "nested" / "deeper" / "out.tsv"   # parents do not exist
    tsv.write_rows(target, ["a", "b"], [["1", "2"]])
    _header, rows = tsv.read_rows(target, ["a", "b"])
    assert rows == [["1", "2"]]
