# Expert Consultation: Automatic Subtitle Sync (No Manual Offset)

## Problem

We implemented a +80ms `GLOBAL_OFFSET` to compensate for MP3/AAC encoder delay, but it doesn't work consistently. Subtitles sync well at the beginning but drift out of sync towards the end of the video. The offset value that works for one voice/script length doesn't work for another.

**We need the sync to be fully automatic — no manual tuning per video.**

## Current Pipeline

```
1. Edge TTS 7.x → audio.mp3 + SentenceBoundary cues (NO WordBoundary)
2. SentenceBoundary gives: text, offset (start in 100ns units), duration (in 100ns units)
3. Words within each sentence are distributed PROPORTIONALLY by character count
4. ASS generated with proportional word timings + GLOBAL_OFFSET
5. FFmpeg burns ASS into video
```

## What We Know

- Edge TTS 7.x `SubMaker.cues` only returns `SentenceBoundary` events, NOT `WordBoundary`
- The `offset` field in SentenceBoundary is in 100-nanosecond units (1 tick = 0.0000001 seconds)
- Audio is MP3, then re-encoded to AAC in final MP4
- The audio delay is NOT constant — it varies based on:
  - MP3 encoder buffering (varies with content)
  - AAC re-encoding delay
  - Container format overhead
  - Player behavior (edit list vs raw timestamps)

## Questions

1. **Can we measure the actual audio delay empirically?** For example:
   - Generate audio with a known silent lead-in (e.g., 1 second of silence)
   - Measure the difference between expected speech start and actual audio start
   - Use this as the offset

2. **Can we detect the audio delay from the MP3 file itself?**
   - MP3 files have a `encoder delay` tag (LAME header)
   - FFmpeg can read this: `ffprobe -show_entries stream.codec_delay`
   - Can we extract this and use it as the offset?

3. **Can we use FFmpeg's `-af "adelay"` filter** to delay the audio to match subtitles instead of delaying subtitles to match audio? This might be more reliable.

4. **Can we use FFmpeg's `-itsoffset` flag** to shift the audio track relative to the video track?

5. **Can we add a silent preamble to the Edge TTS audio** (e.g., 500ms of silence) so that the first subtitle always appears after the audio buffer is primed? This would eliminate the cold-start delay.

6. **Is there a way to detect word-level timing from the MP3 waveform?** For example:
   - Use a simple energy-based voice activity detector
   - Detect when each word starts based on amplitude spikes
   - Match these to our proportional word boundaries

7. **Can we use `espeak-ng` or another local tool** to get word-level timing as a reference, then align Edge TTS audio to it?

8. **FFmpeg's `silencedetect` or `ebur128` filters** — can these help us detect when speech actually starts in the audio file?

## Hardware Context

- Intel i3-1115G4 (2C/4T), 12GB RAM, Linux
- FFmpeg n8.1 with libass, libx264, fontconfig
- Python 3.11.11
- edge-tts 7.2.7 (only SentenceBoundary, no WordBoundary)

## What We Need

**Automatic sync** — subtitles should appear exactly when the word is spoken, without any manual offset tuning. The solution should work for any voice, any script length, any language.
