"""
TikTok/CapCut-style ASS subtitle generator.

Expert-optimized for stable positioning:
- PlayResX: 1920 (wider layout region prevents text wrapping)
- BorderStyle 1 (outline+shadow), white outline glow, Anton font, yellow word highlight
- \\q2 + \\pos on every dialogue line (belt-and-suspenders no-wrap + fixed position)
- \\fad(30,30) for smooth transitions between lines
"""

import os
from typing import List, Tuple
from xml.sax.saxutils import unescape

from loguru import logger

from app.config import config
from app.utils import utils

CHUNK_SIZE = 4
OVERLAP = 0.015


def _seconds_to_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centiseconds = int((secs % 1) * 100)
    whole_secs = int(secs)
    return f"{hours}:{minutes:02d}:{whole_secs:02d}.{centiseconds:02d}"


def _hex_to_ass(hex_color: str) -> str:
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H00{b}{g}{r}".upper()
    return hex_color


def create_word_by_word_ass(
    subtitle_file: str,
    sentences: List[Tuple[str, float, float]],
    word_boundaries: List[Tuple[str, float, float]],
    font_name: str = "Anton",
    font_size: int = 110,
    font_color: str = "#FFFFFF",
    highlight_color: str = "#FFFF00",
    stroke_color: str = "#000000",
    stroke_width: int = 4,
    video_width: int = 1080,
    video_height: int = 1920,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    """
    Generate TikTok/Hormozi-style ASS subtitle.

    Expert-optimized:
    - PlayResX set to 1920 (wider than video) to prevent text wrapping
    - \\q2 on every line forces no-wrap
    - \\pos(960,1770) locks position for Alignment 2 + MarginV 150
    - \\fad(30,30) for smooth transitions
    """
    logger.info(f"generating TikTok-style ASS subtitle: {subtitle_file}")

    primary = _hex_to_ass(font_color)
    hl = _hex_to_ass(highlight_color)

    # PlayResX 1920 > video 1080 — libass scales down, but layout region is wider
    # This prevents text from wrapping when 4 words exceed 980px
    script_res_x = 1920
    script_res_y = video_height

    # X center with PlayResX=1920: 1920/2 = 960
    # Y with MarginV=150: 1920 - 150 = 1770
    pos_x = script_res_x // 2
    pos_y = script_res_y - 150

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {script_res_x}
PlayResY: {script_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary},&H000000FF,&H00FFFFFF,&H80000000,-1,0,0,0,100,100,2,0,1,3,2,2,80,80,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogue_lines = []

    for sentence_text, sent_start, sent_end in sentences:
        clean_text = sentence_text.strip()
        if not clean_text:
            continue

        words = clean_text.split()
        if not words:
            continue

        sentence_wb = []
        for word, w_start, w_end in word_boundaries:
            if w_start < sent_end and w_end > sent_start:
                sentence_wb.append((word, max(w_start, sent_start), min(w_end, sent_end)))

        if len(sentence_wb) < len(words):
            duration = sent_end - sent_start
            word_dur = duration / len(words)
            sentence_wb = []
            t = sent_start
            for w in words:
                e = min(t + word_dur, sent_end)
                sentence_wb.append((w, t, e))
                t = e

        for chunk_idx in range(0, len(sentence_wb), chunk_size):
            chunk = sentence_wb[chunk_idx:chunk_idx + chunk_size]
            if not chunk:
                continue

            chunk_start_time = chunk[0][1]
            prev_end = None

            for i, (cur_word, w_start, w_end) in enumerate(chunk):
                display_start = prev_end - OVERLAP if prev_end is not None else w_start
                display_start = max(display_start, chunk_start_time)

                parts = []
                for j, (w, _, _) in enumerate(chunk):
                    if j == i:
                        parts.append(f"{{\\1c{hl}}}{w}")
                    else:
                        parts.append(w)

                ass_text = " ".join(parts)
                # \\q2 = no-wrap, \\pos = fixed position, \\fad = smooth transitions
                dialogue_lines.append(
                    f"Dialogue: 0,{_seconds_to_ass_time(display_start)},{_seconds_to_ass_time(w_end)},Default,,0,0,0,,{{\\q2\\pos({pos_x},{pos_y})\\fad(30,30)}}{ass_text}"
                )
                prev_end = w_end

    with open(subtitle_file, 'w', encoding='utf-8-sig') as f:
        f.write(header)
        f.write('\n'.join(dialogue_lines))
        f.write('\n')

    logger.info(f"TikTok-style ASS subtitle created: {subtitle_file} ({len(dialogue_lines)} lines)")
    return subtitle_file


def create_word_by_word_ass_from_edge_cues(
    subtitle_file: str,
    sub_maker,
    script_text: str,
    srt_file: str = None,
    font_name: str = "Anton",
    font_size: int = 110,
    font_color: str = "#FFFFFF",
    highlight_color: str = "#FFFF00",
    stroke_color: str = "#000000",
    stroke_width: int = 4,
    video_width: int = 1080,
    video_height: int = 1920,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    logger.info("generating TikTok-style ASS from Edge TTS cues")

    word_boundaries = []
    if hasattr(sub_maker, 'cues') and sub_maker.cues:
        for cue in sub_maker.cues:
            word = unescape(cue.content)
            start = cue.start.total_seconds()
            end = cue.end.total_seconds()
            word_boundaries.append((word, start, end))
    elif hasattr(sub_maker, 'subs') and sub_maker.subs:
        for offset, sub in zip(sub_maker.offset, sub_maker.subs):
            start, end = offset
            start_sec = start / 10_000_000
            end_sec = end / 10_000_000
            word_boundaries.append((unescape(sub), start_sec, end_sec))

    if not word_boundaries:
        logger.warning("no word boundaries from Edge TTS")
        return ""

    sentences = []
    if srt_file and os.path.exists(srt_file):
        from app.services.subtitle import file_to_subtitles
        srt_items_raw = file_to_subtitles(srt_file)
        for idx, time_str, text in srt_items_raw:
            times = time_str.split(' --> ')
            if len(times) != 2:
                continue
            start_str, end_str = times
            start_parts = start_str.replace(',', '.').split(':')
            end_parts = end_str.replace(',', '.').split(':')
            if len(start_parts) == 3 and len(end_parts) == 3:
                start = float(start_parts[0]) * 3600 + float(start_parts[1]) * 60 + float(start_parts[2])
                end = float(end_parts[0]) * 3600 + float(end_parts[1]) * 60 + float(end_parts[2])
                sentences.append((text.strip(), start, end))
        logger.info(f"parsed {len(sentences)} sentences from SRT")
    else:
        script_lines = utils.split_string_by_punctuations(script_text)
        total_words = len(word_boundaries)
        words_per_line = max(1, total_words // len(script_lines)) if script_lines else 1
        word_idx = 0
        for line in script_lines:
            line_words = word_boundaries[word_idx:word_idx + words_per_line]
            if line_words:
                sentences.append((line.strip(), line_words[0][1], line_words[-1][2]))
                word_idx += words_per_line
        if word_idx < total_words and sentences:
            remaining = word_boundaries[word_idx:]
            last = sentences[-1]
            sentences[-1] = (last[0], last[1], remaining[-1][2])

    if not sentences:
        logger.warning("no sentences for ASS subtitle")
        return ""

    font_name = config.ui.get("font_name", font_name)
    highlight_color = config.app.get("subtitle_highlight_color", highlight_color)

    import subprocess
    try:
        result = subprocess.run(["fc-list", f":family={font_name}"], capture_output=True, text=True, timeout=5)
        if not result.stdout.strip():
            for fallback in ["Anton", "Bebas Neue", "Oswald", "Noto Sans Bold"]:
                result = subprocess.run(["fc-list", f":family={fallback}"], capture_output=True, text=True, timeout=5)
                if result.stdout.strip():
                    font_name = fallback
                    logger.info(f"using font: {font_name}")
                    break
            else:
                font_name = "Noto Sans Bold"
    except Exception:
        font_name = "Noto Sans Bold"

    return create_word_by_word_ass(
        subtitle_file=subtitle_file,
        sentences=sentences,
        word_boundaries=word_boundaries,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        highlight_color=highlight_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        video_width=video_width,
        video_height=video_height,
        chunk_size=chunk_size,
    )


def create_word_by_word_ass_from_srt(
    subtitle_file: str,
    srt_file: str,
    audio_duration: float,
    font_name: str = "Anton",
    font_size: int = 110,
    font_color: str = "#FFFFFF",
    highlight_color: str = "#FFFF00",
    stroke_color: str = "#000000",
    stroke_width: int = 4,
    video_width: int = 1080,
    video_height: int = 1920,
    chunk_size: int = CHUNK_SIZE,
) -> str:
    from app.services.subtitle import file_to_subtitles

    srt_items = file_to_subtitles(srt_file)
    if not srt_items:
        return ""

    sentences = []
    for idx, time_str, text in srt_items:
        times = time_str.split(' --> ')
        if len(times) != 2:
            continue
        start_str, end_str = times
        start_parts = start_str.replace(',', '.').split(':')
        end_parts = end_str.replace(',', '.').split(':')
        if len(start_parts) == 3 and len(end_parts) == 3:
            start = float(start_parts[0]) * 3600 + float(start_parts[1]) * 60 + float(start_parts[2])
            end = float(end_parts[0]) * 3600 + float(end_parts[1]) * 60 + float(end_parts[2])
            sentences.append((text.strip(), start, end))

    if not sentences:
        return ""

    word_boundaries = []
    for text, start, end in sentences:
        for word in text.split():
            word_boundaries.append((word, start, end))

    font_name = config.ui.get("font_name", font_name)
    highlight_color = config.app.get("subtitle_highlight_color", highlight_color)

    return create_word_by_word_ass(
        subtitle_file=subtitle_file,
        sentences=sentences,
        word_boundaries=word_boundaries,
        font_name=font_name,
        font_size=font_size,
        font_color=font_color,
        highlight_color=highlight_color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        video_width=video_width,
        video_height=video_height,
        chunk_size=chunk_size,
    )
