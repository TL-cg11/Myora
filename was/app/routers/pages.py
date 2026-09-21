from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)

DIST_DIR = Path(__file__).resolve().parents[2] / "dist"
INDEX_FILE = DIST_DIR / "index.html"
FAVICON_FILE = DIST_DIR / "favicon.svg"
PAGE_PATHS = (
    "/", "/saju", "/tarot", "/face", "/mypage", "/dashboard", "/login", "/signup",
)


def _index_response() -> FileResponse:
    if not INDEX_FILE.is_file():
        raise HTTPException(
            status_code=503,
            detail="Frontend build is missing. Run `npm run build` in luck-was.",
        )
    return FileResponse(INDEX_FILE)


def _favicon_response() -> FileResponse:
    if not FAVICON_FILE.is_file():
        raise HTTPException(status_code=404, detail="Favicon is missing.")
    return FileResponse(FAVICON_FILE, media_type="image/svg+xml")


router.add_api_route("/favicon.svg", _favicon_response, methods=["GET"])


for page_path in PAGE_PATHS:
    router.add_api_route(page_path, _index_response, methods=["GET"])
