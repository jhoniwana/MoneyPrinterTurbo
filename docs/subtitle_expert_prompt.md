# Expert Consultation: ASS Subtitle Position Stability + Performance Optimization

## PART 1: Subtitle Position Problem

### Problem Description

We're generating TikTok/CapCut-style word-by-word animated subtitles using ASS format in a video generation tool (MoneyPrinterTurbo). The subtitles render via FFmpeg's `ass` filter (libass). 

**The core problem: subtitles jump up and down between lines.** Each dialogue line has a different vertical position, creating an unstable, flickering appearance instead of the smooth, consistent bottom-center positioning seen in TikTok/CapCut videos.

### Current ASS Format

```ass
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Anton,120,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,4,0,0,2,50,50,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.50,Default,,0,0,0,,{\1c&H0000FFFF}Hello world this is
Dialogue: 0,0:00:00.48,0:00:01.00,Default,,0,0,0,,Hello {\1c&H0000FFFF}world this is
Dialogue: 0,0:00:00.98,0:00:01.30,Default,,0,0,0,,Hello world {\1c&H0000FFFF}this is
Dialogue: 0,0:00:01.28,0:00:01.50,Default,,0,0,0,,Hello world this {\1c&H0000FFFF}is
Dialogue: 0,0:00:01.50,0:00:01.70,Default,,0,0,0,,{\1c&H0000FFFF}a test
Dialogue: 0,0:00:01.68,0:00:02.00,Default,,0,0,0,,a {\1c&H0000FFFF}test
```

### Key Details

- **Video resolution**: 1080x1920 (vertical/TikTok format)
- **Font**: Anton, size 120
- **BorderStyle**: 4 (opaque box behind text)
- **BackColour**: `&H80000000` (black at 50% opacity)
- **Alignment**: 2 (bottom center)
- **MarginV**: 150
- **Font is bold** (`Bold: -1`)
- **WrapStyle**: 2 (no word wrapping)
- **Rendered via**: FFmpeg `-vf "ass='file.ass'"` using libass

### What We Want

Like TikTok/CapCut captions:
1. **Stable position** — subtitles stay at the exact same Y coordinate regardless of text length
2. **Word-by-word highlight** — current word turns yellow, rest stays white
3. **Black box background** — semi-transparent box behind text for readability
4. **Large bold font** — Anton or similar heavy weight font
5. **3-4 words per line** — not too long

### Specific Questions

1. **Why do the subtitles jump up and down?** Is it because libass re-positions the text based on the visible bounding box of each line? Does `BorderStyle: 4` with `WrapStyle: 2` cause different vertical positions for different text lengths?

2. **How to force a FIXED vertical position?** We want all dialogue lines to render at exactly the same Y coordinate from the bottom, regardless of whether the text is "Hello" or "Hello world this is a very long sentence". What ASS tags or style settings achieve this?

3. **Should we use `\pos(x,y)` override tags?** If so, what coordinates should we use for a 1080x1920 video with bottom-center alignment? Should we calculate the position dynamically?

4. **Is `BorderStyle: 4` correct for a TikTok-style box?** Or should we use `BorderStyle: 1` with `Outline` and `Shadow`? What about `OutlineColour` and `BackColour`?

5. **Does `MarginV` actually work as expected?** Or does libass ignore it when the text bounding box changes?

6. **Should we use `Alignment: 2` (bottom center) or `Alignment: 5` (center center)?** Which gives more predictable positioning?

7. **Any other ASS tricks** to make the subtitle position rock-solid stable like TikTok/CapCut?

---

## PART 2: Performance Optimization

### PC Specifications

| Component | Specification |
|-----------|--------------|
| **CPU** | Intel Core i3-1115G4 (2 cores / 4 threads, up to 4.1 GHz) |
| **RAM** | 12 GB DDR4 |
| **GPU** | Intel UHD Graphics G4 (integrated, NO CUDA) |
| **Storage** | 220 GB NVMe SSD (43 GB free) |
| **OS** | Linux (Ubuntu-based) |
| **Python** | 3.11.11 via uv |
| **FFmpeg** | 6.x with libass, libx264, fontconfig |

