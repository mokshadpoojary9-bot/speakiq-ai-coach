# SpeakIQ Contrastive Speech Dataset — dataset card

Version 1.0.0 · schema 1.0.0 · built by `python -m app.dataset build` (seed 20261013)

## Summary

A small demonstration dataset of **paired speech deliveries**: an unaltered reference recording and deliberately flawed versions of that same recording, with the altered time intervals recorded exactly.

Every flawed sample is a **signal-processing transform of a real human recording**. No sample is synthetic speech, and no flawed sample is a natural human performance of that flaw. This is the single most important thing to know before using it.

| | |
| --- | --- |
| Source recordings | 3 (3 different speakers, 1 recording each) |
| Samples | 75: 3 references + 72 transformed |
| Flaw categories covered | 6 of the 7 defined |
| Severity levels per category | 4 (`near_reference`, `mild`, `moderate`, `severe`) |
| Total audio | 1183.9 s (about 19.7 minutes); samples run from 9.0 s to 25.1 s |
| Audio format | FLAC, 16-bit, mono, 16 kHz |
| Language | English |
| Manual annotations | None |

These figures are read from `speakiq-contrastive-v1/manifest.json`, which the build writes. A test checks that the sample count matches the build recipe.

## Files

```
data/
  DATASET_CARD.md                    this file
  schema/dataset.schema.json         JSON Schema for manifests (generated from backend/app/dataset/schema.py)
  sources/                           the 3 source recordings (OGG) and sources.json (provenance, licence, checksums)
  examples/                          7 audio files + manifest: one speaker, reference and the 'severe' sample per category
  speakiq-contrastive-v1/
    manifest.json                    full metadata for all 75 samples, including checksums
    audio/                           NOT in Git (about 19 MB); created by the build command
```

## Provenance

All audio derives from three utterances of the LibriSpeech corpus, which are recordings made by LibriVox volunteers reading public-domain books. They were obtained as the example files shipped by the librosa project.

| Source ID | LibriSpeech speaker | Description (as given by librosa) | Duration |
| --- | --- | --- | --- |
| `librispeech-5703-47212-0000` | 5703 | The Ashiel Mystery: A Detective Story, chapter XVI. Read by Garth Comira | 14.8 s |
| `librispeech-3436-172162-0000` | 3436 | The Age of Chivalry, chapter IX: The Adventure of the Cart. Read by Anders Lankford | 16.7 s |
| `librispeech-198-209-0000` | 198 | Sense and Sensibility, Chapter 18, Jane Austen. Read by Heather Barnett | 13.9 s |

The description of the third file comes from librosa's metadata. Its recognised words suggest a different Jane Austen novel; nobody has checked this against the audio.

Each source's download URL and SHA-256 are in `sources/sources.json`. The build refuses to run if a source file does not match its checksum.

## Licensing

- **Source audio:** LibriVox recordings are in the public domain. The LibriSpeech corpus that distributes them is licensed CC BY 4.0 (Panayotov, Chen, Povey and Khudanpur, 2015).
- **Derived audio and metadata in this dataset:** offered under CC BY 4.0, with attribution to LibriVox, LibriSpeech and librosa as above.
- No private recordings, and no recordings of the project owner or any user, are included.

This is our reading of the upstream terms, not legal advice. Confirm it before redistributing the dataset outside this project.

## Generation

The reference sample is the source file converted to 16 kHz mono FLAC, otherwise unaltered. Each flawed sample applies one transform to that reference:

| Flaw category | Transform | Severity parameter (near_reference → severe) | Labelled interval |
| --- | --- | --- | --- |
| `excessive_pauses` | Digital silence inserted at the quietest moments | 1×0.35 s, 1×0.7 s, 2×1.1 s, 3×1.8 s | Each inserted silence, exact |
| `rushed_delivery` | Whole clip time-compressed, pitch kept (Praat overlap-add) | 0.95×, 0.87×, 0.77×, 0.65× duration | Whole clip |
| `slow_delivery` | Whole clip time-stretched, pitch kept | 1.05×, 1.15×, 1.3×, 1.5× duration | Whole clip |
| `uneven_pacing` | Four stretches alternately sped up and slowed down | contrast 1.08, 1.2, 1.35, 1.5 | Each fast and slow stretch, exact |
| `pitch_monotony` | Pitch movement scaled toward the speaker's median | 85%, 60%, 35%, 10% of original movement | Whole clip |
| `unclear_articulation` | Low-pass filter (**proxy label**) | cut-off 5000, 3000, 1800, 1000 Hz | Whole clip |
| `filler_words` | **Not covered** | — | — |

`filler_words` is defined in the schema but has no samples: fillers such as "um" cannot be produced by transforming a recording that does not contain them, and no licensed recordings with fillers or licensed speech synthesis were available.

The build is deterministic. Praat's resynthesis draws random numbers for unvoiced sound, so its generator is re-seeded before every call. Two consecutive builds on the development machine produced byte-identical audio and manifests. Identical output on other platforms or library versions has not been tested; compare against the checksums in the manifest.

## Annotation

There are three kinds of information in the manifest, kept separate:

