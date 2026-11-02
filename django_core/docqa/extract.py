"""Text extraction for uploads: .txt, .md and .docx (zip + XML; no new dependency). Bounded in size and refuses XML entities."""
import io
import re
import zipfile

MAX_BYTES, MAX_TEXT = 1_000_000, 200_000
MAX_UNCOMPRESSED, MAX_MEMBERS = 10_000_000, 100


class ExtractError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def extract_text(filename, data):
    name = (filename or '').lower()
    if len(data) > MAX_BYTES:
        raise ExtractError('file_too_large')
    if name.endswith(('.txt', '.md')):
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise ExtractError('not_utf8') from None
    elif name.endswith('.docx'):
        text = _docx(data)
    else:
        raise ExtractError('unsupported_type')
    text = re.sub(r'[ \t]+', ' ', text.replace('\r', '')).strip()
    if not text:
        raise ExtractError('empty')
    if len(text) > MAX_TEXT:
        raise ExtractError('too_long')
    return text


def _docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED:
                raise ExtractError('file_too_large')
            xml = z.read('word/document.xml')
    except (zipfile.BadZipFile, KeyError):
        raise ExtractError('not_docx') from None
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ExtractError('not_docx')
    from xml.etree import ElementTree as ET     # entities refused above
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise ExtractError('not_docx') from None
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs = []
    for p in root.iter(ns + 'p'):
        paragraphs.append(''.join(t.text or '' for t in p.iter(ns + 't')))
    return '\n\n'.join(paragraphs)
