import asyncio
import json
import logging
from typing import Dict, Optional, Callable
import websockets
from datetime import datetime

class WebSocketClient:
    def __init__(self, base_url: str):
        self.logger = logging.getLogger(__name__)
        self.base_url = base_url
        self.ws = None
        self.is_connected = False
        self.callbacks: Dict[str, Callable] = {}
        self.last_heartbeat = None

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.ws = await websockets.connect(self.base_url)
            self.is_connected = True
            self.logger.info("Connected to WebSocket")
            
            # Start heartbeat and message handling
            asyncio.create_task(self._heartbeat())
            asyncio.create_task(self._handle_messages())
            
        except Exception as e:
            self.logger.error(f"Failed to connect to WebSocket: {str(e)}")
            raise

    async def _heartbeat(self):
        """Send periodic heartbeat to keep connection alive"""
        while self.is_connected:
            try:
                await self.ws.send(json.dumps({"type": "heartbeat"}))
                self.last_heartbeat = datetime.now()
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
            except Exception as e:
                self.logger.error(f"Heartbeat failed: {str(e)}")
                await self.reconnect()

    async def _handle_messages(self):
        """Handle incoming WebSocket messages"""
        while self.is_connected:
            try:
                message = await self.ws.recv()
                data = json.loads(message)
                
                # Handle different message types
                msg_type = data.get("messageType")
                if msg_type in self.callbacks:
                    await self.callbacks[msg_type](data)
                else:
                    self.logger.warning(f"Unhandled message type: {msg_type}")
                    
            except Exception as e:
                self.logger.error(f"Error handling message: {str(e)}")
                await self.reconnect()

    async def reconnect(self):
        """Reconnect to WebSocket if connection is lost"""
        self.is_connected = False
        if self.ws:
            await self.ws.close()
        await asyncio.sleep(5)  # Wait before reconnecting
        await self.connect()

    async def send_message(self, message: Dict) -> None:
        """Send a message through WebSocket"""
        if not self.is_connected:
            raise ConnectionError("Not connected to WebSocket")

        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            self.logger.error(f"Failed to send message: {str(e)}")
            raise

    def register_callback(self, message_type: str, callback: Callable):
        """Register callback for specific message types"""
        self.callbacks[message_type] = callback

    async def close(self):
        """Close the WebSocket connection"""
        self.is_connected = False
        if self.ws:
            await self.ws.close()
        self.logger.info("Disconnected from WebSocket") 