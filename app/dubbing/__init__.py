"""Automated dubbing: TTS voice generation + audio/video muxing.

Entirely optional — requires edge-tts (see requirements-tts.txt) and
ffmpeg. Any failure falls back gracefully; the .vi.srt subtitle is
always the primary deliverable regardless of whether dubbing succeeds.
"""
