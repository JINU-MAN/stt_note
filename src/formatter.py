import re
from datetime import datetime

# 문장 끝 패턴: 한국어 종결어미 또는 문장부호로 끝나는 경우
_SENTENCE_END = re.compile(r'[.!?。！？]\s*$|[다요죠까네요]\s*$')

# 단락 분리 기준: 이 글자수 이상 쌓인 후 문장 끝에서 분리
_MIN_PARA_CHARS = 90


def format_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def format_duration(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h}시간 {m}분 {s}초"
    if m > 0:
        return f"{m}분 {s}초"
    return f"{s}초"


_NOTION_TEXT_LIMIT = 2000


def _make_paragraph_block(start_time: float, segments: list) -> list[dict]:
    """단락 하나를 Notion 블록 리스트로 변환. 텍스트가 2000자를 넘으면 블록을 분할합니다."""
    timestamp = format_timestamp(start_time)
    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())

    blocks = []
    # 첫 번째 청크: 타임스탬프 + 텍스트 앞부분
    first_chunk = text[:_NOTION_TEXT_LIMIT]
    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {"content": f"[{timestamp}]  "},
                    "annotations": {"bold": True, "color": "gray"},
                },
                {
                    "type": "text",
                    "text": {"content": first_chunk},
                },
            ]
        },
    })

    # 2000자 초과분은 추가 블록으로 분할
    for i in range(_NOTION_TEXT_LIMIT, len(text), _NOTION_TEXT_LIMIT):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": text[i:i + _NOTION_TEXT_LIMIT]},
                }]
            },
        })

    return blocks


def segments_to_notion_blocks(segments: list, filename: str, duration: float) -> list[dict]:
    """
    Convert faster-whisper segments into Notion block objects.

    Groups consecutive segments into paragraphs when silence gap > 2 seconds.
    Prepends a metadata callout block.
    """
    blocks: list[dict] = []

    # Metadata callout
    date_str = datetime.now().strftime("%Y-%m-%d")
    duration_str = format_duration(duration)
    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{
                "type": "text",
                "text": {"content": f"📅 {date_str}    📁 {filename}    ⏱ {duration_str}"},
            }],
            "icon": {"type": "emoji", "emoji": "📝"},
            "color": "gray_background",
        },
    })

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    if not segments:
        return blocks

    # 90자 이상 쌓인 후 문장 끝 세그먼트에서 단락 분리
    groups: list[tuple[float, list]] = []
    current_group: list = []
    current_start: float | None = None
    current_chars: int = 0

    for seg in segments:
        text = seg.text.strip()
        if not current_group:
            current_start = seg.start
        current_group.append(seg)
        current_chars += len(text)

        if current_chars >= _MIN_PARA_CHARS and _SENTENCE_END.search(text):
            groups.append((current_start, current_group))
            current_group = []
            current_chars = 0
            current_start = None

    if current_group:
        groups.append((current_start, current_group))

    for start_time, group in groups:
        text = " ".join(seg.text.strip() for seg in group if seg.text.strip())
        if text:
            blocks.extend(_make_paragraph_block(start_time, group))

    return blocks


def segments_to_text(segments: list, filename: str, duration: float) -> str:
    """전사 결과를 txt 파일용 텍스트로 변환."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    duration_str = format_duration(duration)

    lines = [
        f"파일: {filename}",
        f"날짜: {date_str}",
        f"길이: {duration_str}",
        "",
        "=" * 50,
        "",
    ]

    if not segments:
        return "\n".join(lines)

    groups: list[tuple[float, list]] = []
    current_group: list = []
    current_start: float | None = None
    current_chars: int = 0

    for seg in segments:
        text = seg.text.strip()
        if not current_group:
            current_start = seg.start
        current_group.append(seg)
        current_chars += len(text)

        if current_chars >= _MIN_PARA_CHARS and _SENTENCE_END.search(text):
            groups.append((current_start, current_group))
            current_group = []
            current_chars = 0
            current_start = None

    if current_group:
        groups.append((current_start, current_group))

    for start_time, group in groups:
        text = " ".join(seg.text.strip() for seg in group if seg.text.strip())
        if text:
            lines.append(f"[{format_timestamp(start_time)}]  {text}")
            lines.append("")

    return "\n".join(lines)


def summary_to_notion_blocks(summary: str, chunk_summaries: list[str]) -> list[dict]:
    """요약 결과를 Notion 블록으로 변환. 전사 텍스트 아래에 추가됩니다."""
    blocks: list[dict] = []

    blocks.append({"object": "block", "type": "divider", "divider": {}})

    blocks.append({
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": "AI 요약"}}],
            "icon": {"type": "emoji", "emoji": "💡"},
            "color": "blue_background",
        },
    })

    # 최종 요약 (2000자 제한 분할)
    for i in range(0, max(len(summary), 1), _NOTION_TEXT_LIMIT):
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": summary[i:i + _NOTION_TEXT_LIMIT]}}]
            },
        })

    # 구간별 요약이 2개 이상이면 토글로 추가
    if len(chunk_summaries) > 1:
        blocks.append({
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": "구간별 요약"}}],
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": f"[{i + 1}구간]  "},
                                    "annotations": {"bold": True},
                                },
                                {
                                    "type": "text",
                                    "text": {"content": s[:_NOTION_TEXT_LIMIT]},
                                },
                            ]
                        },
                    }
                    for i, s in enumerate(chunk_summaries)
                ],
            },
        })

    return blocks
