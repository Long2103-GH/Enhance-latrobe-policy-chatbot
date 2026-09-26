"""
La Trobe University Policy Crawler (RAG Pipeline Ingestion Engine)

This module discovers, extracts, and structures policy documents from the La Trobe
University Policy Library. It utilizes an async headless browser crawler (Crawl4AI)
and parses the resulting semantic Markdown into structured section schema compatible
with downstream RAG vector embedding pipelines.

Output Artifacts:
    - Root JSONL File: policies.jsonl (Full document records and section structures)
    - Root CSV File:   policies_summary.csv (Ingestion metadata and character metrics)
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from crawl4ai import AsyncWebCrawler, CacheMode, CrawlerRunConfig

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================

# Dynamic path resolution targeting project root (raw/get_raw_policies/ -> raw/ -> )
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

JSONL_FILE: Path = PROJECT_ROOT / 'policies.jsonl'
CSV_FILE: Path = PROJECT_ROOT / 'policies_summary.csv'

BASE_URL: str = 'https://policies.latrobe.edu.au'
BROWSE_URL: str = 'https://policies.latrobe.edu.au/browse'

PAGE_TIMEOUT_MS: int = 15000  # 15 second network timeout per document
INTER_REQUEST_DELAY: float = 1.0  # Polite crawl delay between pages

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ==============================================================================
# PARSING & HELPER FUNCTIONS
# ==============================================================================

def clean_text(text: str) -> str:
    """Sanitizes raw text string by removing non-breaking spaces and whitespace noise.
    
    Args:
        text: Raw text string.
        
    Returns:
        Cleaned, normalized string.
    """
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_markdown_to_sections(markdown_text: str) -> list[dict[str, str]]:
    """Transforms raw Markdown content into structured heading-text section dicts.
    
    This maintains exact schema compatibility with downstream chunking modules
    expecting the legacy section list structure.

    Args:
        markdown_text: Unstructured Markdown string.

    Returns:
        List of dictionaries containing 'heading' and 'text' keys.
    """
    sections: list[dict[str, str]] = []
    
    # Split content along Markdown header markers (#, ##, ###, ####)
    raw_blocks: list[str] = re.split(r'\n(?=#{1,4}\s)', markdown_text)
    
    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue
            
        lines: list[str] = block.split('\n', 1)
        
        # Extract heading title and clean header tokens
        raw_heading: str = lines[0]
        heading: str = re.sub(r'^#{1,4}\s*', '', raw_heading).strip()
        heading = clean_text(heading)
        
        # Extract body text associated with this heading
        body_text: str = lines[1].strip() if len(lines) > 1 else ''
        
        # Omit navigational UI noise
        if heading.lower() == 'top of page' or not heading:
            continue
            
        if body_text:
            sections.append({
                'heading': heading,
                'text': body_text
            })
            
    return sections


def load_scraped_urls(file_path: Path) -> set[str]:
    """Reads existing JSONL file to retrieve set of already-processed policy URLs.
    
    Args:
        file_path: Path to local policies.jsonl file.
        
    Returns:
        Set of unique URL strings already persisted to disk.
    """
    scraped_urls: set[str] = set()
    if not file_path.exists():
        return scraped_urls

    with open(file_path, encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if 'url' in data:
                    scraped_urls.add(data['url'])
            except json.JSONDecodeError as err:
                logger.warning(f"Malformed JSON on line {line_num} in {file_path}: {err}")

    return scraped_urls


# ==============================================================================
# CRAWLER ENGINE CORE
# ==============================================================================

async def discover_policy_links(
    crawler: AsyncWebCrawler, config: CrawlerRunConfig
    ) -> dict[str, str]:
    """Scrapes the master browse directory to identify all policy document targets.
    
    Args:
        crawler: Initialized AsyncWebCrawler instance.
        config: Crawler settings.
        
    Returns:
        Dict mapping full target URLs to their link display titles.
    """
    logger.info(f"Fetching master policy directory: {BROWSE_URL}")
    result = await crawler.arun(url=BROWSE_URL, config=config)
    
    if not result.success:
        raise RuntimeError(f"Failed to fetch browse directory page: {result.error_message}")

    policy_links: dict[str, str] = {}
    internal_links: list[dict[str, Any]] = result.links.get("internal", [])

    for link_info in internal_links:
        href: str = link_info.get("href", "")
        title: str = clean_text(link_info.get("text", ""))

        # Filter strictly for valid policy document view links
        if "document/view.php?id=" in href:
            full_url: str = href if href.startswith("http") else f"{BASE_URL}{href}"
            
            # Normalize URL to base document ID parameter
            if "&" in full_url:
                full_url = full_url.split("&")[0]

            if full_url not in policy_links:
                policy_links[full_url] = title if title else "Policy Document"

    logger.info(f"Discovered {len(policy_links)} unique policy target links.")
    return policy_links


async def process_crawling_pipeline() -> None:
    """Executes end-to-end resilient crawling, parsing, and streaming persistence."""
    
    # Configure production crawler parameters
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        word_count_threshold=10,
        page_timeout=PAGE_TIMEOUT_MS
    )

    async with AsyncWebCrawler(verbose=False) as crawler:
        # Step 1: Discover links
        try:
            links_map: dict[str, str] = await discover_policy_links(crawler, crawler_config)
        except Exception as err:
            logger.error(f"Critical error during link discovery phase: {err}")
            return

        # Step 2: Check existing progress for crash resumption
        scraped_urls: set[str] = load_scraped_urls(JSONL_FILE)
        pending_items: list[tuple[str, str]] = [
            (url, title) for url, title in links_map.items() if url not in scraped_urls
        ]

        logger.info(f"Already processed: {len(scraped_urls)} | Remaining to scrape: {len(pending_items)}")

        if not pending_items:
            logger.info("Pipeline sync complete. No new policy documents to extract.")
            return

        summary_records: list[dict[str, Any]] = []

        # Step 3: Sequential extraction loop with real-time disk streaming
        with open(JSONL_FILE, "a", encoding="utf-8") as jsonl_out:
            for idx, (url, fallback_title) in enumerate(pending_items, start=1):
                logger.info(f"[{idx}/{len(pending_items)}] Extracting: {url}")
                
                try:
                    result = await crawler.arun(url=url, config=crawler_config)

                    if not result.success or not result.markdown:
                        logger.error(f"Failed extraction for URL {url}: {result.error_message}")
                        continue

                    # Extract page title
                    extracted_title: str = clean_text(result.metadata.get("title", ""))
                    doc_title: str = extracted_title if extracted_title else fallback_title

                    # Build backward-compatible sections schema
                    sections_data: list[dict[str, str]] = parse_markdown_to_sections(
                        result.markdown
                        )

                    # Build exact schema record required by downstream RAG modules
                    record: dict[str, Any] = {
                        'url': result.url,
                        'title': doc_title,
                        'crawled_at': datetime.now(UTC).isoformat(),
                        'section_count': len(sections_data),
                        'sections': sections_data,
                        'full_text': result.markdown
                    }

                    # Stream JSON record directly to disk
                    jsonl_out.write(json.dumps(record, ensure_ascii=False) + '\n')
                    jsonl_out.flush()

                    # Aggregate summary metrics for CSV metadata tracking
                    summary_records.append({
                        'title': record['title'],
                        'url': record['url'],
                        'section_count': record['section_count'],
                        'text_length': len(record['full_text'])
                    })

                except Exception as err:
                    logger.error(f"Unexpected error processing {url}: {err}")

                # Rate-limiting delay to remain server polite
                await asyncio.sleep(INTER_REQUEST_DELAY)

        # Step 4: Write CSV summary analytics file
        if summary_records:
            df = pd.DataFrame(summary_records)
            write_header: bool = not CSV_FILE.exists()
            df.to_csv(CSV_FILE, mode='a', index=False, header=write_header)
            logger.info(f"Summary metrics updated: {CSV_FILE}")

    logger.info("==========================================")
    logger.info("Pipeline execution completed successfully.")
    logger.info("==========================================")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    asyncio.run(process_crawling_pipeline())