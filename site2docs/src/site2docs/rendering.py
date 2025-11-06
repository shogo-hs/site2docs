"""Playwright を活用して HTML をレンダリングするユーティリティ。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import RenderConfig

try:  # pragma: no cover - optional dependency
    from playwright.async_api import async_playwright, Browser
except Exception:  # pragma: no cover - executed when dependency missing
    async_playwright = None  # type: ignore[assignment]
    Browser = object  # type: ignore[misc,assignment]


@dataclass(slots=True)
class RenderedPage:
    """HTML ページをレンダリングした結果。"""

    source_path: Path
    final_html: str
    final_url: str


class PageRenderer:
    """Playwright を用いて HTML ページをレンダリングし、利用不可の場合はフォールバックします。"""

    def __init__(self, config: RenderConfig) -> None:
        self._config = config

    async def render_many(self, paths: Iterable[Path]) -> list[RenderedPage]:
        """ローカル HTML ファイルを順番にレンダリングします。"""

        pages: list[RenderedPage] = []
        if async_playwright is None:
            for path in paths:
                pages.append(self._read_without_render(path))
            return pages

        async with async_playwright() as playwright:  # type: ignore[misc]
            browser = await playwright.chromium.launch()
            try:
                for path in paths:
                    pages.append(await self._render_single(browser, path))
            finally:
                await browser.close()
        return pages

    async def _render_single(self, browser: Browser, path: Path) -> RenderedPage:
        page = await browser.new_page()
        try:
            await page.goto(path.as_uri(), wait_until=self._config.wait_until, timeout=self._config.render_timeout * 1000)
            await self._auto_expand(page)
            html = await page.content()
            return RenderedPage(source_path=path, final_html=html, final_url=page.url)
        finally:
            await page.close()

    async def _auto_expand(self, page: "Browser") -> None:  # type: ignore[override]
        """スクロールやボタン操作で動的コンテンツを展開します。"""

        # Scroll behaviour
        for _ in range(self._config.max_scroll_iterations):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await asyncio.sleep(self._config.scroll_pause)

        if not self._config.expand_texts:
            return
        expand_script = """
        (texts) => {
            const elements = Array.from(document.querySelectorAll('button, [role="button"], a'));
            for (const element of elements) {
                const label = (element.innerText || element.getAttribute('aria-label') || '').toLowerCase();
                for (const text of texts) {
                    if (label.includes(text.toLowerCase())) {
                        element.click();
                    }
                }
            }
        }
        """
        await page.evaluate(expand_script, list(self._config.expand_texts))

    def _read_without_render(self, path: Path) -> RenderedPage:
        html = path.read_text(encoding="utf-8", errors="ignore")
        return RenderedPage(source_path=path, final_html=html, final_url=path.as_uri())


async def render_paths(paths: Iterable[Path], config: RenderConfig) -> list[RenderedPage]:
    """複数パスをまとめてレンダリングするためのヘルパー。"""

    renderer = PageRenderer(config)
    return await renderer.render_many(paths)
