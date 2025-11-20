"""
Test script to verify iframe canvas extraction from ProcessOn
Run this before running the full spider to verify the approach works
"""

import asyncio
from playwright.async_api import async_playwright
import os


async def test_processon_extraction():
    """Test extracting canvas from ProcessOn page"""

    test_url = "https://www.processon.com/view/542835f90cf2e6eabf100260"
    output_dir = "./test_output"
    os.makedirs(output_dir, exist_ok=True)

    print(f"Testing URL: {test_url}")
    print("=" * 60)

    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1400, 'height': 2000}
        )
        page = await context.new_page()

        try:
            # Navigate to page
            print("1. Navigating to page...")
            await page.goto(test_url, wait_until='networkidle', timeout=60000)
            print("   ✓ Page loaded")

            # Wait for iframe
            print("\n2. Waiting for iframe...")
            await page.wait_for_selector('iframe', timeout=30000)
            print("   ✓ Iframe element found")

            # Additional wait for content
            await page.wait_for_timeout(3000)

            # Get iframe
            print("\n3. Accessing iframe content...")
            iframe_element = await page.query_selector('iframe')
            if not iframe_element:
                print("   ✗ Iframe element not found!")
                return False

            # Get iframe src
            iframe_src = await iframe_element.get_attribute('src')
            print(f"   Iframe src: {iframe_src}")

            # Get iframe content frame
            iframe = await iframe_element.content_frame()
            if not iframe:
                print("   ✗ Could not access iframe content!")
                return False
            print("   ✓ Iframe content accessed")

            # Wait for canvas in iframe
            print("\n4. Waiting for canvas in iframe...")
            try:
                await iframe.wait_for_selector('#designer_canvas', timeout=30000)
                print("   ✓ Canvas found in iframe")
            except Exception as e:
                print(f"   ✗ Canvas not found: {e}")

                # Debug: Check what's in the iframe
                print("\n   Debug: Checking iframe content...")
                iframe_html = await iframe.content()
                print(f"   Iframe HTML length: {len(iframe_html)} characters")

                # Check if there's a body
                body = await iframe.query_selector('body')
                if body:
                    body_text = await body.inner_text()
                    print(f"   Body text: {body_text[:200]}...")

                return False

            # Additional wait for rendering
            await page.wait_for_timeout(2000)

            # Get canvas info
            print("\n5. Extracting canvas information...")
            canvas_info = await iframe.evaluate('''() => {
                const canvas = document.querySelector('#designer_canvas');
                if (canvas) {
                    const style = window.getComputedStyle(canvas);
                    return {
                        width: style.width,
                        height: style.height,
                        shapeCount: document.querySelectorAll('.shape_box').length,
                        innerHTML: canvas.innerHTML.substring(0, 200)
                    };
                }
                return null;
            }''')

            if canvas_info:
                print(f"   Canvas width: {canvas_info['width']}")
                print(f"   Canvas height: {canvas_info['height']}")
                print(f"   Shape count: {canvas_info['shapeCount']}")
                print(f"   ✓ Canvas info extracted")
            else:
                print("   ✗ Could not extract canvas info")

            # Take screenshot of iframe
            print("\n6. Taking screenshot...")
            screenshot_path = os.path.join(output_dir, "test_flowchart.png")
            await iframe_element.screenshot(path=screenshot_path)
            print(f"   ✓ Screenshot saved to: {screenshot_path}")

            # Also try screenshot of just the canvas
            print("\n7. Taking canvas-only screenshot...")
            canvas_element = await iframe.query_selector('#designer_canvas')
            if canvas_element:
                canvas_screenshot_path = os.path.join(output_dir, "test_canvas_only.png")
                await canvas_element.screenshot(path=canvas_screenshot_path)
                print(f"   ✓ Canvas screenshot saved to: {canvas_screenshot_path}")

            print("\n" + "=" * 60)
            print("✓ Test completed successfully!")
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
    print("ProcessOn Iframe Canvas Extraction Test")
    print("=" * 60)

    success = asyncio.run(test_processon_extraction())

    if success:
        print("\n✓ Test passed! You can now run the full spider.")
        print("\nNext steps:")
        print("  1. Run: scrapy crawl processon")
        print("  2. Check output in: ./output/flowcharts/")
    else:
        print("\n✗ Test failed. Check the error messages above.")
        print("\nPossible issues:")
        print("  - Website structure changed")
        print("  - Need to handle authentication/login")
        print("  - JavaScript not fully loaded")
        print("  - Network issues")