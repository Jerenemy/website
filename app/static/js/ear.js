(function () {
  const config = window.EAR_CONFIG || {};
  const QUERY_URL = config.queryUrl;

  const ui = {
    imageInput: document.getElementById("imageInput"),
    audioInput: document.getElementById("audioInput"),
    preview: document.getElementById("preview-area"),
    previewContent: document.getElementById("preview-content"),
    loader: document.getElementById("loader"),
    errorMsg: document.getElementById("error-msg"),
    results: document.getElementById("results-wrapper"),
    sameSub: document.getElementById("same-header-sub"),
    crossSub: document.getElementById("cross-header-sub"),
    colSame: document.getElementById("col-same"),
    colCross: document.getElementById("col-cross"),
    overlay: document.getElementById("media-overlay"),
    overlayCamera: document.getElementById("overlay-camera"),
    overlayMic: document.getElementById("overlay-mic"),
    cameraStream: document.getElementById("camera-stream"),
    banner: document.getElementById("ear-banner"),
    bannerText: document.getElementById("ear-banner-text"),
    btnCamera: document.getElementById("btn-camera"),
    btnMic: document.getElementById("btn-mic"),
    btnCapture: document.getElementById("btn-capture"),
    btnStop: document.getElementById("btn-stop"),
    btnCancelCamera: document.getElementById("btn-cancel-camera"),
    btnCancelMic: document.getElementById("btn-cancel-mic"),
  };

  const state = {
    mediaStream: null,
    mediaRecorder: null,
    audioChunks: [],
    supportedMimeType: "audio/webm",
    audioExtension: "webm",
    discardRecording: false,
  };

  const toggleHidden = (el, hidden) => {
    if (!el) return;
    if (hidden) el.classList.add("hidden");
    else el.classList.remove("hidden");
  };

  const setError = (message) => {
    if (!ui.errorMsg) return;
    ui.errorMsg.textContent = message || "";
    ui.errorMsg.classList.toggle("hidden", !message);
  };

  const disableControls = () => {
    [
      ui.imageInput,
      ui.audioInput,
      ui.btnCamera,
      ui.btnMic,
      ui.btnCapture,
      ui.btnStop,
      ui.btnCancelCamera,
      ui.btnCancelMic,
    ].forEach((el) => {
      if (el) el.disabled = true;
    });
  };

  const showBanner = (message) => {
    if (!ui.banner) return;
    ui.bannerText.textContent = message;
    toggleHidden(ui.banner, false);
  };

  // Hard failure states: missing endpoint or backend not available.
  if (!QUERY_URL) {
    showBanner("Missing query endpoint.");
    setError("Query endpoint missing.");
    disableControls();
    return;
  }

  if (config.engineError) {
    showBanner(`Backend unavailable: ${config.engineError}`);
    setError("Ear backend is unavailable right now.");
    disableControls();
    return;
  }

  const stopTracks = () => {
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((t) => t.stop());
      state.mediaStream = null;
    }
  };

  const hideOverlay = () => {
    toggleHidden(ui.overlay, true);
    ui.overlay?.setAttribute("aria-hidden", "true");
  };

  const showOverlay = (mode) => {
    toggleHidden(ui.overlay, false);
    ui.overlay?.setAttribute("aria-hidden", "false");
    toggleHidden(ui.overlayCamera, mode !== "camera");
    toggleHidden(ui.overlayMic, mode !== "mic");
  };

  const closeOverlay = () => {
    hideOverlay();
    stopTracks();
  };

  const renderPreview = (blob, type) => {
    if (!ui.preview || !ui.previewContent) return;
    toggleHidden(ui.preview, false);
    ui.previewContent.innerHTML = "";
    const url = URL.createObjectURL(blob);
    if (type === "image") {
      const img = document.createElement("img");
      img.src = url;
      img.className = "preview-media";
      ui.previewContent.appendChild(img);
    } else {
      const audio = document.createElement("audio");
      audio.src = url;
      audio.controls = true;
      ui.previewContent.appendChild(audio);
    }
  };

  const populateList = (container, items) => {
    if (!container) return;
    container.innerHTML = "";

    const validItems = (items || []).filter((item) => {
      if (!item || !item.url) return false;
      if (item.url.includes("My Everything.jpg") || item.url.includes("My%20Everything.jpg")) {
        return false;
      }
      return true;
    });

    if (validItems.length === 0) {
      container.innerHTML = '<div style="color:#94a3b8;">No matches found</div>';
      return;
    }

    validItems.forEach((item) => {
      const card = document.createElement("div");
      card.className = "result-card";

      const mediaDiv = document.createElement("div");
      mediaDiv.className = "card-media";
      if (item.type === "image") {
        mediaDiv.innerHTML = `<img src="${item.url}" alt="${item.label}">`;
      } else {
        mediaDiv.innerHTML = `<audio src="${item.url}" controls></audio>`;
      }

      const info = document.createElement("div");
      info.className = "card-info";
      info.innerHTML = `<div class="card-label">${item.label}</div><div class="card-score">Score: ${item.score}</div>`;

      card.append(mediaDiv, info);
      container.appendChild(card);
    });
  };

  const renderResults = (data) => {
    if (!ui.results) return;
    toggleHidden(ui.results, false);

    const qType = data.query_type;
    ui.sameSub.textContent = qType === "image" ? "Image → Image" : "Audio → Audio";
    ui.crossSub.textContent = qType === "image" ? "Image → Audio" : "Audio → Image";

    populateList(ui.colSame, data.same_modality);
    populateList(ui.colCross, data.cross_modality);
  };

  const handleFile = async (blob, type, fileName) => {
    if (!blob) return;
    closeOverlay();
    toggleHidden(ui.results, true);
    setError("");

    renderPreview(blob, type);
    toggleHidden(ui.loader, false);

    const formData = new FormData();
    const fname = fileName || (type === "image" ? "capture.jpg" : `recording.${state.audioExtension}`);
    formData.append("file", blob, fname);

    try {
      const res = await fetch(QUERY_URL, { method: "POST", body: formData });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.error) {
        throw new Error(data.error || `Request failed (${res.status})`);
      }
      renderResults(data);
    } catch (err) {
      console.error(err);
      setError(err.message || "Unknown error");
    } finally {
      toggleHidden(ui.loader, true);
    }
  };

  const startCamera = async () => {
    try {
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (ui.cameraStream) {
        ui.cameraStream.srcObject = state.mediaStream;
      }
      showOverlay("camera");
    } catch (err) {
      setError(`Camera access denied: ${err.message}`);
    }
  };

  const capturePhoto = () => {
    if (!state.mediaStream || !ui.cameraStream) return;
    const canvas = document.createElement("canvas");
    canvas.width = ui.cameraStream.videoWidth;
    canvas.height = ui.cameraStream.videoHeight;
    canvas.getContext("2d").drawImage(ui.cameraStream, 0, 0);
    canvas.toBlob((blob) => {
      handleFile(blob, "image", "webcam_capture.jpg");
    }, "image/jpeg");
  };

  const startMic = async () => {
    try {
      const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/mp4;codecs=mp4a.40.2"];
      state.supportedMimeType = types.find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
      if (!state.supportedMimeType) {
        setError("Your browser does not support in-browser recording.");
        return;
      }

      state.audioExtension = state.supportedMimeType.includes("mp4") ? "mp4" : "webm";
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      state.mediaRecorder = new MediaRecorder(state.mediaStream, { mimeType: state.supportedMimeType });
      state.audioChunks = [];
      state.discardRecording = false;

      state.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) state.audioChunks.push(event.data);
      };

      state.mediaRecorder.onstop = () => {
        if (state.discardRecording) {
          state.audioChunks = [];
          state.mediaRecorder = null;
          return;
        }
        const blob = new Blob(state.audioChunks, { type: state.supportedMimeType });
        state.mediaRecorder = null;
        handleFile(blob, "audio", `mic_rec.${state.audioExtension}`);
      };

      state.mediaRecorder.start();
      showOverlay("mic");
    } catch (err) {
      setError(`Microphone access denied: ${err.message}`);
    }
  };

  const stopRecording = () => {
    state.discardRecording = false;
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
    stopTracks();
    hideOverlay();
  };

  const cancelRecording = () => {
    state.discardRecording = true;
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
    stopTracks();
    hideOverlay();
  };

  // --- Events ---
  ui.imageInput?.addEventListener("change", (e) => handleFile(e.target.files[0], "image"));
  ui.audioInput?.addEventListener("change", (e) => handleFile(e.target.files[0], "audio"));
  ui.btnCamera?.addEventListener("click", startCamera);
  ui.btnMic?.addEventListener("click", startMic);
  ui.btnCapture?.addEventListener("click", capturePhoto);
  ui.btnStop?.addEventListener("click", stopRecording);
  ui.btnCancelCamera?.addEventListener("click", closeOverlay);
  ui.btnCancelMic?.addEventListener("click", cancelRecording);
  ui.overlay?.addEventListener("click", (e) => {
    if (e.target === ui.overlay) {
      if (!ui.overlayMic?.classList.contains("hidden")) {
        cancelRecording();
      } else {
        closeOverlay();
      }
    }
  });
})();
