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
async def websocket_agent(websocket: WebSocket):
    await websocket.accept()  # Accept the WebSocket connection
    try:
        while True:
            # Wait for a task from the client
            data = await websocket.receive_json()
            if 'action' in data and data['action'] == 'run_task':
                response = await run_browser_agent(websocket, data['tasks'])
                await websocket.send_json({"status": "completed", "result": response})
            elif 'action' in data and data['action'] == 'close':
                # Handle client-initiated close
                await websocket.close()
                break
    except Exception as e:
        logging.error(f"Error in WebSocket communication: {str(e)}")
        await websocket.send_json({"status": "error", "message": str(e)})
    finally:
        # Ensure WebSocket is closed properly
        await websocket.close()


# @app.websocket("/ws/agent")
# async def websocket_agent(websocket: WebSocket):
#     await websocket.accept()
#     try:
#         while True:
#             data = await websocket.receive_json()
#             # Process data here, for example:
#             await websocket.send_text(f"Echo: {data}")
#     except Exception as e:
#         logging.error(f"Error in WebSocket communication: {e}")
#         await websocket.send_text(f"Error: {str(e)}")
#     finally:
#         await websocket.close()
#         logging.info("WebSocket connection closed")
