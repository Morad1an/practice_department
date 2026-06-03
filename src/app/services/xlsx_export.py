from __future__ import annotations

from io import BytesIO
from string import ascii_uppercase
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def _column_letter(index: int) -> str:
    if index < 1:
        raise ValueError("index must be positive")

    result = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result.append(ascii_uppercase[remainder])
    return "".join(reversed(result))


def _inline_string_cell(reference: str, value: object) -> str:
    text = "" if value is None else str(value)
    escaped = escape(text)
    return (
        f'<c r="{reference}" s="1" t="inlineStr">'
        f'<is><t xml:space="preserve">{escaped}</t></is>'
        f"</c>"
    )


def _header_cell(reference: str, value: object) -> str:
    text = "" if value is None else str(value)
    escaped = escape(text)
    return (
        f'<c r="{reference}" s="2" t="inlineStr">'
        f'<is><t xml:space="preserve">{escaped}</t></is>'
        f"</c>"
    )


def _display_length(value: object) -> int:
    if value is None:
        return 0
    lines = str(value).splitlines() or [""]
    return max(len(line) for line in lines)


def _build_column_widths(headers: list[str], rows: list[list[object]]) -> list[float]:
    widths: list[float] = []
    columns_count = len(headers)
    for column_index in range(columns_count):
        max_length = _display_length(headers[column_index])
        for row in rows:
            if column_index >= len(row):
                continue
            max_length = max(max_length, _display_length(row[column_index]))

        widths.append(min(max(max_length + 2, 10), 80))
    return widths


def build_xlsx_bytes(
    *,
    sheet_name: str,
    headers: list[str],
    rows: list[list[object]],
) -> bytes:
    sheet_rows: list[str] = []
    header_row: list[object] = list(headers)
    all_rows: list[list[object]] = [header_row, *rows]
    column_widths = _build_column_widths(headers, rows)

    for row_index, row_values in enumerate(all_rows, start=1):
        cells: list[str] = []
        for column_index, value in enumerate(row_values, start=1):
            reference = f"{_column_letter(column_index)}{row_index}"
            if row_index == 1:
                cells.append(_header_cell(reference, value))
            else:
                cells.append(_inline_string_cell(reference, value))
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    last_column = _column_letter(len(headers)) if headers else "A"
    last_row = max(len(all_rows), 1)
    dimension = f"A1:{last_column}{last_row}"
    escaped_sheet_name = escape(sheet_name)
    columns_xml = "".join(
        (f'<col min="{index}" max="{index}" width="{width}" ' 'bestFit="1" customWidth="1"/>')
        for index, width in enumerate(column_widths, start=1)
    )

    worksheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{columns_xml}</cols>"
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escaped_sheet_name}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )

    with BytesIO() as buffer:
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '<Override PartName="/xl/styles.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                "</Types>",
            )
            archive.writestr(
                "_rels/.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/workbook.xml"/>'
                "</Relationships>",
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                'Target="worksheets/sheet1.xml"/>'
                '<Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
                'Target="styles.xml"/>'
                "</Relationships>",
            )
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr(
                "xl/styles.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<fonts count="2">'
                '<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
                '<font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
                "</fonts>"
                '<fills count="2">'
                '<fill><patternFill patternType="none"/></fill>'
                '<fill><patternFill patternType="gray125"/></fill>'
                "</fills>"
                '<borders count="1">'
                "<border><left/><right/><top/><bottom/><diagonal/></border>"
                "</borders>"
                '<cellStyleXfs count="1">'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
                "</cellStyleXfs>"
                '<cellXfs count="3">'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
                '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
                '<alignment wrapText="1" vertical="top"/>'
                "</xf>"
                '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
                '<alignment wrapText="1" vertical="top"/>'
                "</xf>"
                "</cellXfs>"
                '<cellStyles count="1">'
                '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
                "</cellStyles>"
                "</styleSheet>",
            )
            archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)
        return buffer.getvalue()
