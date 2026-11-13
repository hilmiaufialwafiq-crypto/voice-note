document.addEventListener("DOMContentLoaded", () => {
  const fileInput = document.getElementById("audio-file");
  const fileLabel = document.getElementById("file-label");
  const dropZone = document.getElementById("drop-zone");

  if (fileInput && fileLabel) {
    fileInput.addEventListener("change", () => {
      fileLabel.textContent = fileInput.files.length ? fileInput.files[0].name : "Tarik file ke sini atau pilih file";
    });
  }
  if (dropZone && fileInput) {
    ["dragenter", "dragover"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("drag-over");
    }));
    ["dragleave", "drop"].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("drag-over");
    }));
    dropZone.addEventListener("drop", (event) => {
      if (event.dataTransfer.files.length) {
        fileInput.files = event.dataTransfer.files;
        fileInput.dispatchEvent(new Event("change"));
      }
    });
  }

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const startButton = document.getElementById("start-record");
  const stopButton = document.getElementById("stop-record");
  if (!startButton || !stopButton) return;

  const status = document.getElementById("record-status");
  const timer = document.getElementById("timer");
  const hint = document.getElementById("record-hint");
  const preview = document.getElementById("audio-preview");
  const audioInput = document.getElementById("recording-file");
  const transcript = document.getElementById("transcript");
  const orbit = document.getElementById("mic-orbit");
  const supportNote = document.getElementById("speech-support-note");
  const saveButton = document.querySelector(".note-form button[type='submit']");
  const audioNameInput = document.querySelector(".note-form input[name='audio_name']");
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recorder;
  let stream;
  let recognition;
  let chunks = [];
  let elapsed = 0;
  let timerInterval;
  let recognitionStarted = false;

  if (!SpeechRecognition) {
    supportNote.textContent = "Transkripsi langsung tidak tersedia di browser ini. Rekaman tetap dapat disimpan dan dicoba ditranskripsikan melalui server.";
  }

  startButton.addEventListener("click", async () => {
    startButton.disabled = true;
    hint.textContent = "Meminta izin mikrofon...";
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
        throw new Error("Perekaman audio tidak didukung browser ini.");
      }
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunks = [];
      if (audioNameInput) audioNameInput.value = "";
      audioInput.value = "";
      const supportedMimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((mimeType) => MediaRecorder.isTypeSupported(mimeType));
      recorder = supportedMimeType
        ? new MediaRecorder(stream, { mimeType: supportedMimeType })
        : new MediaRecorder(stream);
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size) chunks.push(event.data);
      });
      recorder.addEventListener("stop", () => {
        const mimeType = recorder.mimeType || chunks[0]?.type || "audio/webm";
        const blob = new Blob(chunks, { type: mimeType });
        if (blob.size) {
          const extension = mimeType.includes("mp4")
            ? "m4a"
            : mimeType.includes("ogg")
              ? "ogg"
              : "webm";
          preview.src = URL.createObjectURL(blob);
          preview.hidden = false;
          const file = new File([blob], `rekaman-${Date.now()}.${extension}`, { type: mimeType });
          const transfer = new DataTransfer();
          transfer.items.add(file);
          audioInput.files = transfer.files;
        } else {
          supportNote.textContent = "Audio kosong tidak dapat disimpan. Coba rekam kembali.";
        }
        stream?.getTracks().forEach((track) => track.stop());
        window.clearInterval(timerInterval);
        startButton.disabled = false;
        stopButton.disabled = true;
        if (saveButton) saveButton.disabled = false;
        status.innerHTML = "<i></i> Rekaman selesai";
        status.classList.remove("is-recording");
        orbit.classList.remove("is-recording");
        hint.textContent = "Rekaman siap. Periksa hasil transkripsi, lengkapi judul, lalu simpan catatan.";
      });
      recorder.start();
      if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.lang = "id-ID";
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.addEventListener("result", (event) => {
          let finalText = "";
          let interimText = "";
          for (let index = event.resultIndex; index < event.results.length; index += 1) {
            const result = event.results[index];
            if (result.isFinal) finalText += result[0].transcript + " ";
            else interimText += result[0].transcript;
          }
          if (finalText) transcript.value = `${transcript.value.trim()} ${finalText}`.trim();
          hint.textContent = interimText ? `Mendengar: “${interimText}”` : "Perekaman dan transkripsi sedang berjalan.";
        });
        recognition.addEventListener("error", (event) => {
          if (event.error !== "no-speech" && event.error !== "aborted") {
            recognitionStarted = false;
            supportNote.textContent = "Transkripsi browser terhenti. Rekaman tetap berjalan; teks yang tersedia bisa diedit atau audio dicoba ditranskripsikan oleh server.";
          }
        });
        recognition.addEventListener("end", () => {
          if (recognitionStarted && recorder && recorder.state === "recording") {
            try {
              recognition.start();
            } catch (_error) {
              recognitionStarted = false;
              supportNote.textContent = "Transkripsi browser tidak dapat dilanjutkan. Rekaman audio tetap berjalan.";
            }
          }
        });
        recognitionStarted = true;
        try {
          recognition.start();
        } catch (_error) {
          recognitionStarted = false;
          supportNote.textContent = "Transkripsi browser tidak dapat dimulai. Rekaman audio tetap berjalan.";
        }
      }
      elapsed = 0;
      timer.textContent = "00:00";
      timerInterval = window.setInterval(() => {
        elapsed += 1;
        timer.textContent = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;
      }, 1000);
      stopButton.disabled = false;
      status.innerHTML = "<i></i> Sedang merekam";
      status.classList.add("is-recording");
      orbit.classList.add("is-recording");
      hint.textContent = SpeechRecognition ? "Ucapkan materi dengan jelas. Teks akan muncul di panel catatan." : "Perekaman berlangsung. Berhenti untuk menyimpan audionya.";
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      stream = null;
      if (recorder && recorder.state !== "inactive") recorder.stop();
      startButton.disabled = false;
      stopButton.disabled = true;
      if (saveButton) saveButton.disabled = false;
      status.innerHTML = "<i></i> Siap merekam";
      status.classList.remove("is-recording");
      orbit.classList.remove("is-recording");
      supportNote.textContent = error.name === "NotAllowedError"
        ? "Akses mikrofon ditolak. Izinkan mikrofon di pengaturan browser lalu coba lagi."
        : error.message || "Mikrofon tidak dapat diakses. Pastikan perangkat memiliki mikrofon dan gunakan koneksi aman.";
      hint.textContent = "Periksa izin mikrofon dan coba lagi.";
    }
  });

  stopButton.addEventListener("click", () => {
    if (recognition) {
      recognitionStarted = false;
      recognition.stop();
    }
    if (recorder && recorder.state !== "inactive") recorder.stop();
    stopButton.disabled = true;
    if (saveButton) saveButton.disabled = true;
    status.innerHTML = "<i></i> Menyimpan rekaman...";
    hint.textContent = "Menyiapkan file audio...";
  });
});