1. **Labels by construction** (`annotation.label_provenance: generated_by_construction`). The flaw category, severity and intervals are known because the build applied exactly that change. All 75 samples are labelled this way.
2. **Manual labels.** There are none. Nobody has listened to these samples and rated them. The schema supports `manual` labels and requires an annotator name for them.
3. **Automatic estimates** (`measured`, `provenance: automatic_estimate`). Pitch range, detected silence, a syllable-rate estimate and spectral centroid from the SpeakIQ audio pipeline. These are not labels and were never used to set a label.

**Severity is a parameter tier, not a perceptual rating.** `severe` means the strongest transform setting, not that a listener judged it severely flawed. Whether `near_reference` samples are perceptibly different from the reference is unknown.

**Label support.** `annotation.label_support` is `by_construction` where the transform directly creates the labelled property, and `proxy` for `unclear_articulation`, where filtering only imitates one acoustic consequence of mumbling.

**Support checks.** For each flawed sample the build compares one independent measurement with what the label implies (for example, detected silence should rise when pauses are inserted). In the current build, 60 of 72 flawed samples have a check and all 60 pass. The 12 `uneven_pacing` samples have no automatic check, recorded as `supported: null`. A passing check shows the measurement moved in the expected direction; it does not show a listener would hear the flaw.

**Transcripts** are unedited output of faster-whisper (`base` model), marked `automatic_asr_unverified`. They contain visible recognition errors (for example "nights of the table-round"). Every sample in a pair shares its reference's transcript, because none of the transforms changes the words.

## Splits

Whole speakers are assigned to splits by a seeded shuffle, so no speaker or recording appears in two splits:

| Split | Speaker | Samples |
| --- | --- | --- |
| train | 5703 | 25 |
| validation | 3436 | 25 |
| test | 198 | 25 |

With one speaker per split, these splits demonstrate leakage-free splitting. They are far too small to train or meaningfully evaluate a model.

## Validation

`python -m app.dataset validate DIR` checks: schema and required metadata; duplicate sample, pair, source and path identifiers; labels (allowed values, reference versus flawed consistency, severity rank, categories actually covered, real versus synthetic origin); timestamps (non-negative, end after start, within the audio); transcripts (must match the pair unless a documented difference is declared); pair integrity; speaker and recording leakage across splits; and, unless `--metadata-only` is given, that each audio file exists, matches its checksum, decodes, and has the stated sample rate and duration.

Current results: the full build and the example set each validate with 0 errors and 0 warnings.

## Limitations

- **Transformed, not natural.** Time-stretched speech is not how a person sounds when rushing; real rushed speech also changes articulation, pausing and pitch. Models trained on this may learn the transform's artefacts instead of the flaw.
- **Each sample has exactly one flaw type.** Real deliveries combine several.
- **Transforms leave artefacts** such as resynthesis noise and abrupt joins between stretches. They have not been listened to or rated.
- **The automatic estimates are rough.** The pitch-range estimate in particular is unstable: for speaker 5703, whose median pitch (about 83 Hz) is close to the tracker's 75 Hz floor, samples whose transform should leave pitch alone show measured ranges of up to 31 semitones against 8.2 for the reference, and the reference of speaker 198 measures 21.5 semitones. These look like octave-tracking errors. Do not treat `measured` values as ground truth.
- **`unclear_articulation` is a proxy** and should not be used as ground truth for articulation.
- **Inserted pauses are digital silence**, which sounds unlike a real pause with room tone, and are placed at quiet moments rather than at linguistically meaningful points.
- **Tiny.** Three recordings of about 15 seconds each. No statistical conclusion can be drawn from it.
- **Transcripts are unverified** machine output.
- **The reference is "unaltered", not "good".** Nobody has rated the source readings as model deliveries.
- **No fillers**, and no word-level alignment is stored.

## Biases

- Three speakers, all reading English literary prose for LibriVox. Their demographics are not recorded here and were not inferred.
- Read speech only: no spontaneous, conversational or presentation speech.
- One language, one recording style, clean audio. Nothing here represents accented, disfluent, noisy or non-native speech, so results on this data say nothing about fairness across speaker groups.

## Intended use

Intended: developing and testing the SpeakIQ analysis pipeline, checking that detected intervals line up with known altered intervals, demonstrating the dataset schema and validation, and as fixtures for automated tests.

Not intended: training or benchmarking models for real-world use, judging any person's speaking ability, or any claim about how well a system detects natural delivery flaws.

## Rebuilding and hosting

From `backend/`, with the virtual environment active:

```powershell
python -m app.dataset build              # writes data/speakiq-contrastive-v1/ (manifest + about 19 MB of audio)
python -m app.dataset validate ..\data\speakiq-contrastive-v1
python -m app.dataset build-examples     # rewrites data/examples/
python -m app.dataset export-schema      # rewrites data/schema/dataset.schema.json
```

The full audio is kept out of Git and regenerated by the build, which needs no network access because the three small source files are committed.

**The built dataset is not currently hosted anywhere.** To publish it, zip `data/speakiq-contrastive-v1/` after a build and attach it to a GitHub Release of this repository, or upload it as a Hugging Face dataset repository. Whoever downloads it should run the validate command, which verifies every file against the checksums in the manifest.
