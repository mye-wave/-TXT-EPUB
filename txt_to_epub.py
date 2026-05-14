#!/usr/bin/env python3
"""
Batch-convert Chinese TXT novels to EPUB.

The script intentionally uses only the Python standard library, so it can run
on a fresh Windows Python install without Calibre, ebooklib, chardet, or network
access.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import mimetypes
import re
import sys
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median


TOOL_VERSION = "1.0.0"
DEFAULT_OUTPUT_BASE = Path(r"E:\不知道")
DEFAULT_LANGUAGE = "zh-CN"
MAX_TITLE_LENGTH = 90
DEFAULT_MAX_CHARS_PER_XHTML = 240_000

COMMON_CHINESE_CHARS = set(
    "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动"
    "同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化"
    "高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外"
    "天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气"
    "第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果"
    "料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组"
    "见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门"
    "即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证"
    "改清美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完"
    "类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫"
    "且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青"
    "省列习响约支般史感劳便团往酸历市克何除消构府称太准精值号率族维划选标写存候"
    "亲毛快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局"
    "照参红细引听该铁价严龙飞"
)

CHINESE_NUMERAL = (
    r"[零〇一二三四五六七八九十百千万萬亿億两兩俩壹贰貳叁參肆伍陆陸柒捌玖拾佰仟"
    r"廿卅\d０-９]+"
)
ROMAN_NUMERAL = r"[IVXLCDMivxlcdm]+"
MIXED_NUMERAL = rf"(?:{CHINESE_NUMERAL}|{ROMAN_NUMERAL})"

CHAPTER_PATTERNS = [
    re.compile(
        rf"^(?:正文|正文卷|作品相关|VIP章节|vip章节|VIP卷|vip卷|免费章节|免费卷|公众章节|公众卷|卷首语|楔子卷)?\s*"
        rf"第\s*{MIXED_NUMERAL}\s*[章回节卷部集篇幕话話]\s*.*$"
    ),
    re.compile(rf"^(?:卷|部|篇|集)\s*{MIXED_NUMERAL}(?:\s+|[：:、.-]|\s*$).*$"),
    re.compile(r"^(?:Chapter|CHAPTER|chapter)\s+\d+[\s:：.-].*$"),
    re.compile(
        r"^(?:序|序章|楔子|引子|前言|开篇|终章|尾声|后记|外传|番外|番外篇|"
        r"番外\s*\S+|大结局|完本感言|上架感言|写在最后)(?:\s*\S.*)?$"
    ),
]
WEAK_NUMBERED_TITLE_PATTERN = re.compile(rf"^{MIXED_NUMERAL}\s*[、.．]\s*\S.*$")

TITLE_WRAPPER_RE = re.compile(r"^[\s　【\[\(（《<]+|[\s　】\]\)）》>]+$")
BODY_END_PUNCT = set("。！？!?；;")
SEPARATOR_RE = re.compile(r"^[\s　\-_=*＊·•~～—]{3,}$")
URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)
METADATA_PREFIX_RE = re.compile(
    r"^(?:书名|作品名|小说名|作者|作\s*者|作者名|简介|内容简介|文案|来源|更新时间|最后更新|字数)\s*[:：].*$"
)


@dataclass
class EncodingInfo:
    encoding: str
    strict: bool
    score: float
    replacement_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class ChapterCandidate:
    line_no: int
    title: str


@dataclass
class Chapter:
    title: str
    lines: list[str]
    source_line_no: int | None = None
    href: str | None = None


@dataclass
class ConversionResult:
    source: str
    output: str | None
    title: str
    author: str
    encoding: str
    strict_encoding: bool
    chapter_count: int
    warnings: list[str]
    status: str
    error: str | None = None


def is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return (
        0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2A700 <= code <= 0x2B73F
        or 0x2B740 <= code <= 0x2B81F
        or 0x2B820 <= code <= 0x2CEAF
        or 0x2CEB0 <= code <= 0x2EBEF
        or 0x30000 <= code <= 0x3134F
    )


def is_valid_xml_char(ch: str) -> bool:
    code = ord(ch)
    return (
        code == 0x09
        or code == 0x0A
        or code == 0x0D
        or 0x20 <= code <= 0xD7FF
        or 0xE000 <= code <= 0xFFFD
        or 0x10000 <= code <= 0x10FFFF
    )


def score_decoded_text(text: str, encoding_priority: int, replacement_count: int) -> float:
    sample = text[:200_000]
    if not sample:
        return 0.0

    control_count = 0
    cjk_count = 0
    common_count = 0
    nul_count = sample.count("\x00")
    suspicious_count = 0

    for ch in sample:
        code = ord(ch)
        if ch in "\n\r\t":
            continue
        if code < 32 or 0xD800 <= code <= 0xDFFF:
            control_count += 1
        if is_cjk_char(ch):
            cjk_count += 1
            if ch in COMMON_CHINESE_CHARS:
                common_count += 1

    for token in ("锟斤拷", "ï»¿", "�"):
        suspicious_count += sample.count(token)

    common_ratio = common_count / cjk_count if cjk_count else 0.0
    cjk_ratio = cjk_count / max(1, len(sample))

    return (
        replacement_count * 1000
        + nul_count * 80
        + control_count * 40
        + suspicious_count * 100
        + encoding_priority * 0.25
        - common_ratio * 25
        - cjk_ratio * 5
    )


def decode_txt_file(path: Path) -> tuple[str, EncodingInfo]:
    raw = path.read_bytes()
    if not raw:
        return "", EncodingInfo("utf-8", True, 0.0, 0, ["文件为空。"])

    bom_encodings = [
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe\x00\x00", "utf-32-le"),
        (b"\x00\x00\xfe\xff", "utf-32-be"),
        (b"\xff\xfe", "utf-16-le"),
        (b"\xfe\xff", "utf-16-be"),
    ]
    for bom, encoding in bom_encodings:
        if raw.startswith(bom):
            text = raw.decode(encoding, errors="strict")
            info = EncodingInfo(encoding, True, 0.0, 0)
            return clean_text(text, info)

    encodings: list[str] = ["utf-8", "gb18030", "big5", "cp950"]
    if raw.count(b"\x00") / max(1, len(raw)) > 0.02:
        encodings = ["utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le", "utf-32-be"] + encodings

    candidates: list[tuple[float, str, str, bool, int]] = []
    for priority, encoding in enumerate(dict.fromkeys(encodings)):
        try:
            text = raw.decode(encoding, errors="strict")
            replacement_count = 0
            strict = True
        except UnicodeDecodeError:
            text = raw.decode(encoding, errors="replace")
            replacement_count = text.count("\ufffd")
            strict = False

        score = score_decoded_text(text, priority, replacement_count)
        candidates.append((score, encoding, text, strict, replacement_count))

    score, encoding, text, strict, replacement_count = min(candidates, key=lambda item: item[0])
    info = EncodingInfo(encoding, strict, score, replacement_count)
    if not strict:
        info.warnings.append(
            f"无法严格识别编码，已使用 {encoding} 替换解码；替换字符数量：{replacement_count}。"
        )
    if encoding in {"big5", "cp950"}:
        info.warnings.append("检测到疑似繁体 Big5/CP950 编码；如文字不对，请手动指定 --encoding gb18030 或 utf-8。")

    return clean_text(text, info)


def clean_text(text: str, info: EncodingInfo) -> tuple[str, EncodingInfo]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\ufeff", "")
    text = text.replace("\u00a0", " ")

    removed = 0
    chars: list[str] = []
    for ch in text:
        if is_valid_xml_char(ch):
            chars.append(ch)
        else:
            removed += 1
    if removed:
        info.warnings.append(f"已移除 {removed} 个 EPUB/XML 不允许的控制字符。")

    text = "".join(chars)
    text = re.sub(r"\n{6,}", "\n\n\n", text)
    return text, info


def decode_with_forced_encoding(path: Path, encoding: str) -> tuple[str, EncodingInfo]:
    raw = path.read_bytes()
    text = raw.decode(encoding, errors="strict")
    info = EncodingInfo(encoding, True, 0.0, 0)
    return clean_text(text, info)


def normalize_title(line: str) -> str:
    title = line.strip().strip("\ufeff")
    title = TITLE_WRAPPER_RE.sub("", title)
    title = re.sub(r"\s+", " ", title)
    return title.strip()


def is_probable_chapter_title(line: str, custom_patterns: list[re.Pattern[str]], max_title_length: int) -> bool:
    title = normalize_title(line)
    if not title:
        return False
    if len(title) > max_title_length:
        return False
    if SEPARATOR_RE.match(title):
        return False
    if URL_RE.search(title):
        return False
    if title[-1] in BODY_END_PUNCT and not title.startswith(("第", "Chapter", "CHAPTER", "chapter")):
        return False

    patterns = custom_patterns + CHAPTER_PATTERNS
    return any(pattern.match(title) for pattern in patterns)


def find_chapter_candidates(
    lines: list[str],
    custom_patterns: list[re.Pattern[str]],
    max_title_length: int,
) -> list[ChapterCandidate]:
    candidates: list[ChapterCandidate] = []
    for line_no, line in enumerate(lines):
        if is_probable_chapter_title(line, custom_patterns, max_title_length):
            title = normalize_title(line)
            if candidates and line_no - candidates[-1].line_no <= 2 and title == candidates[-1].title:
                continue
            candidates.append(ChapterCandidate(line_no, title))
    return candidates


def detect_toc_ranges(lines: list[str], candidates: list[ChapterCandidate]) -> tuple[list[ChapterCandidate], list[tuple[int, int]]]:
    if len(candidates) < 4:
        return candidates, []

    ranges: list[tuple[int, int]] = []
    skip_lines: set[int] = set()
    clusters: list[list[ChapterCandidate]] = []
    current: list[ChapterCandidate] = []

    for candidate in candidates:
        current_titles = {item.title for item in current}
        if current and candidate.title in current_titles and len(current) >= 3:
            clusters.append(current)
            current = [candidate]
        elif not current or candidate.line_no - current[-1].line_no <= 3:
            current.append(candidate)
        else:
            clusters.append(current)
            current = [candidate]
    if current:
        clusters.append(current)

    total_lines = len(lines)
    front_limit = max(250, int(total_lines * 0.08))
    for cluster in clusters:
        if len(cluster) < 3 or cluster[0].line_no > front_limit:
            continue

        gaps = [cluster[i + 1].line_no - cluster[i].line_no for i in range(len(cluster) - 1)]
        if gaps and median(gaps) > 2:
            continue

        later_candidates = [item for item in candidates if item.line_no > cluster[-1].line_no]
        later_count = len(later_candidates)
        repeated_titles = sum(
            1 for item in cluster if any(later.title == item.title for later in later_candidates)
        )
        repeated_threshold = max(3, (len(cluster) * 2 + 2) // 3)
        is_repeated_toc = repeated_titles >= repeated_threshold
        is_dense_long_toc = len(cluster) >= 6 and later_count >= max(3, len(cluster) // 3)
        if not (is_repeated_toc or is_dense_long_toc):
            continue

        start = cluster[0].line_no
        for _ in range(3):
            if start <= 0:
                break
            previous = lines[start - 1].strip()
            if previous in {"目录", "正文目录", "章节目录", "Contents", "CONTENTS", ""}:
                start -= 1
            else:
                break
        end = cluster[-1].line_no + 1
        ranges.append((start, end))
        skip_lines.update(item.line_no for item in cluster)

    filtered = [item for item in candidates if item.line_no not in skip_lines]
    return filtered, ranges


def line_is_in_ranges(line_no: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= line_no < end for start, end in ranges)


def slice_lines_excluding_ranges(lines: list[str], start: int, end: int, ranges: list[tuple[int, int]]) -> list[str]:
    return [lines[i] for i in range(start, end) if not line_is_in_ranges(i, ranges)]


def trim_outer_blank_lines(lines: list[str]) -> list[str]:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def is_metadata_only_prefix(lines: list[str]) -> bool:
    meaningful = [line.strip() for line in lines if line.strip()]
    if not meaningful:
        return True
    return all(METADATA_PREFIX_RE.match(line) for line in meaningful)


def split_chapters(
    text: str,
    custom_patterns: list[re.Pattern[str]],
    max_title_length: int,
    keep_toc_text: bool,
) -> tuple[list[Chapter], list[str], int]:
    lines = text.split("\n")
    candidates = find_chapter_candidates(lines, custom_patterns, max_title_length)
    raw_candidate_count = len(candidates)
    toc_ranges: list[tuple[int, int]] = []
    if not keep_toc_text:
        candidates, toc_ranges = detect_toc_ranges(lines, candidates)

    warnings: list[str] = []
    if not candidates:
        warnings.append("未识别到章节标题，已把全文作为单章 EPUB。")
        return [Chapter("正文", trim_outer_blank_lines(lines), None)], warnings, raw_candidate_count

    chapters: list[Chapter] = []
    first = candidates[0]
    prefix_lines = trim_outer_blank_lines(slice_lines_excluding_ranges(lines, 0, first.line_no, toc_ranges))
    if prefix_lines and not is_metadata_only_prefix(prefix_lines):
        chapters.append(Chapter("开篇", prefix_lines, None))

    for idx, candidate in enumerate(candidates):
        next_line = candidates[idx + 1].line_no if idx + 1 < len(candidates) else len(lines)
        body = trim_outer_blank_lines(slice_lines_excluding_ranges(lines, candidate.line_no + 1, next_line, toc_ranges))
        chapters.append(Chapter(candidate.title, body, candidate.line_no + 1))

    if toc_ranges:
        warnings.append(f"检测到并跳过疑似 TXT 自带目录区块 {len(toc_ranges)} 个，避免目录重复。")
    return chapters, warnings, raw_candidate_count


def detect_metadata_from_text(text: str, fallback_title: str) -> tuple[str, str]:
    title = fallback_title
    author = "未知作者"
    for raw_line in text.split("\n")[:120]:
        line = raw_line.strip()
        if not line:
            continue
        author_match = re.match(r"^(?:作者|作\s*者|作者名)\s*[:：]\s*(.+)$", line)
        if author_match:
            candidate = author_match.group(1).strip()
            if 0 < len(candidate) <= 60:
                author = candidate
        title_match = re.match(r"^(?:书名|作品名|小说名)\s*[:：]\s*(.+)$", line)
        if title_match:
            candidate = title_match.group(1).strip()
            if 0 < len(candidate) <= 80:
                title = candidate
    return title, author


def escape_text(text: str) -> str:
    return html.escape(text, quote=False)


def escape_attr(text: str) -> str:
    return html.escape(text, quote=True)


def render_paragraphs(lines: list[str]) -> str:
    output: list[str] = []
    blank_pending = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            blank_pending = True
            continue

        if blank_pending and output:
            output.append('<p class="blank">&#160;</p>')
        blank_pending = False

        escaped = escape_text(line)
        if SEPARATOR_RE.match(line):
            output.append(f'<p class="scene-break">{escaped}</p>')
        else:
            output.append(f"<p>{escaped}</p>")
    if not output:
        output.append('<p class="blank">&#160;</p>')
    return "\n".join(output)


def render_xhtml(title: str, body_title: str | None, lines: list[str], language: str) -> str:
    h1 = f"<h1>{escape_text(body_title)}</h1>\n" if body_title else ""
    body = render_paragraphs(lines)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{escape_attr(language)}" xml:lang="{escape_attr(language)}">
<head>
  <meta charset="utf-8" />
  <title>{escape_text(title)}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css" />
</head>
<body>
{h1}{body}
</body>
</html>
"""


