import os
import glob
import soundfile as sf
import subprocess
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision as tvm
import torchaudio
import gc
import logging
from flask import Flask, request, jsonify, send_from_directory, render_template
from werkzeug.utils import secure_filename
from PIL import Image

# --- CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Note: Matching your server folder name 'ear_data'
DATASET_ROOT = os.path.join(BASE_DIR, 'ear_data') 
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
# We look for the .pt file in the root first, or inside ear_data
CACHE_PATH = os.path.join(BASE_DIR, 'indexed_db.pt')
MODEL_PATH = os.path.join(BASE_DIR, 'pretrained_models', 'best_audio_visual_clip.pt')

# CRITICAL: Limit threads to prevent VPS crash
torch.set_num_threads(1)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EarService")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Force CPU
device = "cpu"

# --- 1. MODEL ARCHITECTURE ---

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


# --- 2. INITIALIZATION ---

logger.info("Initializing model architecture...")

# Load ResNet
resnet_weights = tvm.models.ResNet50_Weights.IMAGENET1K_V2
resnet = tvm.models.resnet50(weights=resnet_weights).eval()
image_encoder = torch.nn.Sequential(*(list(resnet.children())[:-1]), torch.nn.Flatten(1))
img_transforms = resnet_weights.transforms()

# Load Wav2Vec2
bundle = torchaudio.pipelines.WAV2VEC2_BASE
w2v = bundle.get_model().eval()
with torch.no_grad():
    dummy = torch.zeros(1, bundle.sample_rate)
    feats, _ = w2v.extract_features(dummy)
    d_a = feats[-1].shape[-1]
audio_encoder = AudioEncoder(w2v, bundle.sample_rate, d_a)

# Assemble Model
model = AudioVisualCLIP(image_encoder, audio_encoder, audio_dim=d_a, embed_dim=512)
model.to(device)

# Load Weights
if os.path.exists(MODEL_PATH):
    logger.info(f"Loading weights from {MODEL_PATH}")
    state_dict = torch.load(MODEL_PATH, map_location=device)
    model.load_state_dict(state_dict)
    model.eval()
else:
    logger.error(f"Model file not found at {MODEL_PATH}")
    # We don't exit, so the service stays up, but it won't work well.
    
# --- 3. DATASET INDEXING (STRICT LOAD) ---

DB_METADATA = []
DB_TENSOR = None
MAX_AUDIO_SEC = 10

def load_index():
    global DB_METADATA, DB_TENSOR
    
    if os.path.exists(CACHE_PATH):
        logger.info(f"Loading cached database from {CACHE_PATH}")
        try:
            # Force map_location to CPU to avoid CUDA errors
            cache_data = torch.load(CACHE_PATH, map_location="cpu")
            DB_METADATA = cache_data['metadata']
            DB_TENSOR = cache_data['tensor']
            
            # Ensure tensor is on correct device (CPU)
            if hasattr(DB_TENSOR, 'to'):
                DB_TENSOR = DB_TENSOR.to(device)
                
            logger.info(f"Success! Loaded {len(DB_METADATA)} items.")
        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            DB_METADATA = []
            DB_TENSOR = None
    else:
        logger.warning(f"No cache file found at {CACHE_PATH}. Please upload 'indexed_db.pt'.")

# Load immediately on startup
load_index()


# --- 5. ROUTES ---

@app.route('/')
def index():
    # Pass 'debug' status to the template
    return render_template('index.html', debug=app.debug)

@app.route('/ce-loss')
def ce_loss():
    # Pass 'debug' status to the template
    return render_template('ce_loss.html', debug=app.debug)


@app.route('/data/<path:filename>')
@app.route('/ear/data/<path:filename>')
def serve_data(filename):
    # Serve files from the ear_data folder
    return send_from_directory(DATASET_ROOT, filename)

@app.route('/query', methods=['POST'])
def query_endpoint():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No file'}), 400
    
    # Check if DB is loaded
    if DB_TENSOR is None or len(DB_METADATA) == 0:
         return jsonify({'error': 'System warming up or index missing.'}), 503

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        query_emb = None
        query_type = ""
        
        # 1. Embed the Query
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            query_type = "image"
            img = Image.open(filepath).convert("RGB")
            tensor = img_transforms(img).unsqueeze(0).to(device)
            query_emb = model.encode_image(tensor)
            
        elif filename.lower().endswith(('.wav', '.mp3', '.webm', '.mp4', '.m4a', '.ogg')):
            query_type = "audio"
            
            # 1. CONVERT: Use system FFmpeg to normalize to 16kHz Mono WAV
            # This fixes "Format not recognised" (especially for webm)
            temp_wav = filepath + ".converted.wav"
            try:
                subprocess.run([
                    "ffmpeg", 
                    "-i", filepath,       # Input file
                    "-ar", "16000",       # Resample to 16000 Hz
                    "-ac", "1",           # Downmix to Mono
                    "-y",                 # Overwrite output
                    temp_wav
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                return jsonify({'error': 'Audio conversion failed (FFmpeg error)'}), 400

            # 2. LOAD: Read the clean WAV file
            # We use soundfile instead of torchaudio to be safe
            data, sr = sf.read(temp_wav, dtype='float32')
            wav = torch.from_numpy(data).float()
            
            # Cleanup the temp file now that we have the data in memory
            if os.path.exists(temp_wav):
                os.remove(temp_wav)

            # 3. FORMAT: Ensure shape is (Channels, Time)
            if wav.ndim == 1:
                wav = wav.unsqueeze(0)
            else:
                wav = wav.t()

            # 4. PREPARE: Trim and move to device
            max_frames = int(sr * MAX_AUDIO_SEC)
            if wav.shape[1] > max_frames: 
                wav = wav[:, :max_frames]
            
            wav = wav.to(device)
            query_emb = model.encode_audio(wav, sr)
        else:
            return jsonify({'error': 'Unsupported file type'}), 400

        # 2. Similarity Search
        similarities = (query_emb @ DB_TENSOR.T).squeeze(0)
        topk_scores, topk_indices = torch.topk(similarities, min(100, len(DB_METADATA)))
        
        same_modality_results = []
        cross_modality_results = []
        
        # 3. Filter into buckets
        for score, idx in zip(topk_scores, topk_indices):
            item = DB_METADATA[idx.item()]
            
            # Helper to fix URLs for the frontend
            clean_url = item['url']
            if not clean_url.startswith('/ear/data'):
                # Strip old prefix if any and prepend correct one
                if '/data/' in clean_url:
                    rel = clean_url.split('/data/')[-1]
                    clean_url = f"/ear/data/{rel}"
            
            result_obj = {
                "type": item['type'],
                "url": clean_url,
                "label": item['label'],
                "score": round(score.item(), 3)
            }
            
            if item['type'] == query_type:
                if len(same_modality_results) < 5:
                    same_modality_results.append(result_obj)
            else:
                if len(cross_modality_results) < 5:
                    cross_modality_results.append(result_obj)
            
            if len(same_modality_results) >= 5 and len(cross_modality_results) >= 5:
                break

        return jsonify({
            "query_type": query_type,
            "same_modality": same_modality_results,
            "cross_modality": cross_modality_results
        })

    except Exception as e:
        logger.exception("Query failed")
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

if __name__ == '__main__':
    # Local testing
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Run in debug mode")
    args = parser.parse_args()

    # Defaults to False. Only becomes True if you run with --debug
    print(f"Starting EAR Service on port 5001 (Debug={args.debug})...")
    app.run(debug=args.debug, port=5001)