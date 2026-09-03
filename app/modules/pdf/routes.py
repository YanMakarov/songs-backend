"""PDF import API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from .importer import PDFImportError, import_pdf_document
from .schemas import PDFImportResult


router = APIRouter(prefix="/pdf", tags=["pdf"])


@router.post("/import", response_model=PDFImportResult, status_code=status.HTTP_200_OK)
async def import_pdf(file: UploadFile = File(...)) -> PDFImportResult:
    data = await file.read()
    await file.close()
    try:
        # `run_in_threadpool`, not a plain call: pdfminer spends tens of seconds
        # on a large document, and this is the only `async def` in the app — so
        # calling it inline froze the event loop of the single uvicorn process.
        # Every other device's poll then sat in `pending` until the frontend's
        # 20s timeout gave up, which looked like the API failing at random.
        # This does not make the import cheap — pdfminer is pure Python and
        # holds the GIL — but the loop gets scheduled in between, so the rest of
        # the API answers slowly instead of not at all.
        parsed = await run_in_threadpool(import_pdf_document, data)
    except PDFImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PDFImportResult.model_validate(parsed)
