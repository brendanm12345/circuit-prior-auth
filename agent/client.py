# RUN: python3 client.py
import asyncio
import websockets
import json


async def test_browser_agent():
    uri = "ws://localhost:8000/ws/agent"  # Adjust the URL to your FastAPI server
    async with websockets.connect(uri) as websocket:
        # Define a simple task
        task = {
            "id": "1",
            "web_name": "Test Task",
            "ques": "Navigate to example.com",
            "web": "https://www.example.com"
        }
        # Send the task
        await websocket.send(json.dumps(task))

        # Await and print responses
        try:
            while True:
                response = await websocket.recv()
                print("Received from server:", response)
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed by server.")

# Run the test
asyncio.run(test_browser_agent())
