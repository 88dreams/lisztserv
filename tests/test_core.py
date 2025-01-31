"""
Tests for the core functionality of lisztserv.
"""
import os
import json
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import aiohttp
import spotipy
from openai import AsyncOpenAI

from lisztserv.core import (
    ClientManager, RateLimiter, FileHandler,
    get_packaged_browser_path, clean_html_content,
    user_message, send_progress,
    PlaylistManager, SpotifySearchManager,
    PlaywrightCrawler, WebContentExtractor,
    ContentProcessor, process_with_gpt,
    scan_webpage, create_playlist
)

# ClientManager Tests
@pytest.mark.asyncio
async def test_client_manager_spotify():
    """Test Spotify client initialization and singleton behavior."""
    with patch('spotipy.Spotify') as mock_spotify:
        # First call should create new instance
        client1 = await ClientManager.get_spotify()
        mock_spotify.assert_called_once()
        
        # Second call should return same instance
        client2 = await ClientManager.get_spotify()
        assert mock_spotify.call_count == 1
        assert client1 == client2

@pytest.mark.asyncio
async def test_client_manager_openai():
    """Test OpenAI client initialization and singleton behavior."""
    with patch('openai.AsyncOpenAI') as mock_openai:
        # First call should create new instance
        client1 = await ClientManager.get_openai()
        mock_openai.assert_called_once()
        
        # Second call should return same instance
        client2 = await ClientManager.get_openai()
        assert mock_openai.call_count == 1
        assert client1 == client2

@pytest.mark.asyncio
async def test_client_manager_session():
    """Test aiohttp session initialization and singleton behavior."""
    session1 = await ClientManager.get_session()
    assert isinstance(session1, aiohttp.ClientSession)
    assert not session1.closed
    
    # Second call should return same session
    session2 = await ClientManager.get_session()
    assert session1 == session2
    
    # Test cleanup
    await ClientManager.cleanup()
    assert session1.closed

# RateLimiter Tests
@pytest.mark.asyncio
async def test_rate_limiter():
    """Test rate limiting functionality."""
    limiter = RateLimiter(max_calls=2, time_period=1)
    
    # Test function to be rate limited
    @limiter
    async def test_func():
        return datetime.now()
    
    # First two calls should be immediate
    result1 = await test_func()
    result2 = await test_func()
    assert (result2 - result1).total_seconds() < 0.1
    
    # Third call should be delayed
    start = datetime.now()
    result3 = await test_func()
    duration = (datetime.now() - start).total_seconds()
    assert duration >= 1.0

@pytest.mark.asyncio
async def test_rate_limiter_caching():
    """Test rate limiter's caching functionality."""
    limiter = RateLimiter(max_calls=2, time_period=1)
    counter = 0
    
    @limiter
    async def cached_func(param):
        nonlocal counter
        counter += 1
        return counter
    
    # First call should increment counter
    result1 = await cached_func("test")
    assert result1 == 1
    
    # Second call with same params should return cached result
    result2 = await cached_func("test")
    assert result2 == 1
    assert counter == 1  # Counter should not increment due to cache

# FileHandler Tests
@pytest.mark.asyncio
async def test_file_handler(tmp_path):
    """Test FileHandler's save and load operations."""
    file_path = tmp_path / "test_data.json"
    handler = FileHandler(str(file_path))
    
    # Test data
    test_data = [{"key": "value"}, {"test": "data"}]
    
    # Test save
    await handler.save(test_data)
    assert file_path.exists()
    
    # Test load
    loaded_data = await handler.load()
    assert loaded_data == test_data
    
    # Test loading non-existent file
    non_existent = FileHandler(str(tmp_path / "nonexistent.json"))
    empty_data = await non_existent.load()
    assert empty_data == []

@pytest.mark.asyncio
async def test_file_handler_error_handling(tmp_path):
    """Test FileHandler's error handling."""
    file_path = tmp_path / "test_data.json"
    handler = FileHandler(str(file_path))
    
    # Test saving invalid data
    with pytest.raises(Exception):
        await handler.save([{"key": object()}])  # Object is not JSON serializable
    
    # Test loading corrupted file
    file_path.write_text("invalid json")
    with pytest.raises(Exception):
        await handler.load()

# Browser Path Tests
def test_get_packaged_browser_path():
    """Test browser path resolution."""
    with patch('sys.platform', 'win32'):
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=['chromium_headless_shell-1148']):
                path = get_packaged_browser_path()
                assert 'headless_shell.exe' in path
                assert 'chrome-win' in path

# Utility Function Tests
def test_clean_html_content():
    """Test HTML content cleaning functionality."""
    html = """
    <html>
        <body>
            <h1>Title</h1>
            <p>Text with <script>alert('test')</script> and <style>.test{color:red;}</style></p>
            <div>More text</div>
        </body>
    </html>
    """
    cleaned = clean_html_content(html)
    assert '<script>' not in cleaned
    assert '<style>' not in cleaned
    assert 'Title' in cleaned
    assert 'More text' in cleaned

