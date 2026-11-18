"""Provide script-free navigation for the archived book template."""
from html import escape
from html.parser import HTMLParser
import re


class BookMenu(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.entries = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h1" and attrs.get("id") == "title":
            self.title = attrs.get("data-id") or ""
        if tag == "a" and "menu-item" in (attrs.get("class") or "").split():
            href = attrs.get("href") or ""
            if href.startswith("/articles/") and attrs.get("id"):
                self.entries.append((attrs["id"], href))


NAV_STYLE = """<style>
#archive-menu-switch,#archive-menu-switch + label {position:fixed;bottom:.5rem;left:.5rem;z-index:1000}
#archive-menu-switch {width:1px;height:1px;clip-path:inset(50%)}
#archive-menu-switch + label {cursor:pointer;background:white;color:#222;border:1px solid;padding:.25rem .6rem}
#archive-menu-switch:focus-visible + label {outline:2px solid currentColor}
#archive-menu-switch ~ .sidebar-toggle,#archive-menu-switch ~ .off-canvas-content .book-navbar {display:none}
@media(min-width:821px){
#archive-menu-switch:checked ~ .book-sidebar {display:none!important}
html body #archive-menu-switch:checked ~ .off-canvas-content {margin-left:0!important}
}
@media(max-width:820px){
#archive-menu-switch ~ .book-sidebar {display:none!important}
#archive-menu-switch:checked ~ .book-sidebar {display:block!important;transform:none!important}
}
</style>"""


def restore_navigation(text):
    sidebar = '<div class="book-sidebar">'
    if sidebar not in text:
        return text
    menu = BookMenu()
    menu.feed(text)
    if not menu.entries:
        return text
    toggle = ('<input type="checkbox" id="archive-menu-switch">'
              '<label for="archive-menu-switch">切换目录</label>')
    text = text.replace(sidebar, NAV_STYLE + toggle + sidebar, 1)
    for index, (name, _) in enumerate(menu.entries):
        if menu.title and name in {menu.title, menu.title + ".md", menu.title + ".html"}:
            for slot, position, label in (("prePage", index - 1, "上一页"),
                                          ("nextPage", index + 1, "下一页")):
                if 0 <= position < len(menu.entries):
                    href = escape(menu.entries[position][1], quote=True)
                    text = re.sub(r'(<div id="' + slot + r'"[^>]*>)\s*(</div>)',
                                  lambda m: f'{m[1]}<a href="{href}">{label}</a>{m[2]}',
                                  text, count=1)
            break
    return text
