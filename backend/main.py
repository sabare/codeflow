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
def analyze(
    path: str,
    function: str | None = None,
    max_depth: int | None = None,
    include_stdlib: bool = True,
    include_external: bool = True,
    include_builtin: bool = True,
) -> dict:
    folder = Path(path).expanduser().resolve()
    logger.info(
        "/analyze requested path=%s function=%s max_depth=%s stdlib=%s external=%s builtin=%s",
        folder,
        function or "<none>",
        max_depth if max_depth is not None else "<none>",
        include_stdlib,
        include_external,
        include_builtin,
    )

    if not folder.exists() or not folder.is_dir():
        logger.warning("/analyze rejected invalid folder=%s", folder)
        raise HTTPException(status_code=400, detail="Path must point to an existing folder.")
    if max_depth is not None and max_depth < 0:
        raise HTTPException(status_code=400, detail="max_depth must be a non-negative integer.")

    try:
        analysis = build_analysis(folder)
        if function:
            from flow import build_flow_tree

            logger.info("Building function flow tree for %s", function)
            return build_flow_tree(
                analysis,
                function,
                max_depth=max_depth,
                include_stdlib=include_stdlib,
                include_external=include_external,
                include_builtin=include_builtin,
                async_enrichment=True,
            )
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


@app.get("/flow-explanation")
def flow_explanation(flow_fingerprint: str) -> dict:
    logger.info("/flow-explanation requested fingerprint=%s", flow_fingerprint)
    try:
        from flow import get_flow_explanation_status

        return get_flow_explanation_status(flow_fingerprint)
    except Exception as exc:  # pragma: no cover - defensive API guard
        logger.exception("Flow explanation lookup failed for fingerprint=%s", flow_fingerprint)
        raise HTTPException(status_code=500, detail=f"Flow explanation lookup failed: {exc}") from exc
