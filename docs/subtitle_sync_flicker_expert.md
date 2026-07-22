# Expert Consultation: Subtitle Sync + Flickering Issues

## System Overview

We're generating TikTok/CapCut-style word-by-word animated subtitles using ASS format in a video generation tool (MoneyPrinterTurbo). The pipeline:

1. **TTS** → Edge TTS (`es-US-AlonsoNeural-Male`) generates audio + word-level timing cues
2. **Subtitle** → ASS file generated from Edge TTS `SubMaker.cues` (word boundaries)
3. **Video** → FFmpeg `ass` filter burns subtitles into final video via libass

### Current ASS Implementation

```python
# Constants
CHUNK_SIZE = 4  # words per displayed line
OVERLAP = 0.015  # 15ms overlap between consecutive word highlights

# Per word highlight logic:
for i, (cur_word, w_start, w_end) in enumerate(chunk):
    display_start = prev_end - OVERLAP if prev_end is not None else w_start
    display_start = max(display_start, chunk_start_time)
    
    # Build text with yellow highlight on current word
    parts = []
    for j, (w, _, _) in enumerate(chunk):
        if j == i:
            parts.append(f"{{\\1c{hl}}}{w}")  # yellow
        else:
            parts.append(w)  # white
    
    ass_text = " ".join(parts)
    dialogue_lines.append(
        f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,"
        f"{{\\q2\\pos(960,1770)\\fad(30,30)}}{ass_text}"
    )
    prev_end = w_end
```

### Current ASS Style

```ass
[V4+ Styles]
Style: Default,Anton,110,&H00FFFFFF,&H000000FF,&H00FFFFFF,&H80000000,-1,0,0,0,100,100,2,0,1,3,2,2,80,80,150,1
```

Fields:
- PrimaryColour: `&H00FFFFFF` (white)
- SecondaryColour: `&H000000FF` (red)
- OutlineColour: `&H00FFFFFF` (white glow)
- BackColour: `&H80000000` (50% black)
- BorderStyle: 1 (outline + shadow)
- Outline: 3, Shadow: 2
- Alignment: 2 (bottom center)
- MarginV: 150
- PlayResX: 1920, PlayResY: 1920

### Example ASS Output

```ass
Dialogue: 0,0:00:00.10,0:00:00.30,Default,,0,0,0,,{\q2\pos(960,1770)\fad(30,30)}{\1c&H000000BC}En las llanuras de
Dialogue: 0,0:00:00.28,0:00:00.48,Default,,0,0,0,,{\q2\pos(960,1770)\fad(30,30)}En {\1c&H000000BC}las llanuras de
Dialogue: 0,0:00:00.46,0:00:00.93,Default,,0,0,0,,{\q2\pos(960,1770)\fad(30,30)}En las {\1c&H000000BC}llanuras de
Dialogue: 0,0:00:00.91,0:00:01.01,Default,,0,0,0,,{\q2\pos(960,1770)\fad(30,30)}En las llanuras {\1c&H000000BC}de
```

## PROBLEM 1: Subtitles Not Synced with Speech

### Symptoms
- Subtitles appear BEFORE the word is spoken (subtitles lead the audio)
- Or subtitles appear AFTER the word is spoken (subtitles lag behind)
- The offset is consistent throughout the video (not random)

### What We've Verified
- Edge TTS `SubMaker.cues` provide `WordBoundary` events with `start`/`end` timestamps
- These timestamps come directly from Edge TTS server (not generated locally)
- The audio file is written synchronously with the cues
- Total audio duration matches video duration (~58.7s)

### Theoretical Causes

1. **Edge TTS cue offset**: Does Edge TTS report word boundaries relative to the start of the audio stream, or is there an inherent offset (e.g., audio buffer delay)?

2. **Audio encoding delay**: When Edge TTS writes audio chunks, is there a delay between the first byte written and when playback would start? MP3 encoding adds ~50-100ms header.

3. **FFmpeg concat delay**: When clips are concatenated, does FFmpeg introduce any timing offset?

4. **Audio codec delay**: Does the AAC/MP3 encoder introduce decode delay that shifts all timestamps?

5. **MoviePy audio extraction**: When MoviePy writes the final video with audio, does it shift the audio track?

6. **Edge TTS streaming behavior**: The audio is streamed in chunks. Could the first few chunks of audio have a different timing relationship with the cues than later chunks?

7. **Word boundary precision**: Are Edge TTS word boundaries aligned to phoneme boundaries or word boundaries? Could there be a systematic offset?

### Questions for Expert

1. **What is the typical timing offset between Edge TTS word boundaries and actual audio playback?** Is there a known offset (e.g., +100ms, -50ms)?

2. **How does Edge TTS `WordBoundary` timing work internally?** Does it report:
   - Time relative to start of audio stream?
   - Time relative to start of speech synthesis?
   - Time with some inherent offset for audio buffering?

3. **What is the MP3/AAC encoder delay?** When we encode audio with FFmpeg, does it add delay to all timestamps? How do we compensate?

4. **How to empirically measure the offset?** What's the best way to:
   - Extract a frame at a specific timestamp
   - Compare subtitle position with expected speech
   - Calculate the actual offset?

5. **Should we add a configurable offset parameter?** If so, what's a good default for Edge TTS Spanish voice?

6. **Does the `OVERLAP = 0.015` (15ms) between consecutive word highlights cause sync perception issues?** Should we remove or adjust this?

7. **Edge TTS 7.x specifically**: Does the newer version of edge_tts handle timing differently than older versions? Are there known timing bugs?

---

## PROBLEM 2: Flickering Text

### Symptoms
- Subtitle text appears to "flicker" or "flash" during playback
- Most noticeable when words change (highlight moves from one word to next)
- The entire text line seems to briefly disappear or change opacity

