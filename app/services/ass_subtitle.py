"""
TikTok/CapCut-style ASS subtitle generator.

Expert-optimized (v2 - no flickering, proper sync):
- Single Dialogue line per chunk with \\t transform tags for word-by-word highlight
- No overlapping lines (zero double-render artifacts)
- FFmpeg aresample filter handles audio sync (no manual offset needed)
- PlayResX: 1920 (wider layout region prevents text wrapping)
- BorderStyle 1 (outline+shadow), white outline glow, Anton font
"""

import os
from typing import List, Tuple
from xml.sax.saxutils import unescape

from loguru import logger

from app.config import config
from app.utils import utils

CHUNK_SIZE = 1

# Smooth color transition duration in ms (1 frame at 30fps)
TRANSITION_MS = 30


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


def _build_chunk_dialogue(
    chunk: List[Tuple[str, float, float]],
    pos_x: int,
    pos_y: int,
    highlight_color: str = "#FFFF00",
) -> str:
    """
    Build a single Dialogue line for a chunk of words using \\t transform tags.

    Instead of N separate Dialogue lines (one per word) that overlap and cause
    flickering, we emit ONE line per chunk and animate colors with \\t transforms.

    Example for chunk ["En", "las", "llanuras", "de"]:
      {\\1c&H0000FFFF\\t(280,310,\\1c&H00FFFFFF)}En
      {\\1c&H00FFFFFF\\t(280,310,\\1c&H0000FFFF)}las
      {\\1c&H00FFFFFF\\t(280,310,\\1c&H0000FFFF)}llanuras
      {\\1c&H00FFFFFF}de
    """
    if not chunk:
        return ""

    chunk_start_ms = int(chunk[0][1] * 1000)
    chunk_end_ms = int(chunk[-1][2] * 1000)

    parts = []
    for i, (word, w_start, w_end) in enumerate(chunk):
        w_start_ms = int(w_start * 1000)
        rel_start = max(0, w_start_ms - chunk_start_ms)

        tags = []

        if i == 0:
            # First word starts highlighted
            tags.append(f"\\1c{_hex_to_ass(highlight_color)}")
            # Schedule it to turn white when next word starts
            if len(chunk) > 1:
                next_start_ms = int(chunk[1][1] * 1000) - chunk_start_ms
                tags.append(f"\\t({next_start_ms},{next_start_ms + TRANSITION_MS},\\1c{_hex_to_ass('#FFFFFF')})")
        else:
            # Other words start white, turn highlight at their start time
            tags.append(f"\\1c{_hex_to_ass('#FFFFFF')}")
            tags.append(f"\\t({rel_start},{rel_start + TRANSITION_MS},\\1c{_hex_to_ass(highlight_color)})")
            # If not the last word, schedule it to turn back to white
            if i < len(chunk) - 1:
                next_start_ms = int(chunk[i + 1][1] * 1000) - chunk_start_ms
                tags.append(f"\\t({next_start_ms},{next_start_ms + TRANSITION_MS},\\1c{_hex_to_ass('#FFFFFF')})")

        parts.append(f"{{{''.join(tags)}}}{word}")

    ass_text = " ".join(parts)

    start_time = _seconds_to_ass_time(max(0.0, chunk[0][1]))
    end_time = _seconds_to_ass_time(max(0.0, chunk[-1][2]))

    # \\q2 = no-wrap, \\pos = fixed position
    # No \\fad here — color transitions are handled by \\t transforms
    return f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{{\\q2\\pos({pos_x},{pos_y})}}{ass_text}"


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
    Generate TikTok/CapCut-style ASS subtitle with \\t transforms.

    Expert-optimized (v2):
    - Single Dialogue line per chunk (no overlapping lines)
    - \\t transforms for smooth color transitions (no \\fad flickering)
    - PlayResX 1920 to prevent text wrapping
    - Audio sync handled by FFmpeg aresample filter (no manual offset needed)
    """
    logger.info(f"generating TikTok-style ASS subtitle (v2): {subtitle_file}")

    primary = _hex_to_ass(font_color)

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

            dialogue_line = _build_chunk_dialogue(chunk, pos_x, pos_y, highlight_color=highlight_color)
            if dialogue_line:
                dialogue_lines.append(dialogue_line)

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
    logger.info("generating TikTok-style ASS from Edge TTS cues (v2)")

    # Edge TTS 7.x only gives SentenceBoundary (no WordBoundary).
    # Strategy: use SentenceBoundary timing to anchor proportional word distribution
    # within each sentence. Error accumulates max ~200ms per sentence (imperceptible).
    word_boundaries = []
    sentences = []

    if hasattr(sub_maker, 'cues') and sub_maker.cues:
        # Detect if cues are word-level or sentence-level.
        # SentenceBoundary cues contain spaces (multiple words).
        # WordBoundary cues are single tokens.
        first_content = unescape(sub_maker.cues[0].content).strip()
        is_sentence_level = " " in first_content
        if is_sentence_level:
            # SentenceBoundary cues — use anchored proportional distribution
            logger.info("detected SentenceBoundary cues, using anchored distribution")
            for cue in sub_maker.cues:
                sentence_text = unescape(cue.content).strip()
                if not sentence_text:
                    continue
                sentence_start = cue.start.total_seconds()
                sentence_duration = cue.end.total_seconds() - sentence_start

                words = sentence_text.split()
                if not words:
                    continue

                weights = [len(w) + 1 for w in words]
                total_weight = sum(weights)

                current_time = sentence_start
                for i, word in enumerate(words):
                    word_duration = (weights[i] / total_weight) * sentence_duration
                    word_boundaries.append((word, current_time, current_time + word_duration))
                    current_time += word_duration

                sentences.append((sentence_text, sentence_start, sentence_start + sentence_duration))
            logger.info(f"anchored {len(sentences)} sentences, {len(word_boundaries)} words")
        else:
            # WordBoundary cues — use directly
            logger.info("detected WordBoundary cues, using direct timing")
            for cue in sub_maker.cues:
                word = unescape(cue.content)
                start = cue.start.total_seconds()
                end = cue.end.total_seconds()
                word_boundaries.append((word, start, end))
            # Build sentences from script text using punctuation splits
            # Match words to sentences by order (not naive even split)
            script_lines = utils.split_string_by_punctuations(script_text)
            word_idx = 0
            for line in script_lines:
                line_words_clean = line.strip().split()
                if not line_words_clean:
                    continue
                count = len(line_words_clean)
                line_wb = word_boundaries[word_idx:word_idx + count]
                if line_wb:
                    sentences.append((line.strip(), line_wb[0][1], line_wb[-1][2]))
                    word_idx += count
            # Assign any remaining words to the last sentence
            if word_idx < len(word_boundaries) and sentences:
                remaining = word_boundaries[word_idx:]
                last = sentences[-1]
                sentences[-1] = (last[0], last[1], remaining[-1][2])

    elif hasattr(sub_maker, 'subs') and sub_maker.subs:
        for offset, sub in zip(sub_maker.offset, sub_maker.subs):
            start, end = offset
            start_sec = start / 10_000_000
            end_sec = end / 10_000_000
            word_boundaries.append((unescape(sub), start_sec, end_sec))

    # Fallback: parse from SRT file
    if not sentences:
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
