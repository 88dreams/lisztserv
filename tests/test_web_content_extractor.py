"""
Tests for the WebContentExtractor component.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from playwright.async_api import Error as PlaywrightError
import asyncio

from lisztserv.utils.web_extractor import WebContentExtractor

@pytest.fixture
def mock_playwright_factory():
    """Create a mock Playwright factory."""
    async def factory():
        mock = AsyncMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.chromium = AsyncMock()
        return mock
    return factory

@pytest.fixture
def mock_page():
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.goto = AsyncMock()
    page.content = AsyncMock(return_value="<html><body><article>Test Content</article></body></html>")
    page.query_selector = AsyncMock()
    page.close = AsyncMock()
    return page

@pytest.fixture
def mock_browser():
    """Create a mock Playwright browser."""
    browser = AsyncMock()
    browser.new_page = AsyncMock()
    browser.close = AsyncMock()
    return browser

@pytest.fixture
def web_extractor(mock_playwright_factory):
    """Create a WebContentExtractor instance with mocked dependencies."""
    return WebContentExtractor(playwright_factory=mock_playwright_factory)

@pytest.mark.asyncio
async def test_extract_content_success(web_extractor, mock_page, mock_browser):
    """Test successful content extraction."""
    test_url = "https://example.com/article"
    expected_content = "Test Content"
    
    # Setup mocks
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value=expected_content)
    mock_page.query_selector = AsyncMock(return_value=mock_element)
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    
    content = await web_extractor.extract_content(test_url)
    
    assert content == expected_content
    mock_page.goto.assert_called_once_with(test_url, wait_until="networkidle")
    mock_page.query_selector.assert_called()
    mock_page.close.assert_called_once()

@pytest.mark.asyncio
async def test_extract_content_timeout(web_extractor, mock_page, mock_browser):
    """Test content extraction with timeout."""
    test_url = "https://example.com/slow-article"
    
    # Setup mocks
    mock_page.goto = AsyncMock(side_effect=PlaywrightError("Timeout"))
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    
    with pytest.raises(PlaywrightError):
        await web_extractor.extract_content(test_url)
    
    mock_page.close.assert_called_once()

@pytest.mark.asyncio
async def test_extract_content_no_content(web_extractor, mock_page, mock_browser):
    """Test content extraction when no matching content is found."""
    test_url = "https://example.com/empty-article"
    
    # Setup mocks
    mock_page.query_selector = AsyncMock(return_value=None)
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    
    content = await web_extractor.extract_content(test_url)
    assert content == ""
    mock_page.close.assert_called_once()

@pytest.mark.asyncio
async def test_extract_content_multiple_selectors(web_extractor, mock_page, mock_browser):
    """Test content extraction with multiple content selectors."""
    test_url = "https://example.com/complex-article"
    expected_content = "Test Content"
    
    # Setup mocks
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value=expected_content)
    mock_page.query_selector = AsyncMock(side_effect=[None, mock_element])
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    
    content = await web_extractor.extract_content(test_url)
    assert content == expected_content
    assert mock_page.query_selector.call_count > 1
    mock_page.close.assert_called_once()

@pytest.mark.asyncio
async def test_extract_content_cleanup(web_extractor, mock_page, mock_browser):
    """Test proper cleanup of browser resources."""
    test_url = "https://example.com/article"
    
    # Setup mocks
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    web_extractor.playwright = AsyncMock()
    
    await web_extractor.extract_content(test_url)
    
    mock_page.close.assert_called_once()
    mock_browser.close.assert_called_once()
    web_extractor.playwright.stop.assert_called_once()

@pytest.mark.asyncio
async def test_extract_content_js_rendering(web_extractor, mock_page, mock_browser):
    """Test content extraction with JavaScript rendering."""
    test_url = "https://example.com/js-article"
    expected_content = "Dynamic Content"
    
    # Setup mocks
    mock_element = AsyncMock()
    mock_element.text_content = AsyncMock(return_value=expected_content)
    mock_page.query_selector = AsyncMock(return_value=mock_element)
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    
    # Setup playwright factory
    web_extractor.browser = mock_browser
    
    content = await web_extractor.extract_content(test_url)
    
    assert content == expected_content
    mock_page.goto.assert_called_once_with(test_url, wait_until="networkidle")
    mock_page.close.assert_called_once() 