### Current Implementation Details

Each word highlight creates a SEPARATE dialogue line:
```
Dialogue: 0,0:00:00.10,0:00:00.30,... {\1c&H...}En las llanuras de
Dialogue: 0,0:00:00.28,0:00:00.48,... En {\1c&H...}las llanuras de
```

Key observations:
- Line 1 ends at 0:00:00.30
- Line 2 starts at 0:00:00.28 (15ms BEFORE line 1 ends = OVERLAP)
- During 0:00:00.28-0:00:00.30, BOTH lines are active simultaneously

### Theoretical Causes

1. **Overlapping dialogue lines**: Two lines active at the same time could cause rendering artifacts. libass might render one on top of the other, causing opacity/color conflicts.

2. **`\fad(30,30)` on EVERY line**: Each word highlight has a 30ms fade-in and 30ms fade-out. With 4 words per chunk and ~200ms per word, that's 4 × 60ms = 240ms of fade effects per chunk. The fades might overlap with the next chunk's fades.

3. **BorderStyle 1 + Outline/Shadow**: With outline+shadow mode, each overlapping dialogue line creates its own outline. When two lines overlap, you get double outlines, which looks like a flash.

4. **Color transition flash**: When the highlight moves from word N to word N+1, the yellow color jumps. libass might render a single frame where both the old and new yellow word are visible, or neither is visible.

5. **Anti-aliasing artifacts**: libass re-rasterizes text for each dialogue line. When two lines with slightly different text overlap, the anti-aliasing changes, causing visual flicker.

6. **`ScaledBorderAndShadow: yes`**: This scales outline/shadow based on PlayResX. Could this cause inconsistent rendering between overlapping lines?

### Questions for Expert

1. **Do overlapping ASS dialogue lines cause flickering?** When two `Dialogue` lines overlap in time, how does libass render them? Does it:
   - Layer them (alpha blend)?
   - Replace the earlier line?
   - Render both independently?

2. **Is `\fad(30,30)` appropriate for word-by-word highlights?** The fade creates a 30ms transition. At 30fps, that's ~1 frame. Is this too aggressive? Should we:
   - Remove `\fad` entirely (instant switch)?
   - Use `\fad(10,10)` for subtler transition?
   - Only apply fade on chunk boundaries (not within chunks)?

3. **How to eliminate overlap between consecutive word highlights?** Should we:
   - Remove `OVERLAP` entirely (strict non-overlapping times)?
   - Use `display_start = prev_end` (no overlap, no gap)?
   - Ensure each dialogue line's end time < next line's start time?

4. **BorderStyle interaction with overlaps**: With `BorderStyle: 1` (outline), do overlapping lines cause double-outline artifacts? Would `BorderStyle: 4` (opaque box) reduce flickering?

5. **Should we use `\alpha` tags** to control per-line opacity during transitions instead of `\fad`?

6. **Is the flickering from the ASS renderer (libass) or the video encoder (libx264)?** Could the encoder's motion estimation cause artifacts between frames with slightly different subtitle renders?

7. **Optimal chunk_size**: We use `CHUNK_SIZE = 4` (4 words per displayed line). Would a different chunk size reduce flickering?

---

## IMPLEMENTATION CONTEXT

### What We've Already Implemented

| Feature | Status | Notes |
|---------|--------|-------|
| Word-by-word ASS subtitles | Working | TikTok/CapCut style, yellow highlight |
| PlayResX 1920 | Working | Prevents text wrapping |
| `\q2 + \pos` | Working | Fixed position, no wrap |
| BorderStyle 1 + white glow | Just added | Outline 3, Shadow 2 |
| Ken Burns zoompan | Working | FFmpeg-based, 2x oversample |
| rembg caching | Working | Content-hash, instant re-runs |
| VAAPI detection | Working | Auto-detect /dev/dri |
| Force-cover crop | Just added | No black borders for 1:1 images |
| ASS via libx264 | Just fixed | VAAPI incompatible with ass filter |

### Hardware

| Component | Specification |
|-----------|--------------|
| CPU | Intel Core i3-1115G4 (2C/4T, 4.1GHz) |
| RAM | 12 GB DDR4 |
| GPU | Intel UHD Graphics G4 (NO CUDA) |
| OS | Linux |
| FFmpeg | n8.1 with libass, libx264, fontconfig |
| Python | 3.11.11 |
| edge-tts | 7.x (SubMaker with cues) |

### TTS Configuration

- Provider: `edge`
- Voice: `es-US-AlonsoNeural-Male` (Spanish)
- Rate: default
- Word boundaries: from `WordBoundary` events via `SubMaker.cues`

### Video Pipeline

```
1. DeepSeek API → script
2. Edge TTS → audio.mp3 + SubMaker.cues (word timing)
3. Pixabay → images
4. FFmpeg zoompan → Ken Burns clips (per image)
5. rembg → parallax clips (if enabled)
6. ASS subtitle → subtitle.ass (from SubMaker.cues)
7. MoviePy → combined video (all clips concatenated)
8. FFmpeg ass filter → final video with burned subtitles
```

### Key Files

- `app/services/ass_subtitle.py` — ASS generator (our code)
- `app/services/video.py` — FFmpeg filters, Ken Burns, parallax
- `app/services/voice.py` — Edge TTS integration, SubMaker handling
- `app/services/task.py` — Pipeline orchestration

## WHAT WE NEED

1. **Fix subtitle sync** — subtitles must appear exactly when the word is spoken
2. **Fix flickering** — text should be rock-solid stable, no visual artifacts
3. **Maintain TikTok/CapCut style** — word-by-word yellow highlight, white text, bold font
4. **Keep it fast** — we're on a dual-core CPU, can't afford expensive processing
