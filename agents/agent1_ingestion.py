import re
from pathlib import Path


class DataIngestionAgent:
    """
    Reads PDF, HTML, DOCX, or TXT files and returns clean text + structure.
    Falls back to OCR if a PDF has no extractable text layer.
    """

    SUPPORTED = {".pdf", ".html", ".htm", ".docx", ".txt"}

    def run(self, input_path: str) -> dict:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported file type '{suffix}'. Supported: {self.SUPPORTED}")

        parsers = {
            ".pdf":  self._parse_pdf,
            ".html": self._parse_html,
            ".htm":  self._parse_html,
            ".docx": self._parse_docx,
            ".txt":  self._parse_txt,
        }

        raw = parsers[suffix](path)
        raw["text"] = self._clean_text(raw["text"])
        return raw

    # ------------------------------------------------------------------ parsers

    def _parse_pdf(self, path: Path) -> dict:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        pages = [page.get_text() for page in doc]
        text = "\n".join(pages)

        if len(text.strip()) < 100:
            print("  [!] PDF appears scanned — running OCR...")
            text = self._ocr_pdf(path)

        return {"text": text, **self._extract_structure(text)}

    def _parse_html(self, path: Path) -> dict:
        from bs4 import BeautifulSoup
        with open(path, encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
        return {"text": text, **self._extract_structure(text)}

    def _parse_docx(self, path: Path) -> dict:
        from docx import Document
        doc = Document(str(path))
        text = "\n".join(p.text for p in doc.paragraphs)
        return {"text": text, **self._extract_structure(text)}

    def _parse_txt(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        return {"text": text, **self._extract_structure(text)}

    # ------------------------------------------------------------------ OCR

    def _ocr_pdf(self, path: Path) -> str:
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(str(path))
        return "\n".join(pytesseract.image_to_string(img) for img in images)

    # ------------------------------------------------------------------ helpers

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\n{3,}", "\n\n", text)   # collapse blank lines
        text = re.sub(r"[ \t]{2,}", " ", text)    # collapse inline spaces
        text = re.sub(r"-\n(\w)", r"\1", text)    # rejoin hyphenated line breaks
        return text.strip()

    def _extract_structure(self, text: str) -> dict:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        title = lines[0] if lines else ""

        sections, references = [], []
        in_refs = False

        for line in lines[1:]:
            low = line.lower()
            if low in ("references", "bibliography", "works cited"):
                in_refs = True
                continue
            if in_refs:
                references.append(line)
            elif self._is_section_header(line):
                sections.append(line)

        return {"title": title, "sections": sections, "references": references}

    @staticmethod
    def _is_section_header(line: str) -> bool:
        if len(line) > 80:
            return False
        if re.match(r"^\d+[\.\)]\s+\w", line):   # "1. Introduction"
            return True
        if line.isupper() and len(line) > 3:       # "INTRODUCTION"
            return True
        return False
