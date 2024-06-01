import asyncio
import websockets

async def handler(websocket, path):
    try:
        async for message in websocket:
            if isinstance(message, bytes):
                print("Received binary message")
                await websocket.send(message)  # Echo back the binary message for testing
            else:
                print("Received non-binary message")
    except websockets.ConnectionClosed:
        print("Connection closed")

start_server = websockets.serve(handler, "localhost", 5000)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()


