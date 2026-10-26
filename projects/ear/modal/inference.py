"""EAR inference: embeds an uploaded image or sound and searches the index.

The encoders are stock ResNet-50 (ImageNet V2) and wav2vec2-base, frozen during training, so
only the projection heads (heads.pt, cut from best_audio_visual_clip.pt) are EAR's own weights. jeremyzay.com/ear/ renders the
page and serves the media; it forwards /query here and returns this JSON as it is. Requests
must carry the shared key in X-Ear-Key (EAR_KEY), so the endpoint can't run up the bill.
"""
import os
import subprocess
import tempfile

import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchaudio
import torchvision as tvm
from flask import Flask, jsonify, request
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # /root in the Modal container
MAX_AUDIO_SEC = 10
torch.set_num_threads(2)


class ProjectionHead(nn.Module):
    def __init__(self, in_dim, embed_dim):
        super().__init__()
        self.proj = nn.Linear(in_dim, embed_dim)

    def forward(self, x):
        return F.normalize(self.proj(x), dim=-1)


resnet_weights = tvm.models.ResNet50_Weights.IMAGENET1K_V2
resnet = tvm.models.resnet50(weights=resnet_weights).eval()
image_encoder = nn.Sequential(*(list(resnet.children())[:-1]), nn.Flatten(1)).eval()
img_transforms = resnet_weights.transforms()

bundle = torchaudio.pipelines.WAV2VEC2_BASE
w2v = bundle.get_model().eval()

heads = torch.load(os.path.join(BASE_DIR, "heads.pt"), map_location="cpu", weights_only=True)
image_proj = ProjectionHead(2048, 512)
audio_proj = ProjectionHead(768, 512)
image_proj.load_state_dict({"proj.weight": heads["image_proj.proj.weight"], "proj.bias": heads["image_proj.proj.bias"]})
audio_proj.load_state_dict({"proj.weight": heads["audio_proj.proj.weight"], "proj.bias": heads["audio_proj.proj.bias"]})
image_proj.eval()
audio_proj.eval()

index = torch.load(os.path.join(BASE_DIR, "indexed_db.pt"), map_location="cpu")
DB_METADATA = index["metadata"]
DB_TENSOR = index["tensor"]


@torch.no_grad()
def embed_image(path):
    x = img_transforms(Image.open(path).convert("RGB")).unsqueeze(0)
    return image_proj(image_encoder(x))


@torch.no_grad()
def embed_audio(path):
    # ffmpeg normalizes any upload (webm from the recorder included) to 16 kHz mono
    wav_path = path + ".converted.wav"
    subprocess.run(
        ["ffmpeg", "-i", path, "-ar", str(bundle.sample_rate), "-ac", "1", "-y", wav_path],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        data, sr = sf.read(wav_path, dtype="float32")
    finally:
        os.remove(wav_path)
    wav = torch.from_numpy(data).float()
    wav = wav.unsqueeze(0) if wav.ndim == 1 else wav.t()
    wav = wav[:, : int(sr * MAX_AUDIO_SEC)]
    feats, _ = w2v.extract_features(wav)
    return audio_proj(feats[-1].mean(dim=1))


def media_url(url):
    if not url.startswith("/ear/data") and "/data/" in url:
        return "/ear/data/" + url.split("/data/")[-1]
    return url


app = Flask(__name__)


@app.get("/")
def health():
    return jsonify(status="ok", items=len(DB_METADATA))


@app.post("/query")
def query():
    if request.headers.get("X-Ear-Key") != os.environ.get("EAR_KEY"):
        return jsonify(error="Forbidden"), 403
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(error="No file"), 400
    name = file.filename.lower()
    if name.endswith((".jpg", ".jpeg", ".png")):
        query_type = "image"
    elif name.endswith((".wav", ".mp3", ".webm", ".mp4", ".m4a", ".ogg")):
        query_type = "audio"
    else:
        return jsonify(error="Unsupported file type"), 400

    suffix = os.path.splitext(name)[1]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        file.save(tmp)
        path = tmp.name
    try:
        if query_type == "image":
            emb = embed_image(path)
        else:
            try:
                emb = embed_audio(path)
            except subprocess.CalledProcessError:
                return jsonify(error="Audio conversion failed (FFmpeg error)"), 400
    finally:
        os.remove(path)

    scores, indices = torch.topk((emb @ DB_TENSOR.T).squeeze(0), min(100, len(DB_METADATA)))
    same, cross = [], []
    for score, i in zip(scores, indices):
        item = DB_METADATA[i.item()]
        bucket = same if item["type"] == query_type else cross
        if len(bucket) < 5:
            bucket.append({"type": item["type"], "url": media_url(item["url"]),
                           "label": item["label"], "score": round(score.item(), 3)})
        if len(same) >= 5 and len(cross) >= 5:
            break
    return jsonify(query_type=query_type, same_modality=same, cross_modality=cross)