def render_cover_xhtml(title: str, image_href: str, language: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{escape_attr(language)}" xml:lang="{escape_attr(language)}">
<head>
  <meta charset="utf-8" />
  <title>{escape_text(title)} 封面</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css" />
</head>
<body class="cover-page">
  <img src="../{escape_attr(image_href)}" alt="{escape_attr(title)}" />
</body>
</html>
"""


def render_css(font_family: str | None, font_href: str | None) -> str:
    font_face = ""
    body_font = '"Noto Serif CJK SC", "Source Han Serif SC", "Microsoft YaHei", "SimSun", serif'
    if font_family and font_href:
        body_font = f'"{font_family}", {body_font}'
        font_face = f"""@font-face {{
  font-family: "{font_family}";
  src: url("../{font_href}");
}}

"""
    return font_face + f"""body {{
  margin: 0 6%;
  padding: 0;
  font-family: {body_font};
  line-height: 1.82;
  color: #111;
  background: #fff;
}}

h1 {{
  margin: 2.2em 0 1.6em;
  font-size: 1.35em;
  line-height: 1.45;
  text-align: center;
  font-weight: bold;
  page-break-before: always;
}}

p {{
  margin: 0.35em 0;
  text-indent: 2em;
  widows: 2;
  orphans: 2;
}}

p.blank {{
  height: 0.7em;
  line-height: 0.7em;
  margin: 0;
  text-indent: 0;
}}

p.scene-break {{
  text-align: center;
  text-indent: 0;
  margin: 1.2em 0;
  letter-spacing: 0.08em;
}}

.cover-page {{
  margin: 0;
  padding: 0;
  text-align: center;
}}

.cover-page img {{
  max-width: 100%;
  max-height: 100%;
}}
"""


def chunk_lines(lines: list[str], max_chars: int) -> list[list[str]]:
    if max_chars <= 0:
        return [lines]
    chunks: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for line in lines:
        line_chars = len(line) + 1
        if current and current_chars + line_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(line)
        current_chars += line_chars
    if current:
        chunks.append(current)
    return chunks or [[]]


def safe_filename(name: str, default: str = "book") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = default
    return name[:120]


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(2, 10_000):
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"无法为 {path} 生成不冲突的文件名。")


def media_type_for_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".ttf":
        return "font/ttf"
    if suffix == ".otf":
        return "font/otf"
    if suffix == ".woff":
        return "font/woff"
    if suffix == ".woff2":
        return "font/woff2"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    if suffix == ".webp":
        return "image/webp"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def make_default_output_dir() -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_BASE / f"txt转epub_{stamp}"


def build_epub(
    chapters: list[Chapter],
    output_path: Path,
    title: str,
    author: str,
    language: str,
    font_path: Path | None,
    cover_image: Path | None,
    max_chars_per_xhtml: int,
    publisher: str | None = None,
    description: str | None = None,
) -> None:
    uid = f"urn:uuid:{uuid.uuid4()}"
    modified = _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    manifest_items: list[dict[str, str]] = []
    spine_ids: list[str] = []
    nav_items: list[tuple[str, str]] = []
    file_payloads: list[tuple[str, bytes | str, int]] = []

    font_family: str | None = None
    font_href: str | None = None
    if font_path:
        font_family = safe_filename(font_path.stem, "EmbeddedCJK")
        font_href = f"Fonts/{safe_filename(font_path.name, 'font.ttf')}"
        manifest_items.append(
            {
                "id": "embedded-font",
                "href": font_href,
                "media-type": media_type_for_file(font_path),
            }
        )
        file_payloads.append((f"OEBPS/{font_href}", font_path.read_bytes(), zipfile.ZIP_DEFLATED))

    cover_href: str | None = None
    if cover_image:
        cover_href = f"Images/{safe_filename(cover_image.name, 'cover')}"
        cover_media_type = media_type_for_file(cover_image)
        manifest_items.append(
            {
                "id": "cover-image",
                "href": cover_href,
                "media-type": cover_media_type,
                "properties": "cover-image",
            }
        )
        file_payloads.append((f"OEBPS/{cover_href}", cover_image.read_bytes(), zipfile.ZIP_DEFLATED))

        cover_doc_id = "cover"
        cover_doc_href = "Text/cover.xhtml"
        cover_xhtml = render_cover_xhtml(title, cover_href, language)
        manifest_items.append(
            {
                "id": cover_doc_id,
                "href": cover_doc_href,
                "media-type": "application/xhtml+xml",
            }
        )
        file_payloads.append((f"OEBPS/{cover_doc_href}", cover_xhtml, zipfile.ZIP_DEFLATED))
        spine_ids.append(cover_doc_id)

    doc_index = 1
    for chapter_index, chapter in enumerate(chapters, start=1):
        chunks = chunk_lines(chapter.lines, max_chars_per_xhtml)
        first_href: str | None = None
        for part_index, lines in enumerate(chunks, start=1):
            doc_id = f"chap{doc_index:05d}"
            href = f"Text/chapter_{doc_index:05d}.xhtml"
            if first_href is None:
                first_href = href
                chapter.href = href
                body_title = chapter.title
                page_title = chapter.title
            else:
                body_title = f"{chapter.title}（续）"
                page_title = body_title

            xhtml = render_xhtml(page_title, body_title, lines, language)
            manifest_items.append(
                {
                    "id": doc_id,
                    "href": href,
                    "media-type": "application/xhtml+xml",
                }
            )
            file_payloads.append((f"OEBPS/{href}", xhtml, zipfile.ZIP_DEFLATED))
            spine_ids.append(doc_id)
            doc_index += 1

        nav_items.append((chapter.title, first_href or f"Text/chapter_{doc_index:05d}.xhtml"))

    css = render_css(font_family, font_href)
    manifest_items.append({"id": "style", "href": "Styles/style.css", "media-type": "text/css"})
    file_payloads.append(("OEBPS/Styles/style.css", css, zipfile.ZIP_DEFLATED))

    nav_xhtml = render_nav(title, nav_items, language)
    ncx = render_ncx(title, author, uid, nav_items)
    opf = render_opf(
        title=title,
        author=author,
        language=language,
        uid=uid,
        modified=modified,
        manifest_items=manifest_items,
        spine_ids=spine_ids,
        publisher=publisher,
        description=description,
    )

    container_xml = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        epub.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/content.opf", opf, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/nav.xhtml", nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)
        epub.writestr("OEBPS/toc.ncx", ncx, compress_type=zipfile.ZIP_DEFLATED)
        for archive_name, payload, compression in file_payloads:
            epub.writestr(archive_name, payload, compress_type=compression)


def render_nav(title: str, nav_items: list[tuple[str, str]], language: str) -> str:
    links = "\n".join(
        f'      <li><a href="{escape_attr(href)}">{escape_text(item_title)}</a></li>'
        for item_title, href in nav_items
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{escape_attr(language)}" xml:lang="{escape_attr(language)}">
<head>
  <meta charset="utf-8" />
  <title>{escape_text(title)} 目录</title>
  <link rel="stylesheet" type="text/css" href="Styles/style.css" />
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>目录</h1>
    <ol>
{links}
    </ol>
  </nav>
</body>
</html>
"""


def render_ncx(title: str, author: str, uid: str, nav_items: list[tuple[str, str]]) -> str:
    nav_points: list[str] = []
    for index, (item_title, href) in enumerate(nav_items, start=1):
        nav_points.append(
            f"""    <navPoint id="navPoint-{index}" playOrder="{index}">
      <navLabel><text>{escape_text(item_title)}</text></navLabel>
      <content src="{escape_attr(href)}" />
    </navPoint>"""
        )
    nav_map = "\n".join(nav_points)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="{escape_attr(uid)}" />
    <meta name="dtb:depth" content="1" />
    <meta name="dtb:totalPageCount" content="0" />
    <meta name="dtb:maxPageNumber" content="0" />
  </head>
  <docTitle><text>{escape_text(title)}</text></docTitle>
  <docAuthor><text>{escape_text(author)}</text></docAuthor>
  <navMap>
{nav_map}
  </navMap>
</ncx>
"""


def render_manifest_item(item: dict[str, str]) -> str:
    attrs = [
        f'id="{escape_attr(item["id"])}"',
        f'href="{escape_attr(item["href"])}"',
        f'media-type="{escape_attr(item["media-type"])}"',
    ]
    if item.get("properties"):
        attrs.append(f'properties="{escape_attr(item["properties"])}"')
    return "    <item " + " ".join(attrs) + " />"


def render_opf(
    title: str,
    author: str,
    language: str,
    uid: str,
    modified: str,
    manifest_items: list[dict[str, str]],
    spine_ids: list[str],
    publisher: str | None,
    description: str | None,
) -> str:
    manifest = "\n".join(
        [
            '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />',
            '    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />',
        ]
        + [render_manifest_item(item) for item in manifest_items]
    )
    spine = "\n".join(f'    <itemref idref="{escape_attr(item_id)}" />' for item_id in spine_ids)
    publisher_xml = f"    <dc:publisher>{escape_text(publisher)}</dc:publisher>\n" if publisher else ""
    description_xml = f"    <dc:description>{escape_text(description)}</dc:description>\n" if description else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape_text(uid)}</dc:identifier>
    <dc:title>{escape_text(title)}</dc:title>
    <dc:creator>{escape_text(author)}</dc:creator>
    <dc:language>{escape_text(language)}</dc:language>
{publisher_xml}{description_xml}    <meta property="dcterms:modified">{escape_text(modified)}</meta>
    <meta name="generator" content="txt_to_epub.py {escape_attr(TOOL_VERSION)}" />
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine toc="ncx">
{spine}
  </spine>
</package>
"""


def validate_epub(path: Path) -> list[str]:
    warnings: list[str] = []
    with zipfile.ZipFile(path, "r") as epub:
        names = epub.namelist()
        if not names or names[0] != "mimetype":
            warnings.append("EPUB mimetype 不是 zip 内第一个文件，部分老阅读器可能不兼容。")
        try:
            mimetype = epub.read("mimetype").decode("ascii")
        except KeyError:
            warnings.append("EPUB 缺少 mimetype 文件。")
            mimetype = ""
        if mimetype != "application/epub+zip":
            warnings.append("EPUB mimetype 内容不正确。")
        for required in ("META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/toc.ncx"):
            if required not in names:
                warnings.append(f"EPUB 缺少必要文件：{required}")
    return warnings


def compile_custom_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    compiled: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern))
        except re.error as exc:
            raise ValueError(f"自定义章节正则无效：{pattern!r}，错误：{exc}") from exc
    return compiled


