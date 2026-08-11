"""PDF import API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from ..pdf_import import PDFImportError, import_pdf_document
from ..schemas import PDFImportResult


router = APIRouter(prefix="/pdf", tags=["pdf"])


@router.post("/import", response_model=PDFImportResult, status_code=status.HTTP_200_OK)
async def import_pdf(file: UploadFile = File(...)) -> PDFImportResult:
    data = await file.read()
    await file.close()
    try:
        return PDFImportResult.model_validate(import_pdf_document(data))
    except PDFImportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
