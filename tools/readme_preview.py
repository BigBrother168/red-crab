"""readme_preview.py: the top of README.md and README.en.md (down to the first ---) as tools/t/media/preview_zh.html and
preview_en.html, looking roughly as GitHub shows it, the pictures from docs/media.  Standard library only; it knows only
what that part of the README uses: headings, paragraphs, lists, **bold**, [links](...), `code` and raw HTML lines."""
import html, io, os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "t", "media")
CSS = """body{margin:0;background:#f6f8fa;font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;color:#1f2328;line-height:1.6}
.page{max-width:1012px;margin:24px auto;background:#fff;border:1px solid #d1d9e0;border-radius:6px;padding:32px 40px}
.bar{max-width:1012px;margin:16px auto 0;font-size:14px;color:#59636e}
h1{font-size:2em;border-bottom:1px solid #d1d9e0;padding-bottom:.3em} h2{font-size:1.5em;border-bottom:1px solid #d1d9e0;padding-bottom:.3em;margin-top:32px}
h3{font-size:1.25em;margin-top:28px} img{max-width:100%} table{border-collapse:collapse} td{border:1px solid #d1d9e0;padding:6px 13px;vertical-align:top}
a{color:#0969da;text-decoration:none} code{background:#eff1f3;padding:.2em .4em;border-radius:6px;font-size:85%}
div[align=center]{text-align:center} div[align=center] h1{border:none}"""


def inline(t):
    t = html.escape(t, quote=False)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', t)


def raw(line):                       # an HTML line: its tags as they are, markdown links inside (the <sub> line)
    parts = re.split(r"(<[^>]+>)", line)
    return "".join(p if p.startswith("<") else re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', p) for p in parts)


def page(md, title, note):
    top = md[:md.index("\n---\n")]
    top = top.replace('src="docs/media/', 'src="file:///' + os.path.join(ROOT, "docs", "media").replace("\\", "/") + "/")
    out, para, items = [], [], []

    def flush():
        if para:
            out.append("<p>" + "\n".join(inline(p) if not p.startswith("<") else raw(p) for p in para) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join("<li>%s</li>" % inline(i) for i in items) + "</ul>")
            items.clear()
    for line in top.split("\n"):
        if not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            n = len(line) - len(line.lstrip("#"))
            out.append("<h%d>%s</h%d>" % (n, inline(line[n:].strip()), n))
        elif line.startswith("- "):
            items.append(line[2:])
        elif line.startswith("<") and not line.startswith(("<sub", "<img")):
            flush()
            out.append(line)
        else:
            para.append(line.replace("<br>", "\x00"))
    flush()
    body = "\n".join(out).replace("\x00", "<br>").replace("&lt;br&gt;", "<br>")
    return ("<!doctype html><meta charset=utf-8><title>%s</title><style>\n%s\n</style><div class=bar>%s</div><div class=page>%s</div>"
            % (title, CSS, note, body))


for name, lang, title, note in (("README.md", "zh", "红螃蟹", "README.md 预览（模仿 GitHub 的样子，只是近似）"),
                                ("README.en.md", "en", "Red Crab", "README.en.md preview (roughly as GitHub shows it)")):
    md = io.open(os.path.join(ROOT, name), encoding="utf-8").read()
    path = os.path.join(OUT, "preview_%s.html" % lang)
    io.open(path, "w", encoding="utf-8").write(page(md, title, note))
    print("wrote", path)