def convert_one(
    input_path: Path,
    output_dir: Path,
    args: argparse.Namespace,
    custom_patterns: list[re.Pattern[str]],
) -> ConversionResult:
    warnings: list[str] = []
    try:
        if args.encoding:
            text, encoding_info = decode_with_forced_encoding(input_path, args.encoding)
        else:
            text, encoding_info = decode_txt_file(input_path)
        warnings.extend(encoding_info.warnings)

        title, detected_author = detect_metadata_from_text(text, input_path.stem)
        title = args.title or title
        author = args.author or detected_author

        chapters, chapter_warnings, raw_candidate_count = split_chapters(
            text=text,
            custom_patterns=custom_patterns,
            max_title_length=args.max_title_length,
            keep_toc_text=args.keep_toc_text,
        )
        warnings.extend(chapter_warnings)

        if args.preview:
            print(f"\n《{title}》 预览：{input_path}")
            print(f"编码：{encoding_info.encoding}，章节数：{len(chapters)}，候选标题数：{raw_candidate_count}")
            for index, chapter in enumerate(chapters[: args.preview_limit], start=1):
                line_info = f" 行 {chapter.source_line_no}" if chapter.source_line_no else ""
                print(f"{index:04d}. {chapter.title}{line_info}")
            if len(chapters) > args.preview_limit:
                print(f"... 还有 {len(chapters) - args.preview_limit} 章未显示")
            return ConversionResult(
                source=str(input_path),
                output=None,
                title=title,
                author=author,
                encoding=encoding_info.encoding,
                strict_encoding=encoding_info.strict,
                chapter_count=len(chapters),
                warnings=warnings,
                status="preview",
            )

        safe_title = safe_filename(title, input_path.stem)
        output_path = output_dir / f"{safe_title}.epub"
        if output_path.exists() and not args.overwrite:
            output_path = unique_path(output_path)

        font_path = Path(args.font).expanduser().resolve() if args.font else None
        cover_path = Path(args.cover_image).expanduser().resolve() if args.cover_image else None
        if font_path and not font_path.is_file():
            raise FileNotFoundError(f"字体文件不存在：{font_path}")
        if cover_path and not cover_path.is_file():
            raise FileNotFoundError(f"封面图片不存在：{cover_path}")

        build_epub(
            chapters=chapters,
            output_path=output_path,
            title=title,
            author=author,
            language=args.language,
            font_path=font_path,
            cover_image=cover_path,
            max_chars_per_xhtml=args.max_chars_per_xhtml,
            publisher=args.publisher,
            description=args.description,
        )
        warnings.extend(validate_epub(output_path))

        return ConversionResult(
            source=str(input_path),
            output=str(output_path),
            title=title,
            author=author,
            encoding=encoding_info.encoding,
            strict_encoding=encoding_info.strict,
            chapter_count=len(chapters),
            warnings=warnings,
            status="ok",
        )
    except Exception as exc:  # noqa: BLE001 - CLI should continue converting other books.
        return ConversionResult(
            source=str(input_path),
            output=None,
            title=input_path.stem,
            author=args.author or "未知作者",
            encoding=args.encoding or "auto",
            strict_encoding=False,
            chapter_count=0,
            warnings=warnings,
            status="failed",
            error=str(exc),
        )


