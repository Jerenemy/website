from __future__ import annotations

import gc
import glob
import logging
import os
from pathlib import Path
from typing import Dict, List

import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
import torchvision as tvm
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename


class EarEngineError(Exception):
    """Base exception for ear engine failures."""


class EarDatasetEmpty(EarEngineError):
    """Raised when the dataset is missing or empty."""


class AudioEncoder(nn.Module):
    def __init__(self, model, sample_rate, embed_dim):
        super().__init__()
        self.model = model
        self.sample_rate = sample_rate
        self.embed_dim = embed_dim

    def forward(self, wav, sr):
        if isinstance(sr, torch.Tensor):
            sr = sr.item()
        if sr != self.sample_rate:
            wav = torchaudio.functional.resample(wav, sr, self.sample_rate)
        if wav.dim() == 1:
            wav = wav.unsqueeze(0)

        with torch.no_grad():
            feats, _ = self.model.extract_features(wav)
            x = feats[-1].mean(dim=1)
        return x


class ProjectionHead(nn.Module):
    def __init__(self, in_dim, embed_dim):
        super().__init__()
        self.proj = nn.Linear(in_dim, embed_dim)

    def forward(self, x):
        return F.normalize(self.proj(x), dim=-1)


class AudioVisualCLIP(nn.Module):
    def __init__(self, image_encoder, audio_encoder, img_dim=2048, audio_dim=768, embed_dim=512):
        super().__init__()
        self.image_encoder = image_encoder
        self.audio_encoder = audio_encoder
        self.image_proj = ProjectionHead(img_dim, embed_dim)
        self.audio_proj = ProjectionHead(audio_dim, embed_dim)
        self.logit_scale = nn.Parameter(torch.tensor((1 / 0.07)).log())

    def encode_image(self, images):
        with torch.no_grad():
            feats = self.image_encoder(images)
        return self.image_proj(feats)

    def encode_audio(self, audio, sr):
        audio_feats = self.audio_encoder(audio, sr)
        return self.audio_proj(audio_feats)


