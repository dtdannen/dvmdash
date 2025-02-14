#!/usr/bin/env python3
import asyncio
import argparse
import os
import signal
import sys
from typing import Dict, Optional
from loguru import logger
from dotenv import load_dotenv
from production_components import (
    BetterStackLogger,
    LandingPageService,
)

# Load environment variables
load_dotenv()

# Global shutdown event
shutdown_event = asyncio.Event()

class DeploymentManager:
    """Manages the landing page deployment process"""
    
    def __init__(self):
        # Validate required environment variables
        self.do_token = os.getenv("DO_TOKEN")
        if not self.do_token:
            raise ValueError("DO_TOKEN environment variable is required")
            
        self.project_id = os.getenv("DO_PROJECT_ID")
        self.project_name = os.getenv("PROJECT_NAME", "dvmdash-prod")
        self.betterstack_token = os.getenv("BETTERSTACK_TOKEN")
        if not self.betterstack_token:
            raise ValueError("BETTERSTACK_TOKEN environment variable is required")
            
        # Initialize components
        self.betterstack = BetterStackLogger(self.project_name)
        self.landing_page = None
        
    async def deploy(self) -> bool:
        """Deploy the landing page"""
        try:
            logger.info("Starting Landing Page Deployment")
            
            # Create log source
            logs_token = self.betterstack.create_source("landing-page")
            if not logs_token:
                raise ValueError("Failed to create landing-page log source")
                
            logger.info("Successfully created log source")
            
            # Initialize and deploy landing page service
            self.landing_page = LandingPageService(
                self.do_token,
                self.project_name
            )
            
            # Deploy landing page
            logger.info("Deploying landing page...")
            await self.landing_page.deploy(
                branch="main",
                logs_token=logs_token,
                project_id=self.project_id
            )
            
            logger.info("Landing page deployment completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                try:
                    error_detail = e.response.json()
                    logger.error(f"API Response: {error_detail}")
                    if "error" in error_detail:
                        logger.error(f"Error message: {error_detail['error'].get('message', '')}")
                        logger.error(f"Error code: {error_detail['error'].get('code', '')}")
                except:
                    logger.error(f"Raw response: {e.response.text}")
            await self.cleanup()
            return False
            
    async def cleanup(self):
        """Clean up all resources on failure"""
        logger.info("Cleaning up resources...")
        
        if self.landing_page:
            await self.landing_page.cleanup()
            
        if hasattr(self, 'betterstack'):
            self.betterstack.delete_sources()

async def main():
    """Main deployment function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Deploy DVM Dashboard landing page')
    parser.add_argument('--branch', default='main', help='Git branch to deploy')
    args = parser.parse_args()
    
    # Setup signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))
    
    deployment = DeploymentManager()
    try:
        if not await deployment.deploy():
            logger.error("Landing page deployment failed")
            sys.exit(1)
            
        logger.info("Landing page deployment completed successfully!")
        
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        await deployment.cleanup()
        sys.exit(1)
        
async def shutdown(sig):
    """Handle shutdown gracefully"""
    logger.info(f"Received exit signal {sig.name}...")
    shutdown_event.set()

if __name__ == "__main__":
    asyncio.run(main())
