import asyncio
import websockets
import json
import ssl

from hammerib.config import settings
from hammerib.alaric_api.alaric_auth import get_alaric_access_token, validate_alaric_token

class AlaricWebsocketClient:
    def __init__(self, ws_url=None, token=None):
        self.ws_url = ws_url or settings.ALARIC_WEBSOCKET_URL
        self.token = token
        self.websocket = None
        self.is_connected = False
        self.message_handler_callback = None # Callback for handling incoming messages

    async def _ensure_token(self):
        """Ensures a valid token is available, fetching a new one if necessary."""
        if not self.token or not validate_alaric_token(self.token):
            print("No valid token found. Attempting to fetch a new one...")
            # This assumes client_credentials grant for simplicity here.
            # You might need to adjust based on your actual auth flow.
            self.token = await asyncio.to_thread(
                get_alaric_access_token, 
                client_id=settings.ALARIC_CLIENT_ID, 
                client_secret=settings.ALARIC_CLIENT_SECRET
            )
            if not self.token:
                print("Failed to obtain a new access token. Cannot connect.")
                return False
            # Save the new token back to settings if desired (e.g., for other parts of app)
            # Be mindful of where the authoritative token state is managed.
            settings.ALARIC_ACCESS_TOKEN = self.token 
        return True

    async def connect(self):
        """Establishes a WebSocket connection to the Alaric API."""
        if self.is_connected and self.websocket:
            print("Already connected.")
            return

        if not await self._ensure_token():
            return

        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        # Configure SSL context for TLS 1.2 or higher
        # websockets library typically uses system's default which should be fine,
        # but explicitly setting can ensure compliance if needed.
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = True # Alaric uses a public cert, so hostname check is good
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

        try:
            print(f"Connecting to Alaric WebSocket: {self.ws_url}")
            self.websocket = await websockets.connect(
                self.ws_url,
                extra_headers=headers,
                ssl=ssl_context,
                ping_interval=20, # Send a ping every 20 seconds
                ping_timeout=20   # Wait 20 seconds for a pong response
            )
            self.is_connected = True
            print("Successfully connected to Alaric WebSocket API.")
            # Start a task to listen for messages
            asyncio.create_task(self._listen())
        except websockets.exceptions.InvalidStatusCode as e:
            print(f"Connection failed: Invalid status code {e.status_code}. Response headers: {e.headers}")
            if e.status_code == 401:
                print("Authentication failed (401 Unauthorized). Check your access token and credentials.")
                # Potentially clear the token so it's refreshed on next attempt
                self.token = None 
                settings.ALARIC_ACCESS_TOKEN = None
            self.is_connected = False
        except websockets.exceptions.WebSocketException as e:
            print(f"WebSocket connection failed: {e}")
            self.is_connected = False
        except ConnectionRefusedError:
            print(f"Connection refused. Ensure the server is running and accessible at {self.ws_url}")
            self.is_connected = False
        except Exception as e:
            print(f"An unexpected error occurred during connection: {e}")
            self.is_connected = False

    async def _listen(self):
        """Listens for incoming messages from the WebSocket."""
        if not self.websocket or not self.is_connected:
            print("Cannot listen, not connected.")
            return

        print("Listening for messages...")
        try:
            async for message in self.websocket:
                # print(f"Received raw message: {message}") # For debugging
                try:
                    data = json.loads(message)
                    if self.message_handler_callback:
                        await self.message_handler_callback(data)
                    else:
                        print(f"Received data: {data}") # Default handler
                except json.JSONDecodeError:
                    print(f"Received non-JSON message: {message}")
        except websockets.exceptions.ConnectionClosedError as e:
            print(f"Connection closed by server (error): {e.code} {e.reason}")
            self.is_connected = False
        except websockets.exceptions.ConnectionClosedOK:
            print("Connection closed by server (OK).")
            self.is_connected = False
        except Exception as e:
            print(f"Error during listening: {e}")
            self.is_connected = False
        finally:
            await self.close() # Ensure connection is marked as closed

    async def send_message(self, message_dict):
        """Sends a JSON message to the WebSocket server."""
        if not self.websocket or not self.is_connected:
            print("Cannot send message, not connected.")
            return False
        
        try:
            json_message = json.dumps(message_dict)
            # print(f"Sending message: {json_message}") # For debugging
            await self.websocket.send(json_message)
            return True
        except websockets.exceptions.ConnectionClosed:
            print("Cannot send message, connection is closed.")
            self.is_connected = False
            return False
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    async def close(self):
        """Closes the WebSocket connection."""
        if self.websocket and self.is_connected:
            print("Closing WebSocket connection...")
            try:
                await self.websocket.close()
            except Exception as e:
                print(f"Error while closing WebSocket: {e}")
            finally:
                self.websocket = None
                self.is_connected = False
                print("WebSocket connection closed.")
        elif not self.is_connected:
            pass # Already closed or was never open
        else:
            print("No active connection to close.")
            
    def set_message_handler(self, callback):
        """Sets a callback function to handle incoming messages.
        The callback should be an async function that accepts one argument (the message data).
        """
        self.message_handler_callback = callback

# Example Usage (for testing this module directly)
async def default_message_processor(message):
    """A simple async callback to process messages."""
    print(f"Default Processor Received: {message}")
    # Here you would add logic to route messages to different handlers
    # based on messageType or other fields.

async def main_test():
    # --- IMPORTANT ---
    # Before running this test, ensure your ALARIC_CLIENT_ID and ALARIC_CLIENT_SECRET 
    # are correctly set in hammerib/config/settings.py for token acquisition to work.
    # Also ensure the Alaric UAT/Prod environment is accessible.
    
    client = AlaricWebsocketClient()
    client.set_message_handler(default_message_processor)

    await client.connect()

    if client.is_connected:
        # Example: Send a Get Balances request (as per Alaric docs section 5.1)
        # This is just a placeholder. You'll need to construct valid messages.
        get_balances_request = {
            "reqId": "test01",
            "messageType": "getbalances",
            "account": "YOUR_TEST_ACCOUNT" # Replace with a valid test account
        }
        # await client.send_message(get_balances_request)

        # Keep the connection alive for a while to receive messages
        # In a real app, this would be part of a larger event loop.
        try:
            # Keep running for 60 seconds or until connection drops
            for _ in range(60): 
                if not client.is_connected:
                    break
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Test interrupted by user.")
        finally:
            await client.close()
    else:
        print("Failed to connect to Alaric WebSocket. Exiting test.")

if __name__ == "__main__":
    print("Starting Alaric WebSocket Client Test...")
    try:
        asyncio.run(main_test())
    except KeyboardInterrupt:
        print("Alaric client test manually terminated.")
    print("Alaric WebSocket Client Test Finished.") 