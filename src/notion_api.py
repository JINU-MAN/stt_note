from notion_client import Client


def _extract_title(page: dict) -> str:
    """Extract the plain text title from any Notion page object."""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            if parts:
                return parts[0].get("plain_text", "").strip()
    return "(제목 없음)"


class NotionAPI:
    def __init__(self, token: str):
        self.client = Client(auth=token)

    def test_connection(self):
        """Raise if the token is invalid."""
        self.client.users.me()

    def search_pages(self, query: str = "") -> list[dict]:
        """Return up to 20 pages matching the query, sorted by last-edited."""
        response = self.client.search(
            query=query,
            filter={"property": "object", "value": "page"},
            sort={"direction": "descending", "timestamp": "last_edited_time"},
            page_size=20,
        )
        return [
            {"id": r["id"], "title": _extract_title(r)}
            for r in response.get("results", [])
        ]

    def create_child_page(self, parent_page_id: str, title: str) -> str:
        """Create a child page and return its ID."""
        response = self.client.pages.create(
            parent={"page_id": parent_page_id},
            properties={
                "title": {"title": [{"text": {"content": title}}]}
            },
        )
        return response["id"]

    def append_blocks(self, page_id: str, blocks: list[dict]):
        """Append blocks to a page, sending at most 100 per request."""
        for i in range(0, len(blocks), 100):
            self.client.blocks.children.append(
                block_id=page_id,
                children=blocks[i : i + 100],
            )
