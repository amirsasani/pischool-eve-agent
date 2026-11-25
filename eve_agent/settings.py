import os

from dotenv import load_dotenv

load_dotenv()

API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
TRACE_FILE = os.getenv("TRACE_FILE", "logs/agent-traces.jsonl")
MCP_SERVER_HOST = os.getenv("MCP_SERVER_HOST", "127.0.0.1")
MCP_SERVER_PORT = int(os.getenv("MCP_SERVER_PORT", "8001"))
MCP_SERVER_URL = f"http://{MCP_SERVER_HOST}:{MCP_SERVER_PORT}/mcp"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:4b")
