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
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)      # C0 controls (a NUL breaks PostgreSQL text columns)
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
    # ASCII/UTF-8 only (a UTF-16 document would hide a DTD from the byte search below), no NUL, and a DTD is an error in the parser itself
    if b'\x00' in xml or xml[:2] in (b'\xff\xfe', b'\xfe\xff') or not xml.lstrip(b'\xef\xbb\xbf \r\n\t').startswith((b'<?xml', b'<w:')):
        raise ExtractError('not_docx')
    if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        raise ExtractError('not_docx')
    from xml.etree import ElementTree as ET
    from xml.parsers import expat

    def forbid_dtd(*_args):
        raise expat.ExpatError('dtd')
    checker = expat.ParserCreate()             # a DTD or entity declaration, in ANY encoding, is an error in the parser itself
    checker.StartDoctypeDeclHandler = forbid_dtd
    checker.EntityDeclHandler = forbid_dtd
    try:
        checker.Parse(xml, True)
        root = ET.fromstring(xml)
    except (expat.ExpatError, ET.ParseError):
        raise ExtractError('not_docx') from None
    ns = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs = []
    for p in root.iter(ns + 'p'):
        paragraphs.append(''.join(t.text or '' for t in p.iter(ns + 't')))
    return '\n\n'.join(paragraphs)
