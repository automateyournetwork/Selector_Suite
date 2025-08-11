import os, base64, json, uuid, subprocess, tempfile, shutil
from fastmcp import FastMCP

mcp = FastMCP("PacketCopilot")

SESSIONS = {}  # session_id -> working_dir path

def _workdir(session_id: str) -> str:
    if session_id not in SESSIONS:
        wd = tempfile.mkdtemp(prefix=f"pcap_{session_id}_")
        SESSIONS[session_id] = wd
    return SESSIONS[session_id]

@mcp.tool
def new_session() -> str:
    """Create a new analysis session and return its session_id."""
    return str(uuid.uuid4())

@mcp.tool
def upload_pcap_base64(session_id: str, filename: str, data_b64: str) -> str:
    """Upload a PCAP/PCAPNG (base64-encoded). Returns path (server-local)."""
    wd = _workdir(session_id)
    raw = base64.b64decode(data_b64)
    pcap_path = os.path.join(wd, filename)
    with open(pcap_path, "wb") as f:
        f.write(raw)
    return pcap_path

@mcp.tool
def convert_to_json(session_id: str, pcap_path: str) -> str:
    """Run tshark to JSON (payloads stripped). Returns JSON text path."""
    wd = _workdir(session_id)
    json_path = pcap_path + ".json"
    cmd = f'tshark -nlr "{pcap_path}" -T json > "{json_path}"'
    subprocess.run(cmd, shell=True, check=True)

    # (optional) scrub sensitive hex payloads similar to your Streamlit code
    with open(json_path, "r") as f:
        data = json.load(f)
    for pkt in data:
        layers = pkt.get("_source", {}).get("layers", {})
        for k in ("udp", "tcp"):
            if k in layers:
                layers[k].pop(f"{k}.payload", None)
                layers[k].pop(f"{k}.segment_data", None)
                layers[k].pop(f"{k}.reassembled.data", None)
        if "tls" in layers and isinstance(layers["tls"], dict):
            layers["tls"].pop("tls.segment.data", None)
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    return json_path

@mcp.tool
def ask(session_id: str, question: str) -> str:
    """Ask about the uploaded/converted PCAP (RAG/LLM logic lives here)."""
    # You can:
    #  - Reuse your existing chunking + Chroma + Gemini flow
    #  - Or call your Streamlit app’s core funcs extracted into a shared module
    # For now, just echo:
    return f"[demo] Received: {question}. Build RAG over session {session_id}."

@mcp.tool
def cleanup(session_id: str) -> str:
    """Delete all session artifacts immediately."""
    wd = SESSIONS.pop(session_id, None)
    if wd and os.path.exists(wd):
        shutil.rmtree(wd, ignore_errors=True)
    return "ok"

if __name__ == "__main__":
    # Exposes http://0.0.0.0:8000/mcp/ (default path “/mcp/”)
    mcp.run(transport="http", host="0.0.0.0", port=8000)