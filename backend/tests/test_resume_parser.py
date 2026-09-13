"""Pure deterministic parser coverage; no database or API integration here."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.parsers.resume import (
    ParsedEvidence,
    ResumeDocumentMalformed,
    ResumeNoTextAvailable,
    ResumeParser,
    normalize_extracted_text,
)


def _pdf_with_text(*lines: str) -> bytes:
    """Build a minimal one-page PDF with literal strings for pypdf extraction."""

    escaped_lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    commands = ["BT /F1 12 Tf 72 720 Td"]
    for index, line in enumerate(escaped_lines):
        if index:
            commands.append("0 -18 Td")
        commands.append(f"({line}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 3 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, payload in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{number} 0 obj\n".encode())
        output.write(payload)
        output.write(b"\nendobj\n")
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode())
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return output.getvalue()


def _docx(*paragraphs: str) -> bytes:
    document = "".join(
        f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs
    )
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{document}</w:body></w:document>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", xml)
    return output.getvalue()


def _docx_with_document_xml(document_xml: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def test_pdf_extraction_is_deterministic_and_classifies_explicit_headings():
    pytest.importorskip("pypdf")
    content = _pdf_with_text("Education", "- BSc Computer Science", "Technical Skills", "Python, Docker")

    first = ResumeParser.parse(content, "PDF")
    second = ResumeParser.parse(content, "PDF")

    assert first == second
    assert first.raw_text == "Education\n- BSc Computer Science\nTechnical Skills\nPython, Docker"
    assert first.evidence == (
        ParsedEvidence(0, "EDUCATION", "Education", "BSc Computer Science"),
        ParsedEvidence(1, "SKILLS", "Technical Skills", "Python, Docker"),
    )


def test_docx_extracts_visible_text_in_document_order_and_maps_sections():
    parsed = ResumeParser.parse(
        _docx("Professional Experience", "• Built APIs", "Projects", "Resume parser"), "DOCX"
    )

    assert parsed.raw_text == "Professional Experience\n• Built APIs\nProjects\nResume parser"
    assert [(item.ordinal, item.category, item.section_header, item.bullet_text) for item in parsed.evidence] == [
        (0, "EXPERIENCE", "Professional Experience", "Built APIs"),
        (1, "PROJECTS", "Projects", "Resume parser"),
    ]


def test_unknown_content_is_safe_other_evidence_with_stable_ordinal():
    parsed = ResumeParser.parse(_docx("Summary", "Reliable engineering work"), "DOCX")

    assert [(item.ordinal, item.category, item.section_header, item.bullet_text) for item in parsed.evidence] == [
        (0, "OTHER", None, "Summary"),
        (1, "OTHER", None, "Reliable engineering work"),
    ]


def test_normalization_only_removes_control_noise_and_redundant_spacing():
    assert normalize_extracted_text("  Alpha\r\nBeta\t\tGamma\x00\r\r\rDelta  ") == "Alpha\nBeta Gamma\n\nDelta"


def test_no_text_pdf_has_a_controlled_result():
    pytest.importorskip("pypdf")
    with pytest.raises(ResumeNoTextAvailable):
        ResumeParser.parse(_pdf_with_text(), "PDF")


@pytest.mark.parametrize(
    ("content", "file_format"),
    [
        (b"not a PDF", "PDF"),
        (b"not a zip", "DOCX"),
        (_docx_with_document_xml(b"<not valid xml"), "DOCX"),
        (_docx("text"), "TXT"),
    ],
)
def test_malformed_or_unsupported_documents_raise_controlled_parser_errors(content, file_format):
    with pytest.raises(ResumeDocumentMalformed):
        ResumeParser.parse(content, file_format)
