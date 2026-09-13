"""Deterministic, local text extraction for an already validated resume upload.

This module deliberately has no database, storage, HTTP, OCR, or network concerns.
It extracts only text that exists in PDF/DOCX documents and maps explicit section
headings to the evidence vocabulary.  Callers decide how to persist its output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Final, Literal
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAX_PDF_PAGES: Final = 100
MAX_EXTRACTED_TEXT_CHARS: Final = 262_144
MAX_DOCX_DOCUMENT_XML_BYTES: Final = 5 * 1024 * 1024

EvidenceCategory = Literal["EDUCATION", "EXPERIENCE", "PROJECTS", "SKILLS", "OTHER"]


class ResumeParserError(Exception):
    """A controlled error while extracting a local resume document."""


class ResumeDocumentMalformed(ResumeParserError):
    """The selected document cannot be safely parsed as its stated format."""


class ResumeNoTextAvailable(ResumeParserError):
    """A syntactically valid document contains no extractable text (for example, a scan)."""


class ResumeParseLimitExceeded(ResumeParserError):
    """Extraction exceeded a fixed, deterministic safety bound."""


@dataclass(frozen=True)
class ParsedEvidence:
    """A source-order evidence candidate, before persistence or skill matching."""

    ordinal: int
    category: EvidenceCategory
    section_header: str | None
    bullet_text: str
    source_page: int | None = None


@dataclass(frozen=True)
class ParsedResume:
    """The normalized source text and evidence candidates derived from it."""

    raw_text: str
    evidence: tuple[ParsedEvidence, ...]


# Exact normalized headings keep classification intentionally conservative.  A
# resume that does not use one of these headings still has safe OTHER evidence.
_SECTION_HEADERS: Final[dict[str, EvidenceCategory]] = {
    "education": "EDUCATION",
    "education and training": "EDUCATION",
    "academic background": "EDUCATION",
    "experience": "EXPERIENCE",
    "work experience": "EXPERIENCE",
    "professional experience": "EXPERIENCE",
    "employment history": "EXPERIENCE",
    "work history": "EXPERIENCE",
    "projects": "PROJECTS",
    "project experience": "PROJECTS",
    "selected projects": "PROJECTS",
    "technical projects": "PROJECTS",
    "skills": "SKILLS",
    "technical skills": "SKILLS",
    "core skills": "SKILLS",
    "core competencies": "SKILLS",
}
_HORIZONTAL_SPACE = re.compile(r"[\t\f\v ]+")
_SPACE_AROUND_NEWLINE = re.compile(r" *\n *")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_HEADING_PUNCTUATION = re.compile(r"[\s:|\-–—]+$")
_BULLET_PREFIX = re.compile(r"^(?:[•*▪◦\-–—]+|\d+[.)])\s*")


def normalize_extracted_text(text: str) -> str:
    """Apply traceable, non-semantic cleanup to extractor output.

    Line endings and horizontal whitespace are regularized, non-printing control
    characters are removed, and redundant empty lines at boundaries are trimmed.
    Words, punctuation, and line ordering are otherwise retained.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(
        character for character in text if character in {"\n", "\t"} or ord(character) >= 32
    )
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = _SPACE_AROUND_NEWLINE.sub("\n", text)
    return _EXCESS_BLANK_LINES.sub("\n\n", text).strip()