def collect_input_files(paths: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = path.expanduser()
        if path.is_dir():
            iterator = path.rglob("*.txt") if recursive else path.glob("*.txt")
            files.extend(sorted(item for item in iterator if item.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"输入路径不存在：{path}")
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in files:
        resolved = item.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def write_reports(output_dir: Path, results: list[ConversionResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "conversion_report.json"
    txt_path = output_dir / "conversion_report.txt"
    payload = [result.__dict__ for result in results]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = []
    for result in results:
        lines.append(f"[{result.status}] {result.source}")
        if result.output:
            lines.append(f"  输出：{result.output}")
        lines.append(f"  书名：{result.title}")
        lines.append(f"  作者：{result.author}")
        lines.append(f"  编码：{result.encoding} strict={result.strict_encoding}")
        lines.append(f"  章节：{result.chapter_count}")
        if result.error:
            lines.append(f"  错误：{result.error}")
        for warning in result.warnings:
            lines.append(f"  警告：{warning}")
        lines.append("")
    txt_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="把中文 TXT 长篇小说批量转换成带目录的 EPUB。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("inputs", nargs="+", help="TXT 文件或包含 TXT 的文件夹。")
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help=r"输出文件夹。默认会新建到 E:\不知道\txt转epub_时间戳。",
    )
    parser.add_argument("--recursive", action="store_true", help="输入为文件夹时递归查找 TXT。")
    parser.add_argument("--overwrite", action="store_true", help="允许覆盖同名 EPUB。")
    parser.add_argument("--encoding", help="强制指定 TXT 编码，例如 utf-8、gb18030、big5。")
    parser.add_argument("--title", help="强制指定书名；批量转换时不建议使用。")
    parser.add_argument("--author", help="强制指定作者。")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="EPUB 语言标记。")
    parser.add_argument("--publisher", help="EPUB 出版者元数据。")
    parser.add_argument("--description", help="EPUB 简介元数据。")
    parser.add_argument("--font", help="嵌入字体文件，推荐 Noto/思源类 CJK 字体。")
    parser.add_argument("--cover-image", help="封面图片路径，支持 jpg/png/gif/webp。")
    parser.add_argument(
        "--chapter-regex",
        action="append",
        default=[],
        help="额外章节标题正则，可重复传入。正则需匹配整行标题。",
    )
    parser.add_argument(
        "--allow-weak-numbered-title",
        action="store_true",
        help="允许把“一、标题 / 1. 标题”这类弱格式识别为章节；正文误判风险更高。",
    )
    parser.add_argument(
        "--max-title-length",
        type=int,
        default=MAX_TITLE_LENGTH,
        help="章节标题最大字符数，过长的行不会被当作标题。",
    )
    parser.add_argument(
        "--max-chars-per-xhtml",
        type=int,
        default=DEFAULT_MAX_CHARS_PER_XHTML,
        help="单个 XHTML 文件最大字符数；长章节会自动拆成续页，但目录只保留章标题。",
    )
    parser.add_argument("--keep-toc-text", action="store_true", help="保留 TXT 开头疑似自带目录文本。")
    parser.add_argument("--preview", action="store_true", help="只预览识别出的目录，不生成 EPUB。")
    parser.add_argument("--preview-limit", type=int, default=80, help="预览目录时最多显示多少章。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    input_paths = [Path(item) for item in args.inputs]

    try:
        files = collect_input_files(input_paths, args.recursive)
    except Exception as exc:  # noqa: BLE001
        print(f"输入错误：{exc}", file=sys.stderr)
        return 2

    if not files:
        print("没有找到可转换的 TXT 文件。", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser() if args.output_dir else make_default_output_dir()
    try:
        custom_patterns = compile_custom_patterns(args.chapter_regex)
        if args.allow_weak_numbered_title:
            custom_patterns.append(WEAK_NUMBERED_TITLE_PATTERN)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.preview:
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"无法创建输出目录：{output_dir}\n{exc}", file=sys.stderr)
            print("可以用 --output-dir 指定一个已有可写目录。", file=sys.stderr)
            return 2

    results: list[ConversionResult] = []
    for index, file_path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] 处理：{file_path}")
        result = convert_one(file_path, output_dir, args, custom_patterns)
        results.append(result)
        if result.status == "ok":
            print(f"  已生成：{result.output}")
        elif result.status == "preview":
            pass
        else:
            print(f"  失败：{result.error}", file=sys.stderr)

    if not args.preview:
        write_reports(output_dir, results)
        print(f"\n转换报告：{output_dir / 'conversion_report.txt'}")

    ok_count = sum(1 for item in results if item.status == "ok")
    failed_count = sum(1 for item in results if item.status == "failed")
    preview_count = sum(1 for item in results if item.status == "preview")
    print(f"完成：ok={ok_count}, failed={failed_count}, preview={preview_count}")
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
