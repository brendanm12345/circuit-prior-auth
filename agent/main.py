# RUN: uvicorn main:app --reload
import asyncio
from fastapi import WebSocket
from fastapi import FastAPI, Request, WebSocket
from typing import List
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from workflow import run_browser_agent
import os
import json
import random
import logging
import os
import time

app = FastAPI()
client = OpenAI()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    response = await call_next(request)
    return response

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@app.post("/")
async def root():
    return {"message": "Hello World"}


app = FastAPI()


@app.websocket("/ws/agent")
# i need this endpoint to be able to send web sockets messages to the client frequiently while the agent completes actions NOT JUST ALL AT ONCE ONCE THE WEB DRIVER QUITS
async def websocket_agent(websocket: WebSocket):
    await websocket.accept()  # Accept the WebSocket connection
    try:
        while True:
            task = await websocket.receive_json()
            print("Received task:", task)
            # Run browser agent in the background, allowing the WebSocket to handle other messages
            asyncio.create_task(run_browser_agent(websocket, task))
    except Exception as e:
        logging.error(f"Error in WebSocket communication: {str(e)}")
        await websocket.send_json({"status": "error", "message": str(e)})
    finally:
        if not websocket.client_state.value == "DISCONNECTED":
            await websocket.close()