class ResumeParser:
    """Extract PDF/DOCX text locally and derive conservative evidence candidates."""

    @classmethod
    def parse(cls, content: bytes, file_format: str) -> ParsedResume:
        if not isinstance(content, bytes) or not content:
            raise ResumeDocumentMalformed("The document has no readable bytes")
        if file_format == "PDF":
            pages = cls._extract_pdf_pages(content)
        elif file_format == "DOCX":
            pages = (cls._extract_docx_text(content),)
        else:
            raise ResumeDocumentMalformed("Unsupported resume document format")

        normalized_pages = tuple(normalize_extracted_text(page) for page in pages)
        raw_text = normalize_extracted_text("\n\n".join(page for page in normalized_pages if page))
        if not raw_text:
            raise ResumeNoTextAvailable("No machine-readable text was found in this document")
        if len(raw_text) > MAX_EXTRACTED_TEXT_CHARS:
            raise ResumeParseLimitExceeded("Extracted text exceeds the supported limit")
        return ParsedResume(raw_text=raw_text, evidence=cls._derive_evidence(normalized_pages))

    @staticmethod
    def _extract_pdf_pages(content: bytes) -> tuple[str, ...]:
        try:
            # pypdf is intentionally a local parser; importing here keeps DOCX-only
            # operations usable if an installation is accidentally incomplete.
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content), strict=True)
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ResumeParseLimitExceeded("PDF has more pages than the supported limit")
            pages: list[str] = []
            extracted_characters = 0
            for page in reader.pages:
                page_text = page.extract_text(extraction_mode="plain") or ""
                extracted_characters += len(page_text)
                if extracted_characters > MAX_EXTRACTED_TEXT_CHARS:
                    raise ResumeParseLimitExceeded("Extracted text exceeds the supported limit")
                pages.append(page_text)
            return tuple(pages)
        except ResumeParserError:
            raise
        except ImportError as error:
            raise ResumeDocumentMalformed("PDF extraction support is unavailable") from error
        except Exception as error:
            raise ResumeDocumentMalformed("The PDF could not be parsed safely") from error

    @staticmethod
    def _extract_docx_text(content: bytes) -> str:
        try:
            with ZipFile(BytesIO(content)) as archive:
                try:
                    info = archive.getinfo("word/document.xml")
                except KeyError as error:
                    raise ResumeDocumentMalformed("The DOCX document XML is missing") from error
                if info.file_size > MAX_DOCX_DOCUMENT_XML_BYTES:
                    raise ResumeParseLimitExceeded("DOCX document text exceeds the supported limit")
                xml_bytes = archive.read(info)
        except ResumeParserError:
            raise
        except (BadZipFile, OSError, ValueError) as error:
            raise ResumeDocumentMalformed("The DOCX could not be parsed safely") from error

        try:
            root = ElementTree.fromstring(xml_bytes)
        except ElementTree.ParseError as error:
            raise ResumeDocumentMalformed("The DOCX document XML is malformed") from error

        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs: list[str] = []
        for paragraph in root.iter(f"{namespace}p"):
            fragments: list[str] = []
            for node in paragraph.iter():
                if node.tag == f"{namespace}t":
                    fragments.append(node.text or "")
                elif node.tag == f"{namespace}tab":
                    fragments.append("\t")
                elif node.tag in {f"{namespace}br", f"{namespace}cr"}:
                    fragments.append("\n")
            paragraph_text = "".join(fragments)
            if paragraph_text:
                paragraphs.append(paragraph_text)
        return "\n".join(paragraphs)

    @classmethod
    def _derive_evidence(cls, pages: tuple[str, ...]) -> tuple[ParsedEvidence, ...]:
        candidates: list[ParsedEvidence] = []
        category: EvidenceCategory = "OTHER"
        section_header: str | None = None
        ordinal = 0
        for page_index, page in enumerate(pages, start=1):
            if not page:
                continue
            for line in page.splitlines():
                candidate_text = normalize_extracted_text(line)
                if not candidate_text:
                    continue
                heading_category = cls._heading_category(candidate_text)
                if heading_category is not None:
                    category = heading_category
                    section_header = candidate_text
                    continue
                bullet_text = _BULLET_PREFIX.sub("", candidate_text).strip()
                if not bullet_text:
                    continue
                candidates.append(
                    ParsedEvidence(
                        ordinal=ordinal,
                        category=category,
                        section_header=section_header,
                        bullet_text=bullet_text,
                        source_page=page_index if len(pages) > 1 else None,
                    )
                )
                ordinal += 1
        return tuple(candidates)

    @staticmethod
    def _heading_category(text: str) -> EvidenceCategory | None:
        if len(text) > 80:
            return None
        normalized = _HEADING_PUNCTUATION.sub("", text.casefold())
        return _SECTION_HEADERS.get(normalized)
