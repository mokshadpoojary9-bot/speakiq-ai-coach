# Publishing the SpeakIQ Contrastive Speech Dataset

**Status: not published.** The dataset has not been uploaded to any host. This guide describes how to export it and upload it yourself. Update the status line above, and the "Rebuilding and hosting" section of `DATASET_CARD.md`, only after an upload has actually succeeded.

## What is safe to publish

The export contains only:

- the three LibriVox source clips (public domain, distributed in LibriSpeech under CC BY 4.0),
- the 84 transformed variants and 3 references built from them (the filler variants contain synthetic filler sounds),
- the manifest, the JSON Schema, the source registry and the dataset card.

It never includes anything from `backend/.env`, recordings uploaded through the app (those are not stored), or any file outside `data/`. Do not add your own or anyone else's recordings to the export unless you have their permission and have recorded the licence in `sources/sources.json`.

The licence statement in the dataset card is the project's reading of the upstream terms. Confirm it yourself before publishing.

## 1. Build, check and export

From `backend/`, with the virtual environment active:

```powershell
python -m app.dataset build      # regenerates data/speakiq-contrastive-v1/audio (about 19 MB)
python -m app.dataset check      # validates, and confirms a rebuild matches the committed manifest
python -m app.dataset export     # writes data/export/
```

`export` refuses to run unless the built dataset passes validation with every audio file present and matching its checksum. It produces, under `data/export/` (ignored by Git):

```
speakiq-contrastive-<version>/
  README.md            the dataset card with the metadata block Hugging Face expects
  manifest.json
  audio/...            87 FLAC files
  sources/...          3 source OGG files and sources.json
  schema/dataset.schema.json
  SHA256SUMS.txt       checksum of every file above
speakiq-contrastive-<version>.zip
```

The archive is byte-for-byte repeatable: exporting the same build twice gives an identical zip.

## 2a. Upload to the Hugging Face Hub (recommended)

The Hub is designed for datasets, shows the card as the landing page and can play the audio.

1. Create a free account at https://huggingface.co and a **write** access token under Settings → Access Tokens.
2. Install the client and sign in. The token is typed into the prompt and stored by the tool in your user profile, outside this repository:

   ```powershell
   pip install -U huggingface_hub
   hf auth login
   ```

   Do not put this token in `backend/.env`, in any file in this repository, or in a chat. It is a different token from the optional read-only `HF_TOKEN` the backend can use.
3. Create the dataset repository and upload the exported folder. Replace `YOUR_USERNAME`:

   ```powershell
   hf repos create YOUR_USERNAME/speakiq-contrastive --repo-type dataset
   hf upload YOUR_USERNAME/speakiq-contrastive ..\data\export\speakiq-contrastive-1.1.0 . --repo-type dataset
   ```

   These are the commands of `huggingface_hub` 2.x. Older versions use `hf repo create`, or `huggingface-cli` in place of `hf`.
4. Open `https://huggingface.co/datasets/YOUR_USERNAME/speakiq-contrastive` and confirm the card renders and a few audio files play.

## 2b. Or attach it to a GitHub Release

1. On GitHub, open the repository → Releases → "Draft a new release".
2. Create a tag such as `dataset-v1.1.0`, and attach `data/export/speakiq-contrastive-1.1.0.zip`.
3. In the description, paste the Summary and Limitations sections of the dataset card, then publish.

## 3. After a successful upload

- Verify a fresh download: unzip or clone it, then from `backend/` run `python -m app.dataset validate PATH_TO_DOWNLOADED_FOLDER`. It should report 0 errors.
- Record the public URL and the date in `DATASET_CARD.md` and change the status line at the top of this file.
- Commit those documentation changes.

## Downloading (for users, once published)

```powershell
hf download YOUR_USERNAME/speakiq-contrastive --repo-type dataset --local-dir speakiq-contrastive
python -m app.dataset validate speakiq-contrastive
```

Or download and unzip the release archive, then run the same `validate` command on the unzipped folder. Either way, `SHA256SUMS.txt` lists the expected checksum of every file.
