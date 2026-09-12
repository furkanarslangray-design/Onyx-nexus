#!/usr/bin/env python3
"""MCP server for GitHub integration.

Provides tools for repository operations, issue tracking, and code search.
"""

import os
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

import requests
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent


@dataclass
class GitHubConfig:
    token: str
    base_url: str = "https://api.github.com"


class GitHubClient:
    """GitHub API client with rate limit handling."""

    def __init__(self, config: GitHubConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {config.token}",
            "Accept": "application/vnd.github.v3+json"
        })

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Request with rate limit retry."""
        url = f"{self.config.base_url}{endpoint}"

        for attempt in range(3):
            response = self.session.request(method, url, **kwargs)

            if response.status_code == 403 and "rate limit" in response.text.lower():
                # Exponential backoff
                import time
                time.sleep(2 ** attempt)
                continue

            response.raise_for_status()
            return response.json()

        raise RuntimeError("GitHub API rate limit exceeded")

    def get_repo(self, owner: str, repo: str) -> Dict:
        return self._request("GET", f"/repos/{owner}/{repo}")

    def create_issue(self, owner: str, repo: str, title: str, body: str) -> Dict:
        return self._request("POST", f"/repos/{owner}/{repo}/issues", json={
            "title": title,
            "body": body
        })

    def search_code(self, query: str) -> List[Dict]:
        result = self._request("GET", "/search/code", params={"q": query})
        return result.get("items", [])

    def create_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main"
    ) -> Dict:
        import base64
        content_b64 = base64.b64encode(content.encode()).decode()

        return self._request("PUT", f"/repos/{owner}/{repo}/contents/{path}", json={
            "message": message,
            "content": content_b64,
            "branch": branch
        })


# MCP Server setup
app = Server("github-mcp")


@app.list_tools()
async def list_tools() -> List[Tool]:
    return [
        Tool(
            name="get_repo",
            description="Get repository information",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"}
                },
                "required": ["owner", "repo"]
            }
        ),
        Tool(
            name="create_issue",
            description="Create a GitHub issue",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["owner", "repo", "title"]
            }
        ),
        Tool(
            name="search_code",
            description="Search code across GitHub",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    config = GitHubConfig(token=os.getenv("GITHUB_TOKEN"))
    client = GitHubClient(config)

    if name == "get_repo":
        result = client.get_repo(arguments["owner"], arguments["repo"])
    elif name == "create_issue":
        result = client.create_issue(
            arguments["owner"],
            arguments["repo"],
            arguments["title"],
            arguments.get("body", "")
        )
    elif name == "search_code":
        result = client.search_code(arguments["query"])
    else:
        raise ValueError(f"Unknown tool: {name}")

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
