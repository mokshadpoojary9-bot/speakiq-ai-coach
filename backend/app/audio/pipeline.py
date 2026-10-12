"""Runs every feature extractor over one recording."""

import numpy as np

from . import features, timing
from .loading import LoadedAudio
from .pitch import pitch, track_pitch
from .schemas import AudioFeatures, AudioInfo, FrameConfig


def extract_features(audio: LoadedAudio, transcript: str | None = None) -> AudioFeatures:
    samples, sample_rate, duration = audio.samples, audio.sample_rate, audio.duration_sec

    frames = features.compute_frames(samples, sample_rate)
    track = track_pitch(samples, sample_rate)
    pause_result = timing.pauses(frames, duration)

    return AudioFeatures(
        audio=AudioInfo(
            filename=audio.filename,
            duration_sec=round(duration, 3),
            sample_rate_hz=audio.original_sample_rate,
            channels=audio.channels,
            analysis_sample_rate_hz=sample_rate,
            peak_amplitude=round(float(np.abs(samples).max()), 4),
        ),
        frames=FrameConfig(
            frame_length_sec=features.FRAME_LENGTH_SEC,
            hop_sec=features.HOP_SEC,
            n_fft=features.N_FFT,
            window=features.WINDOW,
        ),
        waveform=features.waveform(samples, sample_rate),
        energy=features.energy(frames),
        spectral=features.spectral(samples, frames),
        mfcc=features.mfcc(samples, frames),
        pitch=pitch(track),
        pauses=pause_result,
        speaking_rate=timing.speaking_rate(frames, track, pause_result, duration),
        transcript_rate=timing.transcript_rate(transcript, duration),
        limitations=[
            "These are acoustic measurements of one recording. No comparison with a baseline and no flaw detection is performed yet.",
            "Multi-channel audio is averaged to mono and resampled before analysis.",
            "Acoustic features are not tied to individual words here; word timing comes from the separate transcription and alignment steps.",
        ],
    )
