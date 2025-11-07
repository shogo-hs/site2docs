"""Playwright を活用して HTML をレンダリングするユーティリティ。"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
import os

from .config import RenderConfig

try:  # pragma: no cover - optional dependency
    from playwright.async_api import async_playwright, BrowserContext, Page
except Exception:  # pragma: no cover - executed when dependency missing
    async_playwright = None  # type: ignore[assignment]
    BrowserContext = object  # type: ignore[misc,assignment]
    Page = object  # type: ignore[misc,assignment]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RenderedPage:
    """HTML ページをレンダリングした結果。"""

    source_path: Path
    final_html: str
    final_url: str


ProgressCallback = Callable[[int, int, Path], None]


_AUTO_EXPAND_HEURISTICS = """
() => {
    const clicked = new Set();
    const tryClick = (el) => {
        if (!el || clicked.has(el)) {
            return;
        }
        const style = window.getComputedStyle(el);
        if (style && style.visibility === 'hidden' || style.display === 'none') {
            return;
        }
        if (typeof el.click === 'function') {
            el.click();
            clicked.add(el);
        }
    };

    const selectors = [
        '[aria-expanded="false"]',
        '[data-expand]',
        '[data-toggle]',
        '[data-accordion]',
        '[data-collapsible]',
        '.accordion',
        '.accordion-item',
        '.accordion-button',
        '.collapse',
        '.expand',
        '.expander',
        '.faq-item',
        '.read-more',
        '.show-more',
    ];

    selectors.forEach((selector) => {
        document.querySelectorAll(selector).forEach((el) => {
            const button = el.matches('button, [role="button"], a') ? el : el.querySelector('button, [role="button"], a');
            if (button) {
                tryClick(button);
            }
        });
    });

    document.querySelectorAll('[aria-controls]').forEach((el) => tryClick(el));

    document.querySelectorAll('details:not([open])').forEach((detail) => {
        detail.setAttribute('open', '');
    });

    return clicked.size;
}
"""


_AUTO_EXPAND_BY_TEXT = """
(texts) => {
    const lowered = (texts || []).map((text) => text.toLowerCase());
    if (!lowered.length) {
        return 0;
    }
    let count = 0;
    const elements = Array.from(document.querySelectorAll('button, [role="button"], a'));
    for (const element of elements) {
        const label = (element.innerText || element.getAttribute('aria-label') || '').toLowerCase();
        if (!label) {
            continue;
        }
        if (lowered.some((text) => label.includes(text))) {
            element.click();
            count += 1;
        }
    }
    return count;
}
"""


class PageRenderer:
    """Playwright を用いて HTML ページをレンダリングし、利用不可の場合はフォールバックします。"""

    def __init__(self, config: RenderConfig) -> None:
        self._config = config

    async def render_many(self, paths: Iterable[Path], progress: ProgressCallback | None = None) -> list[RenderedPage]:
        """ローカル HTML ファイルを順番にレンダリングします。"""

        path_list = list(paths)
        if not path_list:
            return []

        pages: list[RenderedPage] = []
        if async_playwright is None:
            total = len(path_list)
            for index, path in enumerate(path_list, start=1):
                pages.append(self._read_without_render(path))
                if progress is not None:
                    progress(index, total, path)
                else:
                    logger.info("Playwright を利用せずに読み込みました (%d/%d): %s", index, total, path.name)
            return pages

        async with async_playwright() as playwright:  # type: ignore[misc]
            browser = await playwright.chromium.launch()
            total = len(path_list)
            results: list[RenderedPage | None] = [None] * total
            worker_count = self._determine_worker_count(total)
            contexts: list[BrowserContext] = [await browser.new_context() for _ in range(worker_count)]
            context_pool: asyncio.Queue[BrowserContext] = asyncio.Queue()
            for context in contexts:
                context_pool.put_nowait(context)
            progress_lock = asyncio.Lock()
            completed = 0

            async def notify_progress(path: Path) -> None:
                nonlocal completed
                async with progress_lock:
                    completed += 1
                    current = completed
                if progress is not None:
                    progress(current, total, path)
                else:
                    logger.info("レンダリング中 (%d/%d): %s", current, total, path.name)

            async def process(index: int, path: Path) -> None:
                context = await context_pool.get()
                try:
                    rendered = await self._render_single(context, path)
                finally:
                    context_pool.put_nowait(context)
                results[index] = rendered
                await notify_progress(path)

            try:
                await asyncio.gather(*(process(index, path) for index, path in enumerate(path_list)))
            finally:
                for context in contexts:
                    try:
                        await context.close()
                    except Exception:
                        logger.debug("コンテキストクローズ中に例外が発生しました。", exc_info=True)
                await browser.close()

        return [page for page in results if page is not None]

    def _determine_worker_count(self, total: int) -> int:
        requested = self._config.max_concurrency
        if requested is not None and requested > 0:
            return max(1, min(total, requested))
        cpu_total = os.cpu_count() or 2
        if cpu_total <= 1:
            baseline = 1
        elif cpu_total <= 4:
            baseline = cpu_total - 1
        else:
            baseline = min(8, cpu_total // 2 + 2)
        return max(1, min(total, baseline))

    async def _render_single(self, context: BrowserContext, path: Path) -> RenderedPage:
        page = await context.new_page()
        try:
            await page.goto(path.as_uri(), wait_until=self._config.wait_until, timeout=self._config.render_timeout * 1000)
            await self._auto_expand(page)
            html = await page.content()
            return RenderedPage(source_path=path, final_html=html, final_url=page.url)
        finally:
            await page.close()

    async def _auto_expand(self, page: Page) -> None:
        """スクロールやボタン操作で動的コンテンツを展開します。"""

        # Scroll behaviour
        for _ in range(self._config.max_scroll_iterations):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            await asyncio.sleep(self._config.scroll_pause)

        if self._config.auto_expand_candidates:
            await page.evaluate(_AUTO_EXPAND_HEURISTICS)

        if self._config.expand_texts:
            await page.evaluate(_AUTO_EXPAND_BY_TEXT, list(self._config.expand_texts))

    def _read_without_render(self, path: Path) -> RenderedPage:
        html = path.read_text(encoding="utf-8", errors="ignore")
        return RenderedPage(source_path=path, final_html=html, final_url=path.as_uri())


async def render_paths(paths: Iterable[Path], config: RenderConfig, progress: ProgressCallback | None = None) -> list[RenderedPage]:
    """複数パスをまとめてレンダリングするためのヘルパー。"""

    renderer = PageRenderer(config)
    return await renderer.render_many(paths, progress=progress)
