"""HTTP API for the Earth Observation agent."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import uvicorn
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from eve_agent.agent import build_agent, invoke_agent_turn
from eve_agent.settings import API_HOST, API_PORT
from eve_agent.tracing import append_trace_record


class ChatRequest(BaseModel):
    session_id: str
    message: str

    @field_validator("session_id", "message")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class ChatResponse(BaseModel):
    session_id: str
    answer: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    app.state.agent = await build_agent()
    yield


app = FastAPI(title="EVE Earth Observation Agent", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def trace_invalid_request(
    request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    request_id = str(uuid4())
    body = error.body if isinstance(error.body, dict) else {}
    session_id = body.get("session_id")
    session_id = session_id if isinstance(session_id, str) else None
    details = jsonable_encoder(error.errors())
    timestamp = datetime.now(timezone.utc).isoformat()
    append_trace_record(
        {
            "trace_id": request_id,
            "request_id": request_id,
            "session_id": session_id,
            "method": request.method,
            "path": request.url.path,
            "started_at": timestamp,
            "finished_at": timestamp,
            "duration_ms": 0,
            "status": "rejected",
            "steps": [
                {
                    "step": "request_validation",
                    "status": "error",
                    "error": {
                        "type": "RequestValidationError",
                        "message": "Request failed validation",
                        "details": details,
                    },
                }
            ],
        }
    )
    return JSONResponse(
        status_code=422,
        content={"request_id": request_id, "detail": details},
    )


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    result = await invoke_agent_turn(
        request.app.state.agent,
        body.session_id,
        body.message,
    )
    return ChatResponse(
        session_id=body.session_id,
        answer=result["messages"][-1].content,
    )


if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)
