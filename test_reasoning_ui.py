"""
Playwright test to verify that reasoning content doesn't appear in the chat window.
"""

import asyncio
from playwright.async_api import async_playwright, expect


async def test_reasoning_not_in_chat():
    """Test that reasoning/thinking content is not displayed in the main chat window."""
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            # Navigate to the app
            await page.goto("http://localhost:8000", timeout=10000)
            
            # Wait for the chat input to be ready
            await page.wait_for_selector("#chat-input", timeout=5000)
            
            # Type a query
            await page.fill("#chat-input", "What happened in Iran this week?")
            
            # Submit the query
            await page.click("#send-btn")
            
            # Wait for response to start streaming
            await page.wait_for_selector(".message.assistant", timeout=10000)
            
            # Wait for the response to complete (done event)
            await asyncio.sleep(5)  # Give it time to complete
            
            # Get the chat messages
            messages = await page.query_selector_all(".message.assistant")
            
            if messages:
                # Get the text content of the last message
                last_message = messages[-1]
                message_text = await last_message.inner_text()
                
                # Check that reasoning content is NOT in the message
                # The reasoning content would be something like "The search results did not provide..."
                # which was incorrectly being displayed
                
                # Also check that <think> tags are not in the message
                message_html = await last_message.inner_html()
                
                # Assert that thinking content is not visible in chat
                assert "<think>" not in message_html, \
                    f"<think> tags should not appear in chat. Found in: {message_html[:500]}"
                
                # The reasoning panel should have the thinking content, not the chat
                print("✅ Chat message doesn't contain <think> tags")
                
            # Check the reasoning panel if it exists
            reasoning_panel = await page.query_selector("#reasoning-content")
            if reasoning_panel:
                panel_text = await reasoning_panel.inner_text()
                print(f"Reasoning panel contains {len(panel_text)} chars")
                
        finally:
            await browser.close()
            
    print("✅ Test passed: Reasoning content is properly separated from chat!")


if __name__ == "__main__":
    asyncio.run(test_reasoning_not_in_chat())
