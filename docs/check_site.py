"""Validate a locally built TARS manual; never deploy or contact external services.

Run after mkdocs build --strict: python docs/check_site.py /path/to/site
Requires the same MkDocs environment as the documentation build.
"""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

from mkdocs.config import load_config
from mkdocs.structure.files import get_files

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ['Getting Started', 'Configuration', 'Using TARS', 'Official TARS Plugins',
          'Troubleshooting', 'Development and Releases', 'Credits and Attribution']


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.text = set(), [], []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append(attrs[key])

    def handle_data(self, data):
        self.text.append(data)


def check(site):
    config = load_config(str(ROOT / 'mkdocs.yml'))
    assert [next(iter(item)) for item in config.nav] == GROUPS
    assert all(len(next(iter(item.values()))) <= 4 for item in config.nav)
    nav = {path for group in config.nav for item in next(iter(group.values())) for path in item.values()}
    files = [file for file in get_files(config) if file.inclusion.is_included()]
    assert {file.src_uri for file in files} == nav, 'Built source differs from public navigation'
    expected = {file.dest_uri for file in files}
    actual = {str(path.relative_to(site)) for path in site.rglob('*.html')}
    assert actual == expected | {'404.html'}, f'Unexpected/missing public pages: {actual ^ (expected | {"404.html"})}'
    assert not any((site / name).exists() for name in ('archive', 'advanced', 'screen',
                   'troubleshooting.html', 'troubleshooting.yaml', 'data-policy.html', 'overrides',
                   'EDAII-Bindings.zip', 'documentation-inventory.csv', 'check_site.py'))
    parsed = {path.resolve(): Page(path.read_text()) for path in site.rglob('*.html')}
    links_checked, external = 0, set()
    for path, page in parsed.items():
        # 404.html is served at arbitrary URLs, so its theme links are root-relative.
        if path.name == '404.html':
            continue
        html = path.read_text()
        assert 'cloud.umami.is' not in html
        assert 'discord.gg/9c58jxVuAT' not in html
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                if url.scheme in ('http', 'https'):
                    external.add(link)
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            if target.is_dir():
                target /= 'index.html'
            assert target.is_relative_to(site.resolve()), f'Link leaves generated site: {path}: {link}'
            assert target.is_file(), f'Broken link: {path}: {link}'
            if url.fragment and target in parsed:
                assert unquote(url.fragment) in parsed[target].ids, f'Broken anchor: {path}: {link}'
            links_checked += 1
    search = json.loads((site / 'search/search_index.json').read_text())
    allowed_locations = {'' if file.url == './' else file.url for file in files}
    assert {entry['location'].split('#')[0] for entry in search['docs']} <= allowed_locations
    landing = ' '.join(parsed[(site / 'index.html').resolve()].text)
    assert 'TARS manual' in landing and 'Elite Dangerous' in landing
    license_text = ' '.join((ROOT / 'LICENSE').read_text().split())
    assert license_text in ' '.join(' '.join(parsed[(site / 'license/index.html').resolve()].text).split())
    print(f'PASS: {len(expected)} public pages; seven concise navigation groups; {links_checked} internal links/assets/anchors')
    print('PASS: excluded upstream/history/assets absent from HTML and search; full MIT notice accessible; inherited analytics absent')
    print(f'External references: {len(external)} distinct URLs (not treated as local links)')


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
