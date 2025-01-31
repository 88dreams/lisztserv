"""
Web content extraction functionality
"""
import aiohttp
import logging
from typing import Optional, Tuple, Any
from bs4 import BeautifulSoup
from aiohttp import ClientError, ClientTimeout
from playwright.async_api import async_playwright, TimeoutError

class WebContentExtractor:
    def __init__(self, playwright_factory=None):
        self.logger = logging.getLogger('spot-debug')
        self.browser = None
        self.playwright = None
        self._playwright_factory = playwright_factory or async_playwright
    
    async def get_browser(self):
        """Initialize and return a browser instance."""
        if not self.browser:
            self.playwright = await self._playwright_factory().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
        return self.browser
    
    async def cleanup(self):
        """Clean up browser resources."""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

    def user_message(self, message: str):
        """Log user messages."""
        self.logger.info(message)
    
    async def extract_content(self, url: str) -> str:
        """Extract content from a webpage."""
        page = None
        try:
            browser = await self.get_browser()
            page = await browser.new_page()
            
            # Navigate to page and wait for content
            await page.goto(url, wait_until="networkidle")
            
            # Try different selectors for content
            selectors = ['article', 'main', '[role="main"]', '.content', '#content', 'body']
            content = None
            
            for selector in selectors:
                element = await page.query_selector(selector)
                if element:
                    content = await element.text_content()
                    if content and content.strip():
                        break
            
            return content.strip() if content else ""
                
        except TimeoutError as e:
            self.logger.error(f"Timeout extracting content: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error extracting content: {e}")
            return ""
        finally:
            if page:
                await page.close()
            await self.cleanup() 