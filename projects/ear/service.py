import os
import glob
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision as tvm
import torchaudio
import gc
import logging
from flask import Flask, request, jsonify, send_from_directory, make_response
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


# --- 4. HTML UI (Embedded) ---

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Audio-Visual Instrument Retrieval</title>
    <style>
        :root { --primary: #3b82f6; --bg: #f8fafc; --card-bg: #ffffff; --text-main: #1e293b; --text-light: #64748b; }
        body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--text-main); margin: 0; padding: 40px 20px; display: flex; flex-direction: column; align-items: center; }
        .container { max-width: 1000px; width: 100%; }
        h1 { text-align: center; font-weight: 800; margin-bottom: 40px; letter-spacing: -0.025em; }
        .upload-section { background: var(--card-bg); padding: 30px; border-radius: 16px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 40px; text-align: center; }
        .action-row { display: flex; gap: 20px; justify-content: center; flex-wrap: wrap; margin-top: 20px; }
        .btn { padding: 15px 30px; border-radius: 12px; cursor: pointer; transition: all 0.2s; min-width: 160px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 10px; border: none; font-size: 1rem; }
        .btn-upload { background: #eff6ff; color: var(--primary); border: 1px solid #bfdbfe; }
        .btn-upload:hover { background: #dbeafe; }
        .btn-live { background: var(--primary); color: white; box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.3); }
        .btn-live:hover { background: #2563eb; transform: translateY(-1px); }
        .file-input { display: none; }
        #media-overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); display: none; justify-content: center; align-items: center; z-index: 100; }
        .overlay-content { background: white; padding: 20px; border-radius: 16px; max-width: 500px; width: 90%; text-align: center; }
        video { width: 100%; border-radius: 8px; background: #000; margin-bottom: 15px; }
        .audio-wave { height: 100px; background: #f1f5f9; border-radius: 8px; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; color: var(--text-light); }
        .recording-dot { width: 15px; height: 15px; background: red; border-radius: 50%; display: inline-block; margin-right: 10px; animation: pulse 1s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
        #preview-area { margin-top: 30px; display: none; flex-direction: column; align-items: center; padding-top: 20px; border-top: 1px solid #e2e8f0; }
        .preview-media { max-width: 200px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        #results-wrapper { display: none; }
        .columns-container { display: grid; grid-template-columns: 1fr 1fr; gap: 30px; margin-top: 20px; }
        @media (max-width: 768px) { .columns-container { grid-template-columns: 1fr; } }
        .column-header { font-size: 1.25rem; font-weight: 700; margin-bottom: 20px; text-align: center; padding-bottom: 10px; border-bottom: 2px solid #e2e8f0; }
        .column-header span { font-size: 0.9rem; font-weight: 400; color: var(--text-light); display: block; margin-top: 4px; }
        .results-list { display: flex; flex-direction: column; gap: 15px; }
        .result-card { background: var(--card-bg); border-radius: 12px; overflow: hidden; display: flex; align-items: center; padding: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transition: transform 0.2s; border: 1px solid #e2e8f0; }
        .result-card:hover { transform: translateY(-2px); box-shadow: 0 8px 12px rgba(0,0,0,0.05); }
        .card-media { width: 80px; height: 80px; flex-shrink: 0; border-radius: 8px; background: #f1f5f9; display: flex; align-items: center; justify-content: center; overflow: hidden; margin-right: 15px; }
        .card-media img { width: 100%; height: 100%; object-fit: cover; }
        .card-media audio { width: 80px; transform: scale(0.8); }
        .card-info { flex-grow: 1; }
        .card-label { font-weight: 600; font-size: 1rem; text-transform: capitalize; color: var(--text-main); }
        .card-score { font-size: 0.85rem; color: var(--primary); font-weight: 700; margin-top: 4px; }
        .spinner { width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: 20px auto; display: none; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
<div class="container">
    <h1>Audio-Visual Instrument Retrieval</h1>
    <div class="upload-section">
        <h3>Start Query</h3>
        <div class="action-row">
            <label class="btn btn-upload">
                📂 Upload Image <input type="file" id="imageInput" accept="image/*" class="file-input">
            </label>
            <label class="btn btn-upload">
                📂 Upload Audio <input type="file" id="audioInput" accept="audio/*" class="file-input">
            </label>
        </div>
        <div class="action-row">
            <button class="btn btn-live" onclick="startCamera()">📷 Use Camera</button>
            <button class="btn btn-live" onclick="startMic()">🎙️ Record Audio</button>
        </div>
        <div id="preview-area">
            <strong>Query Preview</strong>
            <div id="preview-content" style="margin-top:10px;"></div>
            <div class="spinner" id="loader"></div>
            <div id="error-msg" style="color:red; margin-top:10px;"></div>
        </div>
    </div>
    <div id="results-wrapper">
        <div class="columns-container">
            <div class="results-column">
                <div class="column-header">Same Modality<span id="same-header-sub"></span></div>
                <div class="results-list" id="col-same"></div>
            </div>
            <div class="results-column">
                <div class="column-header">Cross Modality<span id="cross-header-sub"></span></div>
                <div class="results-list" id="col-cross"></div>
            </div>
        </div>
    </div>
</div>
<div id="media-overlay">
    <div class="overlay-content" id="overlay-camera" style="display:none;">
        <h3>Take Photo</h3>
        <video id="camera-stream" autoplay playsinline></video>
        <button class="btn btn-live" onclick="capturePhoto()">📸 Capture</button>
        <button class="btn btn-upload" onclick="closeOverlay()">Cancel</button>
    </div>
    <div class="overlay-content" id="overlay-mic" style="display:none;">
        <h3>Record Audio</h3>
        <div class="audio-wave"><div class="recording-dot"></div> Recording...</div>
        <button class="btn btn-live" style="background-color: #ef4444;" onclick="stopRecording()">⏹️ Stop & Search</button>
        <button class="btn btn-upload" onclick="closeOverlay()">Cancel</button>
    </div>
</div>
<script>
    let mediaStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let supportedMimeType = 'audio/webm';
    let audioExtension = 'webm';
    const overlay = document.getElementById('media-overlay');
    const overlayCamera = document.getElementById('overlay-camera');
    const overlayMic = document.getElementById('overlay-mic');
    const cameraStream = document.getElementById('camera-stream');

    document.getElementById('imageInput').addEventListener('change', (e) => handleFile(e.target.files[0], 'image'));
    document.getElementById('audioInput').addEventListener('change', (e) => handleFile(e.target.files[0], 'audio'));

    async function handleFile(blob, type, fileName = null) {
        if(!blob) return;
        closeOverlay();
        document.getElementById('results-wrapper').style.display = 'none';
        const preview = document.getElementById('preview-area');
        const content = document.getElementById('preview-content');
        const loader = document.getElementById('loader');
        const errorDiv = document.getElementById('error-msg');
        
        preview.style.display = 'flex';
        loader.style.display = 'block';
        content.innerHTML = '';
        errorDiv.textContent = '';

        const url = URL.createObjectURL(blob);
        if(type === 'image') {
            const img = document.createElement('img'); img.src = url; img.className = 'preview-media'; content.appendChild(img);
        } else {
            const audio = document.createElement('audio'); audio.src = url; audio.controls = true; content.appendChild(audio);
        }

        const formData = new FormData();
        const fname = fileName || (type === 'image' ? 'capture.jpg' : `recording.${audioExtension}`);
        formData.append('file', blob, fname);

        try {
            // Note: We use relative path 'query' here which Nginx will route correctly
            const res = await fetch('query', { method: 'POST', body: formData });
            const data = await res.json();
            if(data.error) throw new Error(data.error);
            renderDualResults(data);
        } catch (err) {
            console.error(err);
            errorDiv.textContent = `Error: ${err.message}`;
        } finally {
            loader.style.display = 'none';
        }
    }

    async function startCamera() {
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
            cameraStream.srcObject = mediaStream;
            overlay.style.display = 'flex'; overlayCamera.style.display = 'block'; overlayMic.style.display = 'none';
        } catch(e) { alert("Camera access denied: " + e.message); }
    }

    function capturePhoto() {
        if (!mediaStream) return;
        const canvas = document.createElement('canvas');
        canvas.width = cameraStream.videoWidth; canvas.height = cameraStream.videoHeight;
        canvas.getContext('2d').drawImage(cameraStream, 0, 0);
        canvas.toBlob(blob => { handleFile(blob, 'image', 'webcam_capture.jpg'); }, 'image/jpeg');
    }

    async function startMic() {
        try {
            const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/mp4;codecs=mp4a.40.2'];
            supportedMimeType = types.find(t => MediaRecorder.isTypeSupported(t)) || '';
            if (!supportedMimeType) { alert("Browser not supported."); return; }
            audioExtension = supportedMimeType.includes('mp4') ? 'mp4' : 'webm';
            
            mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(mediaStream, { mimeType: supportedMimeType });
            audioChunks = [];
            mediaRecorder.ondataavailable = event => { if (event.data.size > 0) audioChunks.push(event.data); };
            mediaRecorder.onstop = () => {
                const blob = new Blob(audioChunks, { type: supportedMimeType });
                handleFile(blob, 'audio', `mic_rec.${audioExtension}`);
            };
            mediaRecorder.start();
            overlay.style.display = 'flex'; overlayCamera.style.display = 'none'; overlayMic.style.display = 'block';
        } catch(e) { alert("Microphone denied: " + e.message); }
    }

    function stopRecording() { if(mediaRecorder && mediaRecorder.state !== 'inactive') mediaRecorder.stop(); }
    function closeOverlay() {
        overlay.style.display = 'none';
        if(mediaStream) { mediaStream.getTracks().forEach(track => track.stop()); mediaStream = null; }
    }

    function renderDualResults(data) {
        document.getElementById('results-wrapper').style.display = 'block';
        const qType = data.query_type;
        document.getElementById('same-header-sub').textContent = qType === 'image' ? " (Image → Image)" : " (Audio → Audio)";
        document.getElementById('cross-header-sub').textContent = qType === 'image' ? " (Image → Audio)" : " (Audio → Image)";
        populateList(document.getElementById('col-same'), data.same_modality);
        populateList(document.getElementById('col-cross'), data.cross_modality);
    }

    function populateList(container, items) {
        container.innerHTML = '';
        const validItems = items.filter(item => {
            if (item.url.includes("My Everything.jpg") || item.url.includes("My%20Everything.jpg")) return false;
            return true;
        });
        if(validItems.length === 0) { container.innerHTML = '<div style="text-align:center; color:#999;">No matches found</div>'; return; }
        validItems.forEach(item => {
            const card = document.createElement('div'); card.className = 'result-card';
            const mediaDiv = document.createElement('div'); mediaDiv.className = 'card-media';
            // IMPORTANT: Prepend 'ear/' to url so nginx routes it back to this service
            // NOTE: The backend already returns '/ear/data/...' so we just use it directly
            if(item.type === 'image') { mediaDiv.innerHTML = `<img src="${item.url}">`; } 
            else { mediaDiv.innerHTML = `<audio src="${item.url}" controls style="width:80px; transform:scale(0.8)"></audio>`; }
            const infoDiv = document.createElement('div'); infoDiv.className = 'card-info';
            infoDiv.innerHTML = `<div class="card-label">${item.label}</div><div class="card-score">Score: ${item.score}</div>`;
            card.append(mediaDiv, infoDiv); container.appendChild(card);
        });
    }
</script>
</body>
</html>
"""

# --- 5. ROUTES ---

@app.route('/')
def index():
    # Return the embedded HTML directly
    return make_response(HTML_TEMPLATE)

@app.route('/data/<path:filename>')
@app.route('/ear/data/<path:filename>')  # <--- ADD THIS LINE
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
            
        elif filename.lower().endswith(('.wav', '.mp3', '.webm', '.mp4', '.m4a')):
            query_type = "audio"
            wav, sr = torchaudio.load(filepath)
            max_frames = int(sr * MAX_AUDIO_SEC)
            if wav.shape[1] > max_frames: wav = wav[:, :max_frames]
            if wav.shape[0] > 1: wav = wav.mean(dim=0, keepdim=True)
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
            # The cached metadata might have old URLs. We ensure they point to /ear/data
            clean_url = item['url']
            if not clean_url.startswith('/ear/data'):
                # Strip old prefix if any and prepend correct one
                basename = clean_url.split('/')[-1]
                # Try to preserve subfolders if possible, but simplest is relying on what's in cache
                # If cache has full relative paths like '/data/frames/xyz.jpg', we map to '/ear/data/frames/xyz.jpg'
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
    app.run(debug=True, port=5001)