from ._windows_runtime import preload_msvc_runtime

# Must happen before numpy, librosa, parselmouth or ctranslate2 are imported.
preload_msvc_runtime()

__version__ = "0.1.0"
