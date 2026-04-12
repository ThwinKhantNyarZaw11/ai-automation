"""
Search the web for original sources and related images.
Uses Serper.dev API for Google search results.
Usage: python -m execution.source_finder --query "..." [--num_results 5]
"""
import argparse
import json
import requests

from execution.config import SERPER_API_KEY, TMP_DIR


def search_sources(query: str, num_results: int = 5) -> dict:
    """
    Search for original sources and related images for a given query.
    Returns dict with 'sources' (web results) and 'images'.
    """
    if not SERPER_API_KEY:
        raise ValueError("SERPER_API_KEY not set in .env")

    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    # Web search for sources
    web_response = requests.post(
        "https://google.serper.dev/search",
        headers=headers,
        json={"q": query, "num": num_results},
    )
    web_response.raise_for_status()
    web_data = web_response.json()

    # Image search
    img_response = requests.post(
        "https://google.serper.dev/images",
        headers=headers,
        json={"q": query, "num": num_results},
    )
    img_response.raise_for_status()
    img_data = img_response.json()

    results = {
        "query": query,
        "sources": [
            {
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
            }
            for r in web_data.get("organic", [])
        ],
        "images": [
            {
                "title": r.get("title", ""),
                "image_url": r.get("imageUrl", ""),
                "link": r.get("link", ""),
            }
            for r in img_data.get("images", [])
        ],
    }

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Search for sources and images")
    parser.add_argument("--query", required=True)
    parser.add_argument("--num_results", type=int, default=5)
    args = parser.parse_args()

    result = search_sources(args.query, args.num_results)
    print(json.dumps(result, indent=2, ensure_ascii=False))
