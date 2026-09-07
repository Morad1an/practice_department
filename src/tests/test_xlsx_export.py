from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from src.app.services.xlsx_export import build_xlsx_bytes


def test_xlsx_removes_xml_10_control_characters_from_all_xml_parts():
    workbook = build_xlsx_bytes(
        sheet_name='Лист\x01"',
        headers=["Заголовок\x01"],
        rows=[["Значение\x01"]],
    )

    with ZipFile(BytesIO(workbook)) as archive:
        for name in archive.namelist():
            if name.endswith(".xml") or name.endswith(".rels"):
                xml = archive.read(name)
                assert b"\x01" not in xml
                ElementTree.fromstring(xml)
