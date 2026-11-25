"""HTTP API for the Earth Observation agent."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel, field_validator

from eve_agent.agent import build_agent, invoke_agent_turn
from eve_agent.settings import API_HOST, API_PORT


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