def test_user_message():
    """Test user message formatting."""
    with patch('logging.getLogger') as mock_logger:
        user_message("Test message")
        mock_logger.return_value.info.assert_called_once()

@pytest.mark.asyncio
async def test_send_progress():
    """Test progress sending functionality."""
    with patch('lisztserv.core.progress_queue.put_nowait') as mock_put:
        send_progress(50, "Halfway there")
        mock_put.assert_called_once_with((50, "Halfway there"))

# Setup and Teardown
@pytest.fixture(autouse=True)
async def cleanup_after_tests():
    """Cleanup resources after each test."""
    yield
    await ClientManager.cleanup() 

# PlaylistManager Tests
@pytest.mark.asyncio
async def test_playlist_manager():
    """Test playlist creation and track addition."""
    with patch('lisztserv.core.ClientManager.get_spotify') as mock_get_spotify:
        # Mock Spotify client
        mock_spotify = AsyncMock()
        mock_spotify.user_playlist_create.return_value = {"id": "test_playlist_id"}
        mock_spotify.playlist_add_items.return_value = None
        mock_get_spotify.return_value = mock_spotify
        
        # Initialize manager
        manager = PlaylistManager()
        
        # Test playlist creation
        playlist_id = await manager.create_playlist("Test Playlist", "Test Description")
        assert playlist_id == "test_playlist_id"
        mock_spotify.user_playlist_create.assert_called_once()
        
        # Test adding tracks
        track_ids = ["track1", "track2", "track3"]
        await manager.add_tracks_to_playlist(playlist_id, track_ids)
        mock_spotify.playlist_add_items.assert_called_once_with(
            playlist_id, track_ids[:100]  # Tests chunking behavior
        )

@pytest.mark.asyncio
async def test_playlist_manager_progress():
    """Test playlist manager progress reporting."""
    manager = PlaylistManager()
    progress_callback = Mock()
    manager.set_progress_callback(progress_callback)
    
    # Test progress updates
    manager._update_progress(50, "Test progress")
    progress_callback.assert_called_once_with(50, "Test progress")

# SpotifySearchManager Tests
@pytest.mark.asyncio
async def test_spotify_search_manager():
    """Test Spotify search functionality."""
    with patch('lisztserv.core.ClientManager.get_spotify') as mock_get_spotify:
        # Mock Spotify client
        mock_spotify = AsyncMock()
        mock_spotify.album.return_value = {
            "id": "test_album_id",
            "name": "Test Album",
            "artists": [{"name": "Test Artist"}]
        }
        mock_get_spotify.return_value = mock_spotify
        
        # Initialize manager
        manager = SpotifySearchManager()
        
        # Test album info retrieval
        album_info = await manager.get_album_info("test_album_id")
        assert album_info["id"] == "test_album_id"
        assert album_info["name"] == "Test Album"
        mock_spotify.album.assert_called_once_with("test_album_id")

@pytest.mark.asyncio
async def test_spotify_link_scanning():
    """Test Spotify link extraction from content."""
    manager = SpotifySearchManager()
    content = """
    Check out this album: https://open.spotify.com/album/123456
    And this one: https://open.spotify.com/album/789012
    Not a Spotify link: https://example.com
    """
    
    links = await manager.scan_spotify_links(content)
    assert len(links) == 2
    assert "123456" in links
    assert "789012" in links

# PlaywrightCrawler Tests
@pytest.mark.asyncio
async def test_playwright_crawler():
    """Test web page crawling functionality."""
    with patch('playwright.async_api.async_playwright') as mock_playwright:
        # Mock browser and context
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        
        mock_playwright.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        mock_page.content.return_value = "<html><body>Test content</body></html>"
        
        async with PlaywrightCrawler() as crawler:
            content = await crawler.process_url("https://example.com")
            assert "Test content" in content
            
            # Verify browser setup
            mock_playwright.return_value.__aenter__.return_value.chromium.launch.assert_called_once()
            mock_browser.new_context.assert_called_once()
            mock_context.new_page.assert_called_once()

# WebContentExtractor Tests
@pytest.mark.asyncio
async def test_web_content_extractor():
    """Test web content extraction."""
    with patch('playwright.async_api.async_playwright') as mock_playwright:
        # Mock page content
        mock_page = AsyncMock()
        mock_page.content.return_value = """
        <html>
            <body>
                <article>
                    <h1>Test Article</h1>
                    <p>Test content with a Spotify link: 
                       https://open.spotify.com/album/123456</p>
                </article>
            </body>
        </html>
        """
        
        # Setup mock browser chain
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_playwright.return_value.__aenter__.return_value.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page
        
        # Test extraction
        extractor = WebContentExtractor()
        content = await extractor.extract_content("https://example.com")
        
        assert "Test Article" in content
        assert "Test content" in content
        assert "https://open.spotify.com/album/123456" in content