class EarEngine:
    """
    Thin wrapper around the ear retrieval demo code so it can be used as a Flask blueprint.
    Loads the CLIP-like model, indexes the dataset, and serves queries.
    """

    def __init__(self, base_dir: Path | str, data_url_prefix: str = "/ear/data", max_audio_sec: int = 10):
        self.logger = logging.getLogger(__name__)
        self.base_dir = Path(base_dir).resolve()
        self.dataset_root = self.base_dir / "dataset"
        self.upload_folder = self.base_dir / "uploads"
        self.model_path = self.base_dir / "pretrained_models" / "best_audio_visual_clip.pt"
        self.cache_path = self.base_dir / "indexed_db.pt"
        self.data_url_prefix = data_url_prefix.rstrip("/")
        self.max_audio_sec = max_audio_sec

        self.upload_folder.mkdir(parents=True, exist_ok=True)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger.info("Ear engine using device: %s", self.device)

        self.model, self.img_transforms = self._build_model()
        self.db_metadata: List[Dict] = []
        self.db_tensor: torch.Tensor | None = None
        self._index_dataset()

    def _apply_data_prefix(self, metadata: List[Dict]) -> List[Dict]:
        """Ensure cached metadata uses the current data URL prefix."""
        updated = []
        for item in metadata:
            if not isinstance(item, dict):
                continue
            url = item.get("url", "")
            rel = ""
            if "/data/" in url:
                rel = url.split("/data/", 1)[1]
            elif url.startswith("/"):
                rel = url.lstrip("/")
            if rel:
                copy = dict(item)
                copy["url"] = f"{self.data_url_prefix}/{rel}"
                updated.append(copy)
            else:
                updated.append(item)
        return updated

    def _build_model(self):
        self.logger.info("Initializing audio-visual model...")
        resnet_weights = tvm.models.ResNet50_Weights.IMAGENET1K_V2
        resnet = tvm.models.resnet50(weights=resnet_weights).eval()
        image_encoder = torch.nn.Sequential(*(list(resnet.children())[:-1]), torch.nn.Flatten(1))
        img_transforms = resnet_weights.transforms()

        bundle = torchaudio.pipelines.WAV2VEC2_BASE
        w2v = bundle.get_model().eval()
        with torch.no_grad():
            dummy = torch.zeros(1, bundle.sample_rate)
            feats, _ = w2v.extract_features(dummy)
            audio_dim = feats[-1].shape[-1]
        audio_encoder = AudioEncoder(w2v, bundle.sample_rate, audio_dim)

        model = AudioVisualCLIP(image_encoder, audio_encoder, audio_dim=audio_dim, embed_dim=512)
        model.to(self.device)

        if not self.model_path.exists():
            raise EarEngineError(f"Model file not found at {self.model_path}")

        self.logger.info("Loading weights from %s", self.model_path)
        state_dict = torch.load(self.model_path, map_location=self.device)
        model.load_state_dict(state_dict)
        model.eval()
        return model, img_transforms

    def _index_dataset(self):
        """
        Index audio/image embeddings. Tries cache first, then rebuilds from dataset folder.
        """
        if self.cache_path.exists():
            self.logger.info("Found cached database at %s", self.cache_path)
            try:
                cache_data = torch.load(self.cache_path, map_location=self.device)
                self.db_metadata = self._apply_data_prefix(cache_data["metadata"])
                tensor = cache_data["tensor"]
                self.db_tensor = tensor.to(self.device) if hasattr(tensor, "to") else tensor
                self.logger.info("Loaded %s indexed items from cache", len(self.db_metadata))
                return
            except Exception:
                self.logger.exception("Cached index could not be loaded, rebuilding...")

        self.logger.info("Indexing dataset at %s", self.dataset_root)
        embeddings = []
        metadata = []

        audio_files = glob.glob(os.path.join(self.dataset_root, "audio", "**", "*.wav"), recursive=True)
        for i, fpath in enumerate(audio_files):
            try:
                wav, sr = torchaudio.load(fpath)
                max_frames = int(sr * self.max_audio_sec)
                if wav.shape[1] > max_frames:
                    wav = wav[:, :max_frames]
                if wav.shape[0] > 1:
                    wav = wav.mean(dim=0, keepdim=True)
                wav = wav.to(self.device)

                emb = self.model.encode_audio(wav, sr).detach().cpu()

                rel_path = os.path.relpath(fpath, self.dataset_root).replace("\\", "/")
                metadata.append(
                    {
                        "type": "audio",
                        "url": f"{self.data_url_prefix}/{rel_path}",
                        "label": rel_path.split("/")[1] if "/" in rel_path else rel_path,
                    }
                )
                embeddings.append(emb)

                if i % 50 == 0:
                    gc.collect()
            except Exception:
                self.logger.exception("Skipping audio file %s", fpath)

        image_files = glob.glob(os.path.join(self.dataset_root, "frames", "**", "*.jpg"), recursive=True)
        for i, fpath in enumerate(image_files):
            try:
                img = Image.open(fpath).convert("RGB")
                tensor = self.img_transforms(img).unsqueeze(0).to(self.device)
                emb = self.model.encode_image(tensor).detach().cpu()

                rel_path = os.path.relpath(fpath, self.dataset_root).replace("\\", "/")
                metadata.append(
                    {
                        "type": "image",
                        "url": f"{self.data_url_prefix}/{rel_path}",
                        "label": rel_path.split("/")[1] if "/" in rel_path else rel_path,
                    }
                )
                embeddings.append(emb)

                if i % 50 == 0:
                    gc.collect()
            except Exception:
                self.logger.exception("Skipping image file %s", fpath)

        if not embeddings:
            self.db_metadata = []
            self.db_tensor = None
            raise EarDatasetEmpty("No files found under dataset/audio or dataset/frames")

        self.db_metadata = self._apply_data_prefix(metadata)
        self.db_tensor = torch.cat(embeddings, dim=0).to(self.device)
        self.logger.info("Indexed %s items", len(self.db_metadata))

        self.logger.info("Saving cache to %s", self.cache_path)
        try:
            torch.save({"metadata": self.db_metadata, "tensor": self.db_tensor.cpu()}, self.cache_path)
        except Exception:
            self.logger.exception("Failed to write cache to %s", self.cache_path)

    def query(self, file: FileStorage) -> Dict:
        if file.filename == "":
            raise ValueError("No file provided")
        if self.db_tensor is None or len(self.db_metadata) == 0:
            raise EarDatasetEmpty("Dataset index is empty")

        filename = secure_filename(file.filename)
        filepath = self.upload_folder / filename
        file.save(filepath)

        try:
            return self._handle_query(filepath)
        finally:
            try:
                filepath.unlink()
            except FileNotFoundError:
                pass

    def _handle_query(self, filepath: Path) -> Dict:
        filename = filepath.name.lower()
        query_emb = None
        query_type = ""

        if filename.endswith((".jpg", ".jpeg", ".png")):
            query_type = "image"
            img = Image.open(filepath).convert("RGB")
            tensor = self.img_transforms(img).unsqueeze(0).to(self.device)
            query_emb = self.model.encode_image(tensor)
        elif filename.endswith((".wav", ".mp3", ".webm", ".mp4", ".m4a")):
            query_type = "audio"
            wav, sr = torchaudio.load(filepath)
            max_frames = int(sr * self.max_audio_sec)
            if wav.shape[1] > max_frames:
                wav = wav[:, :max_frames]
            if wav.shape[0] > 1:
                wav = wav.mean(dim=0, keepdim=True)
            wav = wav.to(self.device)
            query_emb = self.model.encode_audio(wav, sr)
        else:
            raise ValueError("Unsupported file type")

        similarities = (query_emb @ self.db_tensor.T).squeeze(0)
        topk_scores, topk_indices = torch.topk(similarities, min(100, len(self.db_metadata)))

        same_modality_results = []
        cross_modality_results = []

        for score, idx in zip(topk_scores, topk_indices):
            item = self.db_metadata[idx.item()]
            result_obj = {
                "type": item["type"],
                "url": item["url"],
                "label": item["label"],
                "score": round(score.item(), 3),
            }

            if item["type"] == query_type:
                if len(same_modality_results) < 5:
                    same_modality_results.append(result_obj)
            else:
                if len(cross_modality_results) < 5:
                    cross_modality_results.append(result_obj)

            if len(same_modality_results) >= 5 and len(cross_modality_results) >= 5:
                break

        return {
            "query_type": query_type,
            "same_modality": same_modality_results,
            "cross_modality": cross_modality_results,
        }
