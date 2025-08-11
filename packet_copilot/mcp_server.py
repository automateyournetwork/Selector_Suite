# mcp_server.py
import os, base64, json, uuid, subprocess, tempfile, shutil
from collections import defaultdict
from fastmcp import FastMCP

# === LangChain / RAG bits (mirrors your Streamlit flow, no st.*) ===
import ipaddress, re
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationalRetrievalChain
from langchain_community.document_loaders import JSONLoader
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.vectorstores import Chroma
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder
)

load_dotenv()
assert os.getenv("GOOGLE_API_KEY"), "GOOGLE_API_KEY is required for Gemini."

mcp = FastMCP("PacketCopilot")

# session_id -> state
SESSIONS = defaultdict(dict)  # keys: dir, pcap_path, json_path, docs, pages, qa

# ---------- helpers ----------
def _session(session_id: str) -> dict:
    s = SESSIONS[session_id]
    if "dir" not in s:
        s["dir"] = tempfile.mkdtemp(prefix=f"pcap_{session_id}_")
    return s

def _pcap_to_json(pcap_path: str, json_path: str):
    cmd = f'tshark -nlr "{pcap_path}" -T json > "{json_path}"'
    subprocess.run(cmd, shell=True, check=True)
    # scrub hex payloads similar to your app
    with open(json_path, "r") as f:
        data = json.load(f)
    for pkt in data:
        layers = pkt.get("_source", {}).get("layers", {})
        tcp = layers.get("tcp", {})
        udp = layers.get("udp", {})
        if isinstance(tcp, dict):
            tcp.pop("tcp.payload", None)
            tcp.pop("tcp.segment_data", None)
            tcp.pop("tcp.reassembled.data", None)
        if isinstance(udp, dict):
            udp.pop("udp.payload", None)
        tls = layers.get("tls", {})
        if isinstance(tls, dict):
            tls.pop("tls.segment.data", None)
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

def _build_docs_from_json(json_path: str):
    loader = JSONLoader(
        file_path=json_path,
        jq_schema=".[] | ._source.layers | del(.data)",
        text_content=False
    )
    pages = loader.load_and_split()
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2', model_kwargs={"device": "cpu"})
    splitter = SemanticChunker(embeddings)
    docs = splitter.split_documents(pages)
    return docs, pages

def _return_system_text(pcap_pages) -> str:
    pcap_summary = " ".join([str(p) for p in pcap_pages[:5]])
    return f"""
You are an expert assistant specialized in analyzing PCAPs. Use only the provided packet_capture_info.
Be concise, structured, and add brief protocol hints when relevant.

packet_capture_info (sample):
{pcap_summary}
"""

def _build_chain(docs, priming_text, persist_dir: str):
    embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2', model_kwargs={"device": "cpu"})
    vectordb = Chroma.from_documents(docs, embeddings, persist_directory=persist_dir)
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro-preview-03-25", temperature=0.6)
    prompt = ChatPromptTemplate.from_messages([
        SystemMessagePromptTemplate.from_template(priming_text + "\n\n{context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        HumanMessagePromptTemplate.from_template("{question}")
    ])
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    qa = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectordb.as_retriever(search_kwargs={"k": 50}),
        memory=memory,
        combine_docs_chain_kwargs={'prompt': prompt},
        get_chat_history=lambda x: x,
    )
    return qa

# ---------- MCP tools ----------
@mcp.tool
def new_session() -> str:
    """Create a new analysis session and return its session_id."""
    sid = str(uuid.uuid4())
    _session(sid)
    return sid

@mcp.tool
def upload_pcap_base64(session_id: str, filename: str, data_b64: str) -> str:
    """
    Upload a PCAP/PCAPNG (base64 string). Returns server-local pcap path.
    Note: nginx client_max_body_size may limit size (base64 adds ~33%).
    """
    s = _session(session_id)
    raw = base64.b64decode(data_b64)
    pcap_path = os.path.join(s["dir"], os.path.basename(filename))
    with open(pcap_path, "wb") as f:
        f.write(raw)
    s["pcap_path"] = pcap_path
    return pcap_path

@mcp.tool
def convert_to_json(session_id: str) -> str:
    """
    Convert the uploaded PCAP to JSON via tshark and scrub payloads.
    Returns server-local JSON path.
    """
    s = _session(session_id)
    if not s.get("pcap_path"):
        raise ValueError("No PCAP uploaded. Call upload_pcap_base64 first.")
    json_path = s["pcap_path"] + ".json"
    _pcap_to_json(s["pcap_path"], json_path)
    s["json_path"] = json_path
    return json_path

@mcp.tool
def index_pcap(session_id: str) -> str:
    """
    Build embeddings, split to semantic chunks, create Chroma + RAG chain.
    Returns a short summary of index stats.
    """
    s = _session(session_id)
    if not s.get("json_path"):
        raise ValueError("No JSON found. Call convert_to_json first.")
    docs, pages = _build_docs_from_json(s["json_path"])
    if not docs:
        raise ValueError("No documents generated from the PCAP JSON.")
    s["docs"] = docs
    s["pages"] = pages
    priming = _return_system_text(pages)
    persist_dir = os.path.join(s["dir"], f"chroma_{session_id}")
    s["qa"] = _build_chain(docs, priming, persist_dir)
    return f"Indexed {len(docs)} chunks from {len(pages)} packets."

@mcp.tool
def analyze_pcap(session_id: str, question: str) -> str:
    """
    Ask a question against the indexed PCAP (RAG over Chroma + Gemini).
    """
    s = _session(session_id)
    qa = s.get("qa")
    if qa is None:
        return "PCAP not indexed yet. Call index_pcap first."
    resp = qa({"question": question})
    return resp.get("answer", "No response generated.")

@mcp.tool
def cleanup(session_id: str) -> str:
    """Delete session artifacts."""
    s = SESSIONS.pop(session_id, None)
    if s and (wd := s.get("dir")) and os.path.exists(wd):
        shutil.rmtree(wd, ignore_errors=True)
    return "ok"

if __name__ == "__main__":
    # http streamable endpoint at /mcp/
    mcp.run(transport="http", host="0.0.0.0", port=8000)
