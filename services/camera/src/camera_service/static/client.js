let peer = null;
let sessionId = null;
let heartbeat = null;

const startButton = document.querySelector("#start");
const stopButton = document.querySelector("#stop");
const statusText = document.querySelector("#status");
const videos = document.querySelector("#videos");

function setStatus(message) {
  statusText.textContent = message;
}

function waitForIceGatheringComplete(connection) {
  if (connection.iceGatheringState === "complete") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    function checkState() {
      if (connection.iceGatheringState === "complete") {
        connection.removeEventListener("icegatheringstatechange", checkState);
        resolve();
      }
    }
    connection.addEventListener("icegatheringstatechange", checkState);
  });
}

async function start() {
  startButton.disabled = true;
  setStatus("Checking camera…");

  try {
    const healthResponse = await fetch("/health", { cache: "no-store" });
    const health = await healthResponse.json();
    if (!healthResponse.ok) {
      throw new Error("Camera is unavailable");
    }

    peer = new RTCPeerConnection({ iceServers: [] });
    const connection = peer;
    for (const camera of health.cameras) {
      connection.addTransceiver("video", { direction: "recvonly" });
    }

    connection.addEventListener("track", (event) => {
      const index = connection.getTransceivers().indexOf(event.transceiver);
      const panel = document.createElement("section");
      const label = document.createElement("h2");
      label.textContent = health.cameras[index]?.device || "Camera";
      panel.appendChild(label);
      const video = document.createElement("video");
      video.autoplay = true;
      video.playsInline = true;
      video.muted = true;
      video.srcObject = new MediaStream([event.track]);
      panel.appendChild(video);
      videos.appendChild(panel);
    });

    connection.addEventListener("connectionstatechange", () => {
      setStatus("WebRTC: " + connection.connectionState);
      if (["failed", "closed"].includes(connection.connectionState)) {
        stop();
      }
    });

    const offer = await connection.createOffer();
    await connection.setLocalDescription(offer);
    await waitForIceGatheringComplete(connection);

    setStatus("Sending offer…");
    const offerResponse = await fetch("/offer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sdp: connection.localDescription.sdp,
        type: connection.localDescription.type,
      }),
    });
    const answer = await offerResponse.json();
    if (!offerResponse.ok) {
      throw new Error(answer.error || "WebRTC offer failed");
    }
    sessionId = answer.session_id;
    await connection.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    heartbeat = setInterval(() => {
      if (sessionId) {
        fetch("/sessions/" + sessionId, { method: "POST" }).catch(() => {});
      }
    }, 5000);
    stopButton.disabled = false;
  } catch (error) {
    setStatus(error.message);
    stop();
  }
}

function stop() {
  clearInterval(heartbeat);
  heartbeat = null;
  if (sessionId) {
    fetch("/sessions/" + sessionId, { method: "DELETE", keepalive: true }).catch(() => {});
    sessionId = null;
  }
  if (peer) {
    peer.close();
    peer = null;
  }
  videos.replaceChildren();
  startButton.disabled = false;
  stopButton.disabled = true;
}

startButton.addEventListener("click", start);
stopButton.addEventListener("click", stop);
window.addEventListener("beforeunload", stop);
