# hammerib/hib_core/hib_main.py

import asyncio
import logging
import os
from typing import Dict
import json

from ..alaric_api.client import HammerClient
from ..ib_api.client import IBClient
from ..strategies.basic_strategy import BasicStrategy
from .orchestrator import TradingOrchestrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingSystem:
    def __init__(self, config_path: str = "config/config.json"):
        self.logger = logging.getLogger(__name__)
        self.config = self._load_config(config_path)
        self.orchestrator = TradingOrchestrator()
        self.strategies: Dict[str, BasicStrategy] = {}

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {str(e)}")
            raise

    async def initialize(self):
        """Initialize the trading system"""
        try:
            # Initialize Hammer API client
            hammer_config = self.config.get('hammer_api', {})
            self.orchestrator.hammer_client = HammerClient(
                api_key=hammer_config.get('api_key'),
                api_secret=hammer_config.get('api_secret'),
                base_url=hammer_config.get('base_url')
            )

            # Initialize IBKR client
            ib_config = self.config.get('ibkr', {})
            self.orchestrator.ib_client = IBClient()
            self.orchestrator.ib_client.connect_and_start(
                host=ib_config.get('host', '127.0.0.1'),
                port=ib_config.get('port', 7497),
                client_id=ib_config.get('client_id', 1)
            )

            # Initialize strategies
            for strategy_config in self.config.get('strategies', []):
                strategy = BasicStrategy(strategy_config['name'])
                self.strategies[strategy_config['name']] = strategy

            # Initialize orchestrator
            await self.orchestrator.initialize()

            self.logger.info("Trading system initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize trading system: {str(e)}")
            raise

    async def start(self):
        """Start the trading system"""
        try:
            # Start strategies
            for strategy in self.strategies.values():
                strategy.start()

            # Start orchestrator
            await self.orchestrator.start()

        except Exception as e:
            self.logger.error(f"Error in trading system: {str(e)}")
            await self.shutdown()

    async def shutdown(self):
        """Shutdown the trading system"""
        try:
            # Stop strategies
            for strategy in self.strategies.values():
                strategy.stop()

            # Shutdown orchestrator
            await self.orchestrator.shutdown()

            self.logger.info("Trading system shutdown complete")
        except Exception as e:
            self.logger.error(f"Error during shutdown: {str(e)}")

async def main():
    """Main entry point"""
    try:
        # Create and start trading system
        system = TradingSystem()
        await system.initialize()
        await system.start()
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
        await system.shutdown()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        await system.shutdown()

if __name__ == "__main__":
    asyncio.run(main()) 