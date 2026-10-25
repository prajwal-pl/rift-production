from typing import Protocol


class StorageProvider(Protocol):
    async def upload_file(
        self,
        path: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str: ...

    async def get_file(self, path: str) -> bytes: ...

    def get_public_url(self, path: str) -> str: ...
