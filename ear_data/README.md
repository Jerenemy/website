# Ear demo storage

This folder holds the data and artifacts used by the `/ear` retrieval demo. Nothing in here is checked into git (see `.gitignore`)—it’s runtime/storage only.

Expected contents:
- `dataset/` — your media corpus (`audio/**.wav`, `frames/**.jpg`).
- `pretrained_models/best_audio_visual_clip.pt` — projection weights.
- `indexed_db.pt` — cached embeddings (written after first index).
- `uploads/` — transient uploads saved during queries.

If you relocate this folder, set `EAR_BASE_DIR=/absolute/path/to/ear_data` in your environment or supervisor config so the app can find it.
