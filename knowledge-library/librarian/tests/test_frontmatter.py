from librarian import frontmatter

ART = """---
title: X
category: "旧类"
tags: [zhihu, 旧类]
---

# X
body
"""

def row(rel="文学/a.md"):
    return [rel, "X", "旧类", "文学", "文学评论; 思想史", "C++; tip of week",
            "文学评论", "一句话。", "high", "false", "", "", "h" * 16, "v1", "d"]

def test_apply_and_idempotent(tmp_path):
    p = tmp_path / "a.md"
    p.write_text(ART, encoding="utf-8")
    assert frontmatter.apply(p, row()) == "written"
    text = p.read_text(encoding="utf-8")
    assert 'primary_category: "文学"' in text
    assert 'topics: "文学评论; 思想史"' in text
    assert '  - Cpp' in text and '  - tip-of-week' in text
    assert 'category: "旧类"' in text          # untouched
    assert "zhihu" not in text                 # import tags replaced
    assert frontmatter.apply(p, row()) == "unchanged"

def test_no_frontmatter(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("just body", encoding="utf-8")
    assert frontmatter.apply(p, row()) == "no-frontmatter"


def test_multiline_title_with_dashes_not_split(tmp_path):
    # Some Zhihu titles were imported as multi-line quoted scalars whose
    # continuation line starts with dashes (e.g. "------大总结"). The closing
    # fence must be a line that is exactly '---', not any '\n---', or the
    # frontmatter gets split mid-title and the import metadata below it
    # (author/url/interaction_time) is orphaned into the body.
    art = (
        '---\n'
        'title: ""Deep Learning"\n'
        '------大总结"\n'
        'author: "计算机视觉研究院"\n'
        'interaction_time: "2016-10-27T00:27:54.282000+00:00"\n'
        '---\n\n# body\n'
    )
    p = tmp_path / "a.md"
    p.write_text(art, encoding="utf-8")
    assert frontmatter.apply(p, row()) == "written"
    text = p.read_text(encoding="utf-8")
    fm, body = text[4:].split("\n---\n", 1)      # split on the real closing fence
    assert "author:" in fm                       # import meta stayed in frontmatter
    assert "interaction_time:" in fm
    assert "------大总结" in fm                    # multi-line title preserved
    assert 'primary_category: "文学"' in fm       # labels appended into frontmatter
    assert body.strip() == "# body"              # body untouched, not split into it
