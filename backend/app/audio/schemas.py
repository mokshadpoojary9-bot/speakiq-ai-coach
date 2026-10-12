"""Response contract for audio feature extraction. All times are in seconds."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

# measured: computed directly from the signal.
# estimated: computed from the signal through a heuristic whose error is not bounded here.
# unavailable: not computed; `limitations` says why. Values are then null or empty.
MetricStatus = Literal["measured", "estimated", "unavailable"]


class Interval(BaseModel):
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _end_after_start(self) -> "Interval":
        if self.end <= self.start:
            raise ValueError("interval end must be greater than start")
        return self


class Metric(BaseModel):
    status: MetricStatus
    method: str
    limitations: list[str] = []


class FrameSeries(BaseModel):
    """Evenly spaced values; value i is at `start_sec + i * hop_sec`. Null means no value at that frame."""

    unit: str
    start_sec: float
    hop_sec: float
    values: list[float | None]


class AudioInfo(BaseModel):
    filename: str
    duration_sec: float
    sample_rate_hz: int
    channels: int
    analysis_sample_rate_hz: int
    peak_amplitude: float = Field(description="Largest absolute sample value, 0 to 1 full scale.")


class FrameConfig(BaseModel):
    frame_length_sec: float
    hop_sec: float
    n_fft: int
    window: str


class Waveform(Metric):
    bucket_sec: float
    peaks: list[float] = Field(description="Largest absolute amplitude per bucket, 0 to 1 full scale.")


class Energy(Metric):
    series: FrameSeries | None = None
    mean_db: float | None = None
    max_db: float | None = None
    noise_floor_db: float | None = Field(default=None, description="10th percentile of frame energy.")


class Spectral(Metric):
    centroid: FrameSeries | None = None
    mean_centroid_hz: float | None = None
    mean_bandwidth_hz: float | None = None
    mean_rolloff_hz: float | None = None
    mean_flatness: float | None = None
    mean_zero_crossing_rate: float | None = None


class Mfcc(Metric):
    n_mfcc: int
    mean: list[float] = []
    std: list[float] = []


class Pitch(Metric):
    series: FrameSeries | None = None
    voiced_fraction: float | None = None
    median_hz: float | None = None
    mean_hz: float | None = None
    min_hz: float | None = None
    max_hz: float | None = None
    range_semitones: float | None = Field(default=None, description="5th to 95th percentile of voiced F0.")


class PauseInterval(Interval):
    position: Literal["leading", "internal", "trailing"]


class Pauses(Metric):
    threshold_db: float | None = None
    min_pause_sec: float
    intervals: list[PauseInterval] = []
    internal_pause_count: int | None = None
    total_internal_pause_sec: float | None = None
    speech_sec: float | None = Field(default=None, description="Duration minus every detected silence.")


class SpeakingRate(Metric):
    syllable_nuclei: int | None = None
    syllable_times_sec: list[float] = []
    speech_rate_syll_per_sec: float | None = Field(default=None, description="Nuclei divided by total duration.")
    articulation_rate_syll_per_sec: float | None = Field(default=None, description="Nuclei divided by speech time.")


class TranscriptRate(Metric):
    word_count: int | None = None
    words_per_minute: float | None = None


class AudioFeatures(BaseModel):
    is_demo: Literal[False] = False
    audio: AudioInfo
    frames: FrameConfig
    waveform: Waveform
    energy: Energy
    spectral: Spectral
    mfcc: Mfcc
    pitch: Pitch
    pauses: Pauses
    speaking_rate: SpeakingRate
    transcript_rate: TranscriptRate
    limitations: list[str]
