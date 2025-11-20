"""
Debug script to identify the correct iframe selector
"""

import asyncio
from playwright.async_api import async_playwright
import sys

# Fix Windows asyncio issue
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def debug_iframe_selectors():
    """Test different iframe selectors"""

    test_url = "https://www.processon.com/view/542835f90cf2e6eabf100260"

    print(f"Testing URL: {test_url}")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # Set to False to see browser
        context = await browser.new_context(viewport={'width': 1400, 'height': 2000})
        page = await context.new_page()

        try:
            print("\n1. Loading page...")
            await page.goto(test_url, wait_until='networkidle', timeout=60000)
            print("   ✓ Page loaded")

            # Wait a bit
            await page.wait_for_timeout(3000)

            print("\n2. Checking for iframes...")

            # Method 1: Count all iframes
            iframe_count = await page.evaluate('document.querySelectorAll("iframe").length')
            print(f"   Total iframes found: {iframe_count}")

            if iframe_count == 0:
                print("   ✗ No iframes found!")

                # Check if page requires login
                login_btn = await page.query_selector('.login_btn')
                if login_btn:
                    print("   ⚠ Login button detected - page might require authentication")

                # Print page title
                title = await page.title()
                print(f"   Page title: {title}")

                return False

            # Method 2: Try different selectors
            selectors_to_try = [
                'iframe',
                'iframe.mind_view',
                '.mind_view iframe',
                'div.mind_view iframe',
                'div.view_box iframe',
            ]

            print("\n3. Testing selectors...")
            working_selector = None

            for selector in selectors_to_try:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        print(f"   ✓ Works: {selector}")
                        if not working_selector:
                            working_selector = selector
                    else:
                        print(f"   ✗ Fails: {selector}")
                except Exception as e:
                    print(f"   ✗ Error with {selector}: {e}")

            if not working_selector:
                print("\n   ✗ No working selector found!")
                return False

            print(f"\n4. Using selector: {working_selector}")
            iframe_element = await page.query_selector(working_selector)

            # Get iframe info
            iframe_src = await iframe_element.get_attribute('src')
            iframe_class = await iframe_element.get_attribute('class')

            print(f"   Iframe src: {iframe_src}")
            print(f"   Iframe class: '{iframe_class}'")

            # Wait for iframe to populate if src is empty
            if not iframe_src or iframe_src == '':
                print("\n5. Waiting for iframe src to populate...")
                for i in range(10):
                    await page.wait_for_timeout(1000)
                    iframe_src = await iframe_element.get_attribute('src')
                    if iframe_src:
                        print(f"   ✓ Iframe src populated after {i + 1} seconds: {iframe_src}")
                        break
                else:
                    print("   ✗ Iframe src still empty after 10 seconds")

            # Try to access iframe content
            print("\n6. Accessing iframe content...")
            iframe = await iframe_element.content_frame()

            if not iframe:
                print("   ✗ Could not access iframe content!")
                return False

            print("   ✓ Iframe content accessible")

            # Check for canvas
            print("\n7. Checking for canvas in iframe...")
            try:
                await iframe.wait_for_selector('#designer_canvas', timeout=10000)
                print("   ✓ Canvas found!")

                # Get canvas info
                canvas_html = await iframe.evaluate('''() => {
                    const canvas = document.querySelector('#designer_canvas');
                    if (canvas) {
                        return {
                            id: canvas.id,
                            width: canvas.style.width,
                            height: canvas.style.height,
                            hasShapes: document.querySelectorAll('.shape_box').length > 0
                        };
                    }
                    return null;
                }''')

                print(f"   Canvas info: {canvas_html}")

            except Exception as e:
                print(f"   ✗ Canvas not found: {e}")

                # Debug: What's in the iframe?
                iframe_content = await iframe.content()
                print(f"   Iframe HTML length: {len(iframe_content)} chars")
                print(f"   First 500 chars:\n{iframe_content[:500]}")

                return False

            # Take screenshot
            print("\n8. Taking screenshot...")
            await iframe_element.screenshot(path='debug_screenshot.png')
            print("   ✓ Screenshot saved as debug_screenshot.png")

            print("\n" + "=" * 60)
            print("✓ SUCCESS!")
            print(f"Use this selector in your spider: '{working_selector}'")
            print("=" * 60)

            return True

        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()


if __name__ == '__main__':
    print("ProcessOn Iframe Selector Debug Tool")
    print("=" * 60)

    success = asyncio.run(debug_iframe_selectors())

    if not success:
        print("\n" + "=" * 60)
        print("TROUBLESHOOTING:")
        print("=" * 60)
        print("1. Check if the website requires login")
        print("2. Try running with headless=False to see what's happening")
        print("3. Check if website structure has changed")
        print("4. Verify network connectivity")
        print("5. Try a different URL from the same site")