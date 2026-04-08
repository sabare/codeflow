from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

try:
    from analyzer import browse_directory, build_analysis, list_functions_in_file
except ImportError:  # pragma: no cover - lets the app work as a package too
    from .analyzer import browse_directory, build_analysis, list_functions_in_file


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("code-analysis-visualizer")

app = FastAPI(title="Code Analysis Visualizer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Backend starting from cwd=%s, file=%s", os.getcwd(), __file__)


@app.get("/analyze")
def analyze(path: str, function: str | None = None) -> dict:
    folder = Path(path).expanduser().resolve()
    logger.info("/analyze requested path=%s function=%s", folder, function or "<none>")

    if not folder.exists() or not folder.is_dir():
        logger.warning("/analyze rejected invalid folder=%s", folder)
        raise HTTPException(status_code=400, detail="Path must point to an existing folder.")
    logger.info(function)
    try:
        analysis = build_analysis(folder)
        if function:
            from flow import build_flow_tree

            logger.info("Building function flow tree for %s", function)
            return build_flow_tree(analysis, function)
        logger.info("Returning project analysis for folder=%s", folder)
        return analysis
    except Exception as exc: #defensive API guard
        logger.exception("Analysis failed for folder=%s function=%s", folder, function or "<none>")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc


@app.get("/browse")
def browse(path: str) -> dict:
    logger.info("/browse requested path=%s", path)
    try:
        result = browse_directory(Path(path))
        logger.info(
            "/browse resolved path=%s directories=%d files=%d",
            result.get("path"),
            len(result.get("directories", [])),
            len(result.get("files", [])),
        )
        return result
    except FileNotFoundError as exc:
        logger.warning("/browse rejected path=%s", path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/functions")
def functions(path: str) -> dict:
    logger.info("/functions requested path=%s", path)
    try:
        result = list_functions_in_file(Path(path))
        logger.info("/functions found %d functions in %s", len(result.get("functions", [])), result.get("path"))
        return result
    except FileNotFoundError as exc:
        logger.warning("/functions rejected path=%s", path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
