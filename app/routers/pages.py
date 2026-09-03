from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

DIST_DIR = Path(__file__).resolve().parents[2] / "dist"
INDEX_FILE = DIST_DIR / "index.html"
PAGE_PATHS = ("/", "/saju", "/tarot", "/face", "/mypage")


def _index_response() -> FileResponse:
    if not INDEX_FILE.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend build is missing. Run `npm run build` in luck-was.",
        )
    return FileResponse(INDEX_FILE)


for page_path in PAGE_PATHS:
    router.add_api_route(page_path, _index_response, methods=["GET"])
