import re
import requests
from pathlib import Path


GROBID_URL = "http://localhost:8070"


class DataIngestionAgent:
    """
    Reads PDF, HTML, DOCX, or TXT files and returns clean text + structure.
    For PDFs: tries GROBID first (scientific paper parser), falls back to
    PyMuPDF + regex. Falls back to OCR if PDF has no extractable text layer.
    """

    SUPPORTED = {".pdf", ".html", ".htm", ".docx", ".txt"}

    _NOISE_PATTERNS = re.compile(
        r"^(TABLE|TA BL E|FIGURE|F IGU R E|FIG\.?|APPENDIX)\s*[\dA-Z]",
        re.IGNORECASE,
    )

    _REF_HEADINGS = re.compile(
        r"^r[\s]*e[\s]*f[\s]*e[\s]*r[\s]*e[\s]*n[\s]*c[\s]*e[\s]*s$"
        r"|^b[\s]*i[\s]*b[\s]*l[\s]*i[\s]*o[\s]*g[\s]*r[\s]*a[\s]*p[\s]*h[\s]*y$"
        r"|^works\s+cited$",
        re.IGNORECASE,
    )

    def run(self, input_path: str) -> dict:
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {input_path}")

        suffix = path.suffix.lower()
        if suffix not in self.SUPPORTED:
            raise ValueError(f"Unsupported file type '{suffix}'. Supported: {self.SUPPORTED}")

        if suffix == ".pdf":
            if self._mineru_available():
                print("  [MinerU] Parsing...")
                result = self._parse_pdf_mineru(path)
                if result:
                    result["text"] = self._clean_text(result["text"])
                    result["parser"] = "mineru"
                    return result
                print("  [MinerU] Failed — falling back to GROBID/PyMuPDF")

            if self._grobid_available():
                print("  [GROBID] Parsing with GROBID...")
                result = self._parse_pdf_grobid(path)
                if result:
                    result["text"] = self._clean_text(result["text"])
                    result["parser"] = "grobid"
                    return result
                print("  [GROBID] Failed — falling back to PyMuPDF")

        parsers = {
            ".pdf":  self._parse_pdf_pymupdf,
            ".html": self._parse_html,
            ".htm":  self._parse_html,
            ".docx": self._parse_docx,
            ".txt":  self._parse_txt,
        }

        raw = parsers[suffix](path)
        raw["text"] = self._clean_text(raw["text"])
        raw["parser"] = "pymupdf-enhanced"
        return raw

    # ------------------------------------------------------------------ MinerU

    def _mineru_available(self) -> bool:
        import shutil
        return bool(shutil.which("mineru") or Path("/opt/anaconda3/bin/mineru").exists())

    def _parse_pdf_mineru(self, path: Path) -> dict | None:
        import subprocess, tempfile, shutil as sh

        mineru_bin = sh.which("mineru") or "/opt/anaconda3/bin/mineru"
        if not Path(mineru_bin).exists():
            return None

        tmp_dir = Path(tempfile.mkdtemp(prefix="mineru_kg_"))
        try:
            proc = subprocess.run(
                [mineru_bin, "-p", str(path), "-o", str(tmp_dir),
                 "-m", "txt", "-b", "pipeline", "-l", "en"],
                capture_output=True, text=True, timeout=180,
            )
            if proc.returncode != 0:
                print(f"  [MinerU] Error (rc={proc.returncode}): {proc.stderr[:300]}")
                return None

            md_files = list(tmp_dir.rglob("*.md"))
            if not md_files:
                print("  [MinerU] No .md output found")
                return None

            md_text = md_files[0].read_text(encoding="utf-8")
            return self._parse_mineru_md(md_text)
        except subprocess.TimeoutExpired:
            print("  [MinerU] Timeout after 180s")
            return None
        except Exception as e:
            print(f"  [MinerU] Exception: {e}")
            return None
        finally:
            sh.rmtree(tmp_dir, ignore_errors=True)

    def _parse_mineru_md(self, md: str) -> dict:
        """
        Parses MinerU markdown output. Handles two common structures:
          A) # Title heading  →  Author1 | Author2  →  ## Abstract
          B) ## Please cite this article as:  →  plain-text title  →  ## Abstract
        """
        lines = md.splitlines()

        title = ""
        abstract_parts = []
        keywords = ""
        sections = []
        references = []
        authors = []

        in_abstract = False
        collect_kw_next = False
        in_refs = False
        found_title = False
        after_cite_heading = False
        after_running_head = False   # True when # heading was "Running head: ..."
        in_body = False              # True after first real body section heading
        pre_body_paras = []          # long paragraphs before first body section (Frontiers format)

        for line in lines:
            s = line.strip()
            if not s or re.match(r'^!\[', s):
                continue

            # Any heading
            if re.match(r'^#{1,6} ', line):
                heading = re.sub(r'^#+\s*', '', s).strip()
                norm = re.sub(r'\s+', ' ', heading).lower()
                norm_nospace = norm.replace(' ', '')

                # Abstract heading variants:
                #   "Abstract", "Resumen" (Spanish), "A B S T R A C T" (Elsevier spaced)
                in_abstract = (norm == 'abstract'
                               or norm.rstrip(':') in ('resumen', 'résumé', 'zusammenfassung')
                               or norm_nospace == 'abstract')
                in_refs = norm in ('references', 'bibliography', 'works cited')
                collect_kw_next = 'keyword' in norm or 'palabras clave' in norm
                after_cite_heading = 'cite this article' in norm or 'please cite' in norm

                if not in_abstract and not in_refs and not collect_kw_next:
                    sections.append(heading)

                # First real body section → stop collecting pre-body paragraphs
                body_section = re.match(
                    r'^(introduction|background|method|result|discussion|conclusion|study\s*\d)',
                    norm, re.IGNORECASE)
                if body_section:
                    in_body = True

                # Pattern A: level-1 heading is the title
                if re.match(r'^# (?!#)', line) and not found_title:
                    if re.match(r'running head\s*:', heading, re.IGNORECASE):
                        # Word manuscript artifact — skip, take next plain text line
                        after_running_head = True
                    else:
                        title = heading
                        found_title = True
                continue

            # Pattern A2: first plain-text line after "Running head:" level-1 heading
            if after_running_head and not found_title:
                if len(s.split()) >= 5:
                    title = s
                    found_title = True
                after_running_head = False
                continue

            # Pattern B: first plain-text line after "Please cite..." heading is the title
            if after_cite_heading and not found_title:
                if len(s.split()) >= 4:
                    title = s
                    found_title = True
                after_cite_heading = False
                continue

            # Keywords: next line after keyword heading
            if collect_kw_next:
                keywords = s
                collect_kw_next = False
                continue

            # Inline "Keywords: ..." / "Palabras clave: ..." text
            kw_m = re.match(r'^(?:keywords?|palabras\s+clave)\s*[:\.]?\s*(.+)', s, re.IGNORECASE)
            if kw_m and not keywords:
                keywords = kw_m.group(1).strip()
                continue

            if in_abstract:
                abstract_parts.append(s)
            elif not in_body and not in_refs:
                # Track the last long paragraph before first body section (Frontiers format).
                # Skip: citation lines, numbered affiliation lists, short metadata lines.
                _is_citation = re.match(r'^Citation\s*:', s, re.IGNORECASE)
                _is_affil = re.match(r'^\d[\s\w]{0,3}[A-Z]', s) and len(s.split()) < 60
                if not _is_citation and not _is_affil and len(s.split()) >= 20:
                    pre_body_paras.append(s)
            if in_refs:
                references.append(s)

        # Fallback C: no level-1 title found → use first ## heading with ≥5 words
        if not found_title:
            for s in sections:
                if len(s.split()) >= 5:
                    title = s
                    break

        # Fallback D: Frontiers format — abstract is the LAST long paragraph before the
        # first body section heading, with no "Abstract" heading (Krug 2021, Mascarenhas 2018).
        if not abstract_parts and pre_body_paras:
            abstract_parts = [pre_body_paras[-1]]

        # Authors: pipe-separated line within first 30 non-empty non-heading lines
        plain_lines = [l.strip() for l in lines
                       if l.strip() and not re.match(r'^#', l) and not re.match(r'^!\[', l.strip())]
        for text_line in plain_lines[:30]:
            if '|' in text_line and len(text_line) < 400:
                parts = [p.strip() for p in text_line.split('|') if p.strip()]
                if parts and all(2 < len(p) < 60 and not re.search(r'https?://', p) for p in parts):
                    authors = parts
                    break

        # DOI: search only in first 50 lines to avoid picking up reference DOIs
        doi = ""
        header_text = "\n".join(lines[:50])
        doi_m = re.search(r'10\.\d{4,}/[^\s,)]+', header_text)
        if doi_m:
            doi = doi_m.group(0).rstrip('.')

        return {
            "title": title,
            "abstract": " ".join(abstract_parts),
            "authors": authors,
            "keywords": keywords,
            "doi": doi,
            "sections": sections,
            "references": references,
            "text": md,
            "word_count": len(md.split()),
        }

    # ------------------------------------------------------------------ GROBID

    def _grobid_available(self) -> bool:
        try:
            r = requests.get(f"{GROBID_URL}/api/isalive", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _parse_pdf_grobid(self, path: Path) -> dict | None:
        try:
            with open(path, "rb") as f:
                response = requests.post(
                    f"{GROBID_URL}/api/processFulltextDocument",
                    files={"input": f},
                    data={"consolidateHeader": "1", "consolidateCitations": "0"},
                    timeout=60,
                )
            if response.status_code != 200:
                return None

            return self._parse_grobid_xml(response.text)
        except Exception as e:
            print(f"  [GROBID] Error: {e}")
            return None

    def _parse_grobid_xml(self, xml_text: str) -> dict:
        from xml.etree import ElementTree as ET

        ns = {
            "tei": "http://www.tei-c.org/ns/1.0",
            "xml": "http://www.w3.org/XML/1998/namespace",
        }
        root = ET.fromstring(xml_text)

        # Title
        title_el = root.find(".//tei:titleStmt/tei:title[@type='main']", ns)
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        # Abstract
        abstract_el = root.find(".//tei:abstract", ns)
        abstract = "".join(abstract_el.itertext()).strip() if abstract_el is not None else ""

        # Authors
        authors = []
        for author in root.findall(".//tei:fileDesc//tei:author", ns):
            forename = author.find(".//tei:forename", ns)
            surname = author.find(".//tei:surname", ns)
            name_parts = []
            if forename is not None and forename.text:
                name_parts.append(forename.text.strip())
            if surname is not None and surname.text:
                name_parts.append(surname.text.strip())
            if name_parts:
                authors.append(" ".join(name_parts))

        # Sections
        sections = []
        body_text_parts = []
        for div in root.findall(".//tei:body//tei:div", ns):
            head = div.find("tei:head", ns)
            if head is not None and head.text:
                sections.append(head.text.strip())
            for p in div.findall(".//tei:p", ns):
                body_text_parts.append("".join(p.itertext()))

        # References
        references = []
        for ref in root.findall(".//tei:listBibl/tei:biblStruct", ns):
            parts = []
            # Authors
            ref_authors = []
            for author in ref.findall(".//tei:author", ns):
                surname = author.find(".//tei:surname", ns)
                forename = author.find(".//tei:forename", ns)
                name = ""
                if surname is not None and surname.text:
                    name = surname.text.strip()
                if forename is not None and forename.text:
                    name += f", {forename.text.strip()}"
                if name:
                    ref_authors.append(name)
            if ref_authors:
                parts.append("; ".join(ref_authors))
            # Year
            date = ref.find(".//tei:date[@type='published']", ns)
            if date is not None and date.get("when"):
                parts.append(f"({date.get('when')[:4]})")
            # Title
            ref_title = ref.find(".//tei:title[@level='a']", ns)
            if ref_title is None:
                ref_title = ref.find(".//tei:title", ns)
            if ref_title is not None and ref_title.text:
                parts.append(ref_title.text.strip())
            # Journal
            journal = ref.find(".//tei:title[@level='j']", ns)
            if journal is not None and journal.text:
                parts.append(f"[{journal.text.strip()}]")
            if parts:
                references.append(" ".join(parts))

        full_text = abstract + "\n\n" + "\n\n".join(body_text_parts)

        return {
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "sections": sections,
            "references": references,
            "text": full_text,
        }

    # ------------------------------------------------------------------ PyMuPDF (enhanced)

    def _parse_pdf_pymupdf(self, path: Path) -> dict:
        import fitz
        doc = fitz.open(str(path))

        # --- raw text for OCR fallback check ---
        raw_text = "\n".join(page.get_text() for page in doc)
        if len(raw_text.strip()) < 100:
            print("  [!] PDF appears scanned — running OCR...")
            raw_text = self._ocr_pdf(path)
            return {"text": raw_text, "title": "", "abstract": "",
                    "authors": [], "keywords": "", "sections": [],
                    "references": [], "toc": [], "doi": "", "parser": "pymupdf"}

        # --- metadata ---
        meta = doc.metadata or {}
        title = meta.get("title", "").strip()
        doi = ""

        # --- TOC (built-in outline) ---
        toc = doc.get_toc()  # [[level, title, page], ...]
        toc_sections = [{"level": lvl, "title": t, "page": pg} for lvl, t, pg in toc]

        # --- font-size based extraction across all pages ---
        spans_by_page = []
        for page in doc:
            page_spans = []
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    for span in line["spans"]:
                        page_spans.append({
                            "text": span["text"].strip(),
                            "size": round(span["size"], 1),
                            "bold": bool(span["flags"] & 2**4),
                            "bbox": span["bbox"],
                        })
            spans_by_page.append(page_spans)

        all_spans = [s for page in spans_by_page for s in page if s["text"]]

        # Determine dominant body font size (most common size)
        from collections import Counter
        size_counts = Counter(s["size"] for s in all_spans)
        body_size = size_counts.most_common(1)[0][0]

        # Detect repository/preprint cover page (e.g. ISCTE-IUL, arXiv) → skip to next page
        _repo_markers = re.compile(
            r'deposited in|citation for published item|peer.?review status'
            r'|repositório|preprint server|accepted version|this is the peer reviewed',
            re.IGNORECASE,
        )
        title_page_idx = 0
        if spans_by_page:
            page0_text = " ".join(s["text"] for s in spans_by_page[0])
            if _repo_markers.search(page0_text) and len(spans_by_page) > 1:
                title_page_idx = 1

        title_page_spans = spans_by_page[title_page_idx] if spans_by_page else []

        # Title: largest bold text on title page, or metadata
        if not title or len(title) < 10:
            bold_large = [s for s in title_page_spans if s["bold"] and s["size"] > body_size + 4]
            if bold_large:
                max_size = max(s["size"] for s in bold_large)
                title_parts = [s["text"] for s in bold_large if s["size"] == max_size and s["text"]]
                title = " ".join(title_parts).strip()

            # Fallback: same-size bold text (title bold but not larger than body)
            if (not title or len(title) < 10):
                for s in title_page_spans:
                    if s["bold"] and len(s["text"].split()) >= 4:
                        title = s["text"].strip()
                        break

        # Authors: bold text on title page slightly larger than body, smaller than title
        title_size = max((s["size"] for s in title_page_spans if s["bold"]), default=body_size + 6)
        authors = []
        seen_authors = set()
        for s in title_page_spans:
            if (s["bold"] and body_size < s["size"] < title_size - 2
                    and len(s["text"]) > 3
                    and not re.search(r"\d|doi|http|@", s["text"], re.IGNORECASE)):
                name = re.sub(r"[\|\s]+$", "", s["text"]).strip()
                if name and name not in seen_authors:
                    seen_authors.add(name)
                    authors.append(name)

        # Abstract: text block following "Abstract" label on title page
        abstract = ""
        abstract_label_found = False
        abstract_parts = []
        for s in title_page_spans:
            if re.match(r"^abstract$", s["text"], re.IGNORECASE):
                abstract_label_found = True
                continue
            if abstract_label_found:
                if s["size"] < body_size - 1 or re.match(r"^keywords?", s["text"], re.IGNORECASE):
                    break
                abstract_parts.append(s["text"])
        abstract = " ".join(abstract_parts).strip()

        # Keywords: span following "Keywords" label
        keywords = ""
        for i, s in enumerate(title_page_spans):
            if re.match(r"^k[\sE]*e[\sY]*y[\sW]*o[\sR]*d[\sS]*s?$", s["text"], re.IGNORECASE):
                kw_parts = []
                for ks in title_page_spans[i+1:i+5]:
                    if ks["size"] < body_size - 3:
                        kw_parts.append(ks["text"])
                    else:
                        break
                keywords = " ".join(kw_parts).strip()
                break

        # DOI: find in title page spans first, then page 0 as fallback
        for s in title_page_spans + (spans_by_page[0] if title_page_idx > 0 else []):
            doi_match = re.search(r"10\.\d{4,}/\S+", s["text"])
            if doi_match:
                doi = doi_match.group(0).rstrip(".")
                break

        # References: use TOC page to find start, collect from there
        ref_start_page = None
        for lvl, t, pg in toc:
            if re.search(r"reference|bibliography", t, re.IGNORECASE):
                ref_start_page = pg - 1  # 0-indexed
                break

        references = []
        if ref_start_page is not None:
            ref_text = "\n".join(
                page.get_text() for page in doc
                if page.number >= ref_start_page
            )
            for line in ref_text.splitlines():
                line = line.strip()
                if line and not re.match(r"^(references|bibliography)$", line, re.IGNORECASE):
                    references.append(line)

        # Full clean text
        full_text = self._clean_text(raw_text)

        # Sections from TOC (clean, structured)
        sections = [item["title"] for item in toc_sections if item["level"] >= 2]

        return {
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "keywords": keywords,
            "doi": doi,
            "toc": toc_sections,
            "sections": sections,
            "references": references,
            "text": full_text,
        }

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

    # ------------------------------------------------------------------ regex helpers

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\b([A-Z])(?: ([A-Z])){2,}\b", lambda m: m.group(0).replace(" ", ""), text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"-\n(\w)", r"\1", text)
        return text.strip()

    def _extract_structure(self, text: str, pdf_doc=None) -> dict:
        title = self._extract_title(text, pdf_doc)
        sections, references = self._extract_sections_and_refs(text)
        return {
            "title": title,
            "abstract": "",
            "authors": [],
            "sections": sections,
            "references": references,
        }

    def _extract_title(self, text: str, pdf_doc=None) -> str:
        if pdf_doc is not None:
            meta_title = pdf_doc.metadata.get("title", "").strip()
            if meta_title and len(meta_title) > 10:
                return meta_title

        lines = [l.strip() for l in text.splitlines() if l.strip()]
        skip_patterns = re.compile(
            r"doi:|http|www\.|©|\d{4};\d|received:|accepted:|correspondence|email:",
            re.IGNORECASE,
        )
        for line in lines[:50]:
            if skip_patterns.search(line):
                continue
            words = line.split()
            if 4 <= len(words) <= 25 and not self._NOISE_PATTERNS.match(line):
                return line

        return lines[0] if lines else ""

    def _extract_sections_and_refs(self, text: str):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        sections, references = [], []
        in_refs = False
        seen_sections = set()

        for line in lines:
            if self._REF_HEADINGS.match(re.sub(r"\s+", " ", line).strip()):
                in_refs = True
                continue

            if in_refs:
                references.append(line)
            elif self._is_section_header(line):
                key = line.upper()
                if key not in seen_sections:
                    seen_sections.add(key)
                    sections.append(line)

        return sections, references

    def _is_section_header(self, line: str) -> bool:
        if len(line) > 80:
            return False
        if self._NOISE_PATTERNS.match(line):
            return False
        if re.match(r"^\d+[\.\)]\s+[A-Z]\w+", line):
            return True
        if re.match(r"^[A-Z][A-Z\s]{3,49}$", line) and not re.search(r"\d", line):
            return True
        return False
