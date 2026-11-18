"""Tests for folder_symbols/appinfo.py: the welcome page texts, the About data and the page choice."""
import dataclasses
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

import pytest

import folder_symbols
from folder_symbols.appinfo import (APP_NAME, EMPTY_PAGE, MAIN_PAGE, WELCOME, YARU_ARTWORK, about_info,
                                    page_for, warn)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------- welcome page
def test_welcome_texts_exact():
    assert WELCOME.icon_name == "folder-symbolic"
    assert WELCOME.title == "Choose a folder"
    assert WELCOME.description == "In Files, right-click a folder and choose “Choose Icon…”."


def test_welcome_uses_typographic_quotes_and_ellipsis():
    assert '"' not in WELCOME.description and "..." not in WELCOME.description


# ------------------------------------------------------------- About
def test_about_version_is_package_version():
    assert about_info().version == folder_symbols.__version__


def test_about_fields_not_empty():
    info = about_info()
    for field in dataclasses.fields(info):
        assert getattr(info, field.name), field.name
    for section in info.legal_sections:
        for field in dataclasses.fields(section):
            assert getattr(section, field.name).strip(), field.name


def test_about_fixed_fields():
    info = about_info()
    assert info.application_name == APP_NAME == "Folder Symbols"
    assert info.developer_name == "Vladyslav Chernyshov"
    assert info.license == "MIT"
    assert info.application_icon == "folder-symbolic"


@pytest.mark.parametrize("name", ["website", "issue_url"])
def test_about_urls_well_formed(name):
    url = urlparse(getattr(about_info(), name))
    assert url.scheme == "https" and url.netloc == "github.com"
    assert url.path.startswith("/VladyslavChernyshov/folder-symbols")
    assert not url.query and not url.fragment and " " not in url.geturl()


def test_about_issue_url_is_the_repository_tracker():
    info = about_info()
    assert info.issue_url == info.website + "/issues"


def test_about_copyright_matches_license_file():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as f:
        line = next(l for l in f if l.startswith("Copyright (c) "))
    assert about_info().copyright == "© " + line[len("Copyright (c) "):].strip()


def _notice_text():
    """NOTICE.md as plain text: markdown bold and code marks removed, whitespace collapsed."""
    with open(os.path.join(ROOT, "NOTICE.md"), encoding="utf-8") as f:
        text = f.read()
    return " ".join(text.replace("**", "").replace("`", "").split())


def test_yaru_legal_section_is_copied_from_notice():
    """Every owner line and sentence of the legal section is in NOTICE.md as written there."""
    notice = _notice_text()
    assert YARU_ARTWORK.copyright in notice
    visible = re.sub(r"<[^>]+>", "", YARU_ARTWORK.text)          # the text the dialog shows
    sentences = re.split(r"(?<=[.)])\s+(?=[A-Z])", visible.replace("\n", " "))
    assert len(sentences) >= 3
    for sentence in sentences:
        assert " ".join(sentence.split()) in notice, sentence


def test_yaru_legal_section_names_the_licence():
    assert "Creative Commons Attribution-ShareAlike 4.0" in YARU_ARTWORK.text
    assert "https://creativecommons.org/licenses/by-sa/4.0/" in YARU_ARTWORK.text


def test_yaru_legal_section_is_valid_markup():
    """The dialog shows the text as Pango markup: the only tags are links, and the text has no stray & or <."""
    tags = re.findall(r"<[^>]+>", YARU_ARTWORK.text)
    assert tags and all(re.fullmatch(r'<a href="https://[^"<>&]+">|</a>', t) for t in tags)
    assert "&" not in YARU_ARTWORK.text
    for text in (YARU_ARTWORK.copyright, about_info().comments, about_info().copyright):
        assert not set("<>&") & set(text)


# ------------------------------------------------------------- page choice
@pytest.mark.parametrize("dirs, current, page", [
    ([], None, EMPTY_PAGE),
    ([], EMPTY_PAGE, EMPTY_PAGE),
    (["/a"], None, MAIN_PAGE),
    (["/a", "/b"], None, MAIN_PAGE),
    (["/a"], EMPTY_PAGE, MAIN_PAGE),          # a second launch with folders while the welcome page is open
    (["/a"], MAIN_PAGE, MAIN_PAGE),
    ([], MAIN_PAGE, MAIN_PAGE),               # no way back to the welcome page
])
def test_page_for(dirs, current, page):
    assert page_for(dirs, current) == page


def test_page_names_differ():
    assert EMPTY_PAGE != MAIN_PAGE


# ------------------------------------------------------------- warnings on stderr
def test_warn_prints_one_prefixed_line(capsys):
    warn("x")
    warn(OSError("disk full"))
    assert capsys.readouterr() == ("", "folder-symbols: x\nfolder-symbols: disk full\n")


def test_appinfo_module_does_not_import_gi():
    code = "import sys, folder_symbols.appinfo; print('gi' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