# ContentProcessor Tests
@pytest.mark.asyncio
async def test_content_processor():
    """Test content processing workflow."""
    with patch('lisztserv.core.WebContentExtractor') as mock_extractor, \
         patch('lisztserv.core.process_with_gpt') as mock_gpt, \
         patch('lisztserv.core.SpotifySearchManager') as mock_spotify_search:
        
        # Mock dependencies
        mock_extractor.return_value.__aenter__.return_value.extract_content.return_value = "Test content"
        mock_gpt.return_value = "Processed content"
        mock_spotify_search.return_value.scan_spotify_links.return_value = ["album1", "album2"]
        
        processor = ContentProcessor()
        async with processor:
            await processor.process_url("https://example.com", "output.json")
            
            # Verify processing flow
            mock_extractor.return_value.__aenter__.return_value.extract_content.assert_called_once()
            mock_gpt.assert_called_once()
            mock_spotify_search.return_value.scan_spotify_links.assert_called_once()

@pytest.mark.asyncio
async def test_process_with_gpt():
    """Test GPT content processing."""
    with patch('lisztserv.core.ClientManager.get_openai') as mock_get_openai:
        # Mock OpenAI client
        mock_openai = AsyncMock()
        mock_openai.chat.completions.create.return_value.choices[0].message.content = "Processed content"
        mock_get_openai.return_value = mock_openai
        
        result = await process_with_gpt("Test content")
        assert result == "Processed content"
        mock_openai.chat.completions.create.assert_called_once()

# Integration Tests
@pytest.mark.asyncio
async def test_full_workflow():
    """Test the complete workflow from URL to playlist creation."""
    with patch('lisztserv.core.WebContentExtractor') as mock_extractor, \
         patch('lisztserv.core.process_with_gpt') as mock_gpt, \
         patch('lisztserv.core.SpotifySearchManager') as mock_spotify_search, \
         patch('lisztserv.core.PlaylistManager') as mock_playlist_manager:
        
        # Mock all dependencies
        mock_extractor.return_value.__aenter__.return_value.extract_content.return_value = """
        Check out these albums:
        https://open.spotify.com/album/123
        https://open.spotify.com/album/456
        """
        mock_gpt.return_value = "Processed music content"
        mock_spotify_search.return_value.scan_spotify_links.return_value = ["123", "456"]
        mock_spotify_search.return_value.get_album_info.return_value = {
            "name": "Test Album",
            "artists": [{"name": "Test Artist"}]
        }
        mock_playlist_manager.return_value.create_playlist.return_value = "playlist_id"
        
        # Test full workflow
        result = await scan_webpage("https://example.com", "output.json")
        assert len(result) == 2
        assert all(album["id"] in ["123", "456"] for album in result)
        
        # Create playlist from results
        await create_playlist("output.json", "Test Playlist")
        mock_playlist_manager.return_value.create_playlist.assert_called_once()
        mock_playlist_manager.return_value.add_tracks_to_playlist.assert_called_once()

# Error Handling Tests
@pytest.mark.asyncio
async def test_error_handling():
    """Test error handling in various components."""
    # Test FileHandler error
    with pytest.raises(Exception):
        handler = FileHandler("/nonexistent/path/file.json")
        await handler.save([{"invalid": object()}])
    
    # Test PlaywrightCrawler error
    with patch('playwright.async_api.async_playwright') as mock_playwright:
        mock_playwright.return_value.__aenter__.return_value.chromium.launch.side_effect = Exception("Browser error")
        with pytest.raises(Exception):
            async with PlaywrightCrawler() as crawler:
                await crawler.process_url("https://example.com")
    
    # Test Spotify API error
    with patch('lisztserv.core.ClientManager.get_spotify') as mock_get_spotify:
        mock_get_spotify.side_effect = Exception("Spotify API error")
        manager = PlaylistManager()
        with pytest.raises(Exception):
            await manager.create_playlist("Test Playlist")

# Performance Tests
@pytest.mark.asyncio
async def test_rate_limiter_performance():
    """Test rate limiter under load."""
    limiter = RateLimiter(max_calls=10, time_period=1)
    
    @limiter
    async def test_func():
        return datetime.now()
    
    # Test multiple concurrent calls
    tasks = [test_func() for _ in range(20)]
    start = datetime.now()
    results = await asyncio.gather(*tasks)
    duration = (datetime.now() - start).total_seconds()
    
    # Should take at least 1 second due to rate limiting
    assert duration >= 1.0
    # Should complete within reasonable time
    assert duration < 3.0

@pytest.mark.asyncio
async def test_concurrent_file_operations(tmp_path):
    """Test concurrent file operations."""
    file_path = tmp_path / "concurrent_test.json"
    handler = FileHandler(str(file_path))
    
    # Test concurrent saves
    async def save_operation(data):
        await handler.save(data)
        return await handler.load()
    
    tasks = [save_operation([{"id": i}]) for i in range(5)]
    results = await asyncio.gather(*tasks)
    
    # Verify data integrity
    final_data = await handler.load()
    assert len(final_data) == 1  # Should contain only the last save
    assert isinstance(final_data, list) 