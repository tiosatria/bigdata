"""
Phase 2: Batch Renderer
Renders collected data to high-quality images
Resolved: Fixes cropping issues by using absolute positioning offsets instead of transforms.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
import sys
from tqdm import tqdm

class FlowchartRenderer:
    """
    Renders flowchart data to high-quality images
    """

    def __init__(self,
                 input_file='output/flowcharts_raw_data.jsonl',
                 output_dir='output/flowcharts',
                 quality=100,
                 scale=2.0,
                 max_concurrent=4,
                 margin=32,
                 debug=False,
                 debug_dir='output/debug_render'):

        self.input_file = input_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.quality = quality
        self.scale = scale
        self.max_concurrent = max_concurrent
        self.margin = int(margin)

        self.debug = bool(debug)
        self.debug_dir = Path(debug_dir)
        if self.debug:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

        self.rendered_count = 0
        self.failed_count = 0
        self.skipped_count = 0

    def load_data(self):
        data = []
        with open(self.input_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return data

    async def render_single(self, page, item):
        try:
            filename = item.get('title_clean', None) or item.get('title', 'Untitled')
            try:
                chart_id = item['url'].split('/view/')[1].split('/')[0]
                filename = f"{chart_id}.png"
                filepath = self.output_dir / filename
            except:
                # expected no guid found, use original filename instead
                pass

            if filepath.exists():
                self.skipped_count += 1
                return {'status': 'skipped', 'filename': filename}

            # Build complete HTML page
            html_content = self.build_html(item)
            await page.set_content(html_content, wait_until='networkidle')
            await page.wait_for_timeout(1000)

            # --- CORE FIX: ROBUST DOM MANIPULATION ---
            # Instead of transforming, we strip layout and reposition absolutely
            metrics = await page.evaluate('''(opts) => {
                const { marginPx } = opts;
                const result = { status: 'ok' };
                const canvas = document.querySelector('#designer_canvas');
                if (!canvas) return { status: 'no-canvas' };

                // 1. RESET CANVAS LAYOUT
                // Clear any existing transforms or margins that mess up measurements
                canvas.style.transform = 'none';
                canvas.style.margin = '0';
                canvas.style.left = '0';
                canvas.style.top = '0';
                canvas.style.position = 'absolute'; 
                
                // Ensure we can read everything
                canvas.style.overflow = 'visible';

                // 2. MEASURE CONTENT (Global Coordinates)
                // We iterate all visible shapes to find the true bounding box relative to the document
                const selector = ['.shape_box', '.linker_box', '.text_canvas', 'img', 'svg', '[data-shape]'].join(', ');
                const nodes = Array.from(canvas.querySelectorAll(selector));
                
                let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
                let foundNodes = 0;

                nodes.forEach(n => {
                    // Get rect relative to viewport/document (since we reset canvas to 0,0)
                    const r = n.getBoundingClientRect();
                    if (r.width === 0 && r.height === 0) return; // skip invisible
                    
                    // Expand bounds
                    if (r.left < minX) minX = r.left;
                    if (r.top < minY) minY = r.top;
                    if (r.right > maxX) maxX = r.right;
                    if (r.bottom > maxY) maxY = r.bottom;
                    foundNodes++;
                });

                // Fallback if empty
                if (foundNodes === 0) {
                    minX = 0; minY = 0;
                    maxX = 100; maxY = 100;
                }

                // 3. CALCULATE DIMENSIONS
                const contentW = Math.ceil(maxX - minX);
                const contentH = Math.ceil(maxY - minY);
                
                // 4. CREATE WRAPPER (The "Camera Frame")
                // We create a new container exactly the size of the content + margin
                let wrapper = document.getElementById('render_container');
                if (!wrapper) {
                    wrapper = document.createElement('div');
                    wrapper.id = 'render_container';
                    document.body.innerHTML = ''; // Clear body to remove scrollbars/padding
                    document.body.appendChild(wrapper);
                }

                wrapper.style.width = (contentW + marginPx * 2) + 'px';
                wrapper.style.height = (contentH + marginPx * 2) + 'px';
                wrapper.style.background = 'white';
                wrapper.style.position = 'relative';
                wrapper.style.overflow = 'hidden'; // Clean clip

                // 5. POSITION CANVAS INSIDE
                // We move the canvas so the content (minX, minY) sits exactly at (margin, margin)
                wrapper.appendChild(canvas);
                
                // Calculation: 
                // We want the point (minX) to be at (margin).
                // So we shift left by (minX - margin).
                canvas.style.position = 'absolute';
                canvas.style.left = -(minX - marginPx) + 'px';
                canvas.style.top = -(minY - marginPx) + 'px';
                
                // Force canvas size to be large enough to not clip internally
                canvas.style.width = Math.max(2000, contentW + minX + 1000) + 'px';
                canvas.style.height = Math.max(2000, contentH + minY + 1000) + 'px';

                return { minX, minY, contentW, contentH };
            }''', {"marginPx": self.margin})

            # Take screenshot of the perfectly sized wrapper
            wrapper = await page.query_selector('#render_container')
            if wrapper:
                await wrapper.screenshot(path=str(filepath), type='png', scale='device')
            else:
                # Fallback
                await page.screenshot(path=str(filepath), full_page=True, type='png', scale='device')

            self.rendered_count += 1
            return {'status': 'success', 'filename': filename}

        except Exception as e:
            self.failed_count += 1
            return {'status': 'failed', 'error': str(e), 'filename': filename}

    def build_html(self, item):
        # (This function remains largely the same, but we ensure CSS doesn't fight us)
        width = item.get('width', '1050px').replace('px', '')
        height = item.get('height', '1500px').replace('px', '')

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        /* Reset base styles */
        html, body {{ margin: 0; padding: 0; background: white; }}
        
        /* Ensure critical visibility */
        .shape_box, .linker_box, .text_canvas {{
            position: absolute !important;
            box-sizing: border-box;
            overflow: visible !important;
        }}
        .shape_box img, .shape_box canvas, .shape_box svg {{
            width: 100% !important;
            height: 100% !important;
            display: block;
        }}
        
        /* Inject Scraped Styles */
        {' '.join(item.get('inline_styles', []))}
    </style>
</head>
<body>
    {item.get('full_html', item.get('canvas_html', ''))}
</body>
</html>
"""
        return html

    async def render_batch(self, items):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=self.scale,
            )
            pages = [await context.new_page() for _ in range(self.max_concurrent)]

            pbar = tqdm(total=len(items), desc="Rendering flowcharts")
            for i in range(0, len(items), self.max_concurrent):
                batch = items[i:i + self.max_concurrent]
                tasks = []
                for idx, item in enumerate(batch):
                    if idx < len(pages):
                        tasks.append(self.render_single(pages[idx], item))

                results = await asyncio.gather(*tasks)
                pbar.update(len(batch))
            pbar.close()
            await browser.close()

    async def run(self):
        print(f"Render Scale: {self.scale}x")
        items = self.load_data()
        await self.render_batch(items)
        print(f"Done. Rendered: {self.rendered_count}, Failed: {self.failed_count}")

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='output/flowcharts_raw_data.jsonl')
    parser.add_argument('--output', default='output/flowcharts')
    parser.add_argument('--scale', type=float, default=2.0)
    parser.add_argument('--concurrent', type=int, default=4)
    args = parser.parse_args()

    renderer = FlowchartRenderer(
        input_file=args.input,
        output_dir=args.output,
        scale=args.scale,
        max_concurrent=args.concurrent
    )
    await renderer.run()

if __name__ == '__main__':
    asyncio.run(main())