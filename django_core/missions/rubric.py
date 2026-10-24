"""Read the rubric levels (score 1-5 per indicator) from the owner's local observation guide (.docx). The text is stored in
``RubricLevel`` rows of the database only; it is never written to a tracked file. stdlib only."""
import re
import zipfile
from xml.etree import ElementTree

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def _text(el):
    return ''.join(t.text or '' for t in el.iter(f'{W}t')).strip()


def parse_rubric_docx(path):
    """Return ``{indicator_code: {score: text}}``. An indicator is a numbered heading paragraph ("۱. ...") followed by a
    table whose rows are (score, criterion). Raises ValueError unless exactly 12 indicators with levels 1-5 are found."""
    with zipfile.ZipFile(path) as z:
        body = ElementTree.fromstring(z.read('word/document.xml')).find(f'{W}body')
    result, heading = {}, None
    for el in body:
        if el.tag == f'{W}p':
            m = re.match(r'^\s*(\d{1,2})\s*[.\-)]\s*\S', _text(el).translate(_DIGITS))
            heading = int(m.group(1)) if m else heading
        elif el.tag == f'{W}tbl' and heading is not None:
            levels = {}
            for tr in el.iter(f'{W}tr'):
                cells = [_text(tc) for tc in tr.findall(f'{W}tc')]
                if len(cells) >= 2 and cells[0].translate(_DIGITS) in set('12345') and cells[1]:
                    levels[int(cells[0].translate(_DIGITS))] = cells[1]
            if levels:
                result[heading] = levels
            heading = None
    if sorted(result) != list(range(1, 13)) or any(sorted(v) != [1, 2, 3, 4, 5] for v in result.values()):
        raise ValueError('expected 12 indicators with levels 1-5')
    return result