### Current Video Generation Pipeline

1. **Script generation** — DeepSeek API call (~2-5s)
2. **Search terms generation** — DeepSeek API call (~2-5s)
3. **Audio generation** — Edge TTS (~10-30s depending on script length)
4. **Subtitle generation** — ASS/SRT from Edge TTS cues (~1-2s)
5. **Material download** — Pixabay API + download (~20-60s)
6. **Image preprocessing** — Ken Burns effect per image (~3-8s per image)
   - If parallax enabled: rembg background removal (~5-15s per image)
7. **Video combining** — FFmpeg concat + transitions (~30-120s)
8. **Final video generation** — MoviePy write + FFmpeg ASS overlay (~60-180s)

**Total typical time: 3-8 minutes for a 60-second video**

### Current Bottlenecks

1. **rembg (parallax)** — ~5-15s per image for CPU-based background removal. This is the #1 bottleneck when parallax is enabled.
2. **MoviePy write_videofile** — Re-encodes each clip individually before FFmpeg concat. Each clip is encoded twice (once per clip, once for final).
3. **FFmpeg ASS overlay** — Final pass re-encodes the entire video with subtitle overlay.
4. **Image processing** — Ken Burns creates PIL Image objects per frame, which is slow.

### Performance Questions

1. **How to speed up rembg on CPU?** We have NO CUDA GPU. Current options:
   - `onnxruntime` (CPU) — what we use now
   - `onnxruntime-gpu` — won't work without CUDA
   - Is there a lighter alternative to rembg for simple foreground/background separation?
   - Can we cache the rembg result and reuse it across clips?
   - What rembg model is fastest? (u2net, u2netp, etc.)

2. **How to reduce FFmpeg encoding passes?** Currently:
   - Each clip is written to a temp file (encoding pass 1)
   - All clips are concatenated (encoding pass 2)
   - ASS subtitles are overlaid (encoding pass 3)
   Can we combine any of these?

3. **How to speed up Ken Burns / image-to-video?** Current approach:
   - Load image into PIL
   - For each frame (30fps × duration): crop, resize with LANCZOS
   - Write to temp file
   Is there a faster way? Can we use FFmpeg's zoompan filter directly?

4. **FFmpeg optimization flags** — What flags should we use for faster encoding?
   - `-preset ultrafast` vs `-preset medium`?
   - `-crf` value tradeoffs?
   - Hardware encoding options for Intel UHD? (Quick Sync / VAAPI)
   - Can we use `-c:v copy` somewhere to avoid re-encoding?

5. **Parallel processing** — We have 4 threads (2 cores × 2 hyperthreads). How can we parallelize:
   - Multiple image preprocessing tasks
   - Multiple clip encoding tasks
   - Multiple video generation tasks

6. **Memory management** — With 12GB RAM, what's the best strategy?
   - How many clips can we process in parallel before OOM?
   - Should we stream-process instead of loading everything into memory?

7. **rembg model optimization** — Is there a way to:
   - Use a smaller/faster model?
   - Reduce image resolution before rembg processing?
   - Use ONNX optimization flags?

8. **Intel UHD Graphics G4** — Can we use it for anything?
   - VAAPI hardware encoding?
   - OpenCL acceleration?
   - Any FFmpeg filters that can use Intel iGPU?

9. **Caching strategies** — What can we cache?
   - rembg results (same image used in multiple clips?)
   - Ken Burns frames?
   - Intermediate video files?

10. **Alternative approaches** — Instead of MoviePy + FFmpeg, would any of these be faster?
    - Pure FFmpeg pipeline (no Python video processing)
    - GStreamer
    - Direct libav bindings

### Target

**We want to generate a 60-second video in under 2 minutes** on this hardware. Currently it takes 3-8 minutes. What's the most impactful optimization we can make?
