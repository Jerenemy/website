"""Deploys EAR's inference (inference.py) on Modal: `modal deploy projects/ear/modal/modal_app.py`.

The weights and index are untracked, like the rest of projects/ear: pretrained_models/heads.pt
and indexed_db.pt must be on the machine that deploys. The `ear-key` Modal secret holds EAR_KEY,
which projects/ear/.env on the server also sets.

It scales to zero, so it costs nothing at idle and the first query after a quiet spell waits
for a cold start. One container at most.
"""
from pathlib import Path

import modal

EAR = Path(__file__).resolve().parent.parent

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg")
    .pip_install(
        "torch==2.9.1", "torchvision==0.24.1", "torchaudio==2.9.1",
        "flask==3.1.2", "soundfile==0.13.1", "pillow==11.3.0",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    # Bake the stock encoder weights into the image so a cold start doesn't download them
    .run_commands(
        'python -c "import torchvision as tvm, torchaudio; '
        'tvm.models.resnet50(weights=tvm.models.ResNet50_Weights.IMAGENET1K_V2); '
        'torchaudio.pipelines.WAV2VEC2_BASE.get_model()"'
    )
    .add_local_file(EAR / "pretrained_models" / "heads.pt", "/root/heads.pt")
    .add_local_file(EAR / "indexed_db.pt", "/root/indexed_db.pt")
    .add_local_file(Path(__file__).parent / "inference.py", "/root/inference.py")
)

app = modal.App("ear", image=image)


@app.function(
    cpu=2.0,
    memory=2048,
    max_containers=1,
    scaledown_window=300,
    timeout=120,
    secrets=[modal.Secret.from_name("ear-key")],
)
@modal.concurrent(max_inputs=4)
@modal.wsgi_app()
def web():
    from inference import app as flask_app
    return flask_app
