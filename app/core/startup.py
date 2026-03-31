"""
Startup Warm-Up Routines for GeoVision Lab

This module pre-loads heavy models at application startup to avoid
blocking the first user request with model downloads and initialization.

Usage:
    from app.core.startup import warm_up_models

    await warm_up_models()  # Call on application startup
"""

import asyncio
import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Global state to track warm-up status
# Each model entry:
#   "status": "pending" | "loading" | "ready" | "error"
#   "label":  human-readable name for the UI
_warmup_status: Dict[str, Any] = {
    "started": False,
    "completed": False,
    "in_progress": False,
    "models": {
        "ner": {"status": "pending", "label": "NER (bert-base-NER)"},
        "embeddings": {"status": "pending", "label": "Embeddings (all-MiniLM-L6-v2)"},
        "llm": {"status": "pending", "label": "LLM (initializing…)"},
        "reranker": {"status": "pending", "label": "Re-ranker (BGE)"},
    },
}


def _set_model_status(name: str, status: str, label: str | None = None) -> None:
    """Update per-model status in the warmup state dict."""
    _warmup_status["models"][name]["status"] = status
    if label is not None:
        _warmup_status["models"][name]["label"] = label


def get_warmup_status() -> Dict[str, Any]:
    """Get current model warm-up status (safe copy for API responses)."""
    models = _warmup_status["models"]
    all_ready = all(v["status"] == "ready" for v in models.values())
    any_error = any(v["status"] == "error" for v in models.values())

    return {
        "started": _warmup_status["started"],
        "completed": _warmup_status["completed"],
        "in_progress": _warmup_status["in_progress"],
        # Legacy bool results for backward compat
        "results": {k: (v["status"] == "ready") for k, v in models.items()},
        # Rich per-model info for new UI
        "models": {k: dict(v) for k, v in models.items()},
        "ready": all_ready and _warmup_status["completed"],
        "any_error": any_error,
    }


# ---------------------------------------------------------------------------
# Individual warm-up functions
# ---------------------------------------------------------------------------


async def warm_up_ner_pipeline() -> bool:
    """Pre-load the NER (Named Entity Recognition) pipeline."""
    _set_model_status("ner", "loading")
    try:
        logger.info("[STARTUP] Loading NER model (dslim/bert-base-NER)…")
        start_time = time.time()

        # Import is blocking — run in executor to keep event loop free
        loop = asyncio.get_event_loop()
        from app.core.di_nlp import get_ner_pipeline

        ner_pipeline = await loop.run_in_executor(None, get_ner_pipeline)

        # Quick functional test
        await loop.run_in_executor(None, ner_pipeline, "Paris is in France")

        elapsed = time.time() - start_time
        logger.info(f"[STARTUP] ✅ NER pipeline ready in {elapsed:.1f}s")
        _set_model_status("ner", "ready", "NER (bert-base-NER)")
        return True

    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to load NER pipeline: {e}")
        _set_model_status("ner", "error")
        return False


async def warm_up_embeddings() -> bool:
    """Pre-load the embedding model."""
    _set_model_status("embeddings", "loading")
    try:
        logger.info("[STARTUP] Loading embedding model…")
        start_time = time.time()

        loop = asyncio.get_event_loop()
        from app.core.di_nlp import get_embeddings

        embeddings = await loop.run_in_executor(None, get_embeddings)
        await loop.run_in_executor(None, embeddings.embed_query, "test embedding")

        elapsed = time.time() - start_time
        logger.info(f"[STARTUP] ✅ Embedding model ready in {elapsed:.1f}s")
        _set_model_status("embeddings", "ready", "Embeddings (all-MiniLM-L6-v2)")
        return True

    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to load embeddings: {e}")
        _set_model_status("embeddings", "error")
        return False


async def warm_up_llm() -> bool:
    """
    Wait for Ollama to become reachable, then verify the LLM connection.

    Retries with exponential back-off so the app boots even before Ollama
    has finished pulling models (which can take many minutes on first run).
    """
    from app.core.config import settings

    model_name = settings.REASONING_LLM_MODEL_NAME
    _set_model_status("llm", "loading", f"LLM ({model_name}) — waiting for Ollama…")
    logger.info(f"[STARTUP] Waiting for Ollama + LLM ({model_name})…")

    max_attempts = 60  # up to ~10 minutes
    base_sleep = 10  # seconds between retries

    for attempt in range(1, max_attempts + 1):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Check if Ollama is up
                r = await client.get(f"{settings.OLLAMA_URL}/api/tags")
                r.raise_for_status()
                tags_data = r.json()

            # Check whether our model is already pulled
            pulled_names = [m.get("name", "") for m in tags_data.get("models", [])]
            is_pulled = any(model_name in n for n in pulled_names)

            if not is_pulled:
                logger.info(
                    f"[STARTUP] Ollama reachable but {model_name} not yet pulled "
                    f"(attempt {attempt}/{max_attempts}). "
                    f"Available: {pulled_names[:5] or 'none'}"
                )
                _set_model_status(
                    "llm",
                    "loading",
                    f"LLM ({model_name}) — downloading… (attempt {attempt})",
                )
                await asyncio.sleep(base_sleep)
                continue

            # Model is present → initialise the LangChain wrapper
            loop = asyncio.get_event_loop()
            from app.core.di_llm import get_llm

            await loop.run_in_executor(None, get_llm)

            logger.info(f"[STARTUP] ✅ LLM ({model_name}) ready")
            _set_model_status("llm", "ready", f"LLM ({model_name})")
            return True

        except Exception as e:
            logger.warning(
                f"[STARTUP] Ollama not reachable (attempt {attempt}/{max_attempts}): {e}"
            )
            _set_model_status(
                "llm",
                "loading",
                f"LLM ({model_name}) — connecting… (attempt {attempt})",
            )
            await asyncio.sleep(base_sleep)

    logger.error(f"[STARTUP] ❌ Gave up waiting for LLM after {max_attempts} attempts")
    _set_model_status("llm", "error")
    return False


async def warm_up_reranker() -> bool:
    """
    Pre-load the BGE re-ranker model.

    The re-ranker is a cross-encoder model that improves retrieval precision.
    Loading it at startup avoids the ~2-5 second delay on first query.
    """
    from app.core.config import settings

    if not settings.RAG_RERANKER_ENABLED:
        logger.info("[STARTUP] Re-ranker disabled, skipping warm-up")
        _set_model_status("reranker", "pending", "Re-ranker (disabled)")
        return True  # Not an error, just disabled

    _set_model_status(
        "reranker", "loading", f"Re-ranker ({settings.RAG_RERANKER_MODEL})"
    )
    try:
        logger.info(
            f"[STARTUP] Loading BGE re-ranker model: {settings.RAG_RERANKER_MODEL}…"
        )
        start_time = time.time()

        loop = asyncio.get_event_loop()
        from app.services.reranker import get_reranker_service

        # Load the model (this triggers the download if not cached)
        reranker = await loop.run_in_executor(None, get_reranker_service)

        # Verify model is loaded
        is_available = await loop.run_in_executor(None, reranker.is_available)

        if not is_available:
            logger.warning("[STARTUP] Re-ranker model failed to load")
            _set_model_status("reranker", "error")
            return False

        elapsed = time.time() - start_time
        logger.info(f"[STARTUP] ✅ Re-ranker ready in {elapsed:.1f}s")
        _set_model_status(
            "reranker", "ready", f"Re-ranker ({settings.RAG_RERANKER_MODEL})"
        )
        return True

    except Exception as e:
        logger.error(f"[STARTUP] ❌ Failed to load re-ranker: {e}")
        _set_model_status("reranker", "error")
        return False


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def warm_up_models() -> Dict[str, bool]:
    """
    Warm up all models at application startup.

    Runs NER, embeddings, and reranker in parallel, then waits for the LLM.
    Updates _warmup_status in real-time so the UI can poll progress.
    """
    global _warmup_status

    _warmup_status["started"] = True
    _warmup_status["in_progress"] = True

    logger.info("=" * 60)
    logger.info("[STARTUP] Beginning model warm-up (async)…")
    logger.info("[STARTUP] UI is available immediately while models load.")
    logger.info("=" * 60)

    # NER, embeddings, and reranker can be loaded in parallel
    ner_result, embedding_result, reranker_result = await asyncio.gather(
        warm_up_ner_pipeline(),
        warm_up_embeddings(),
        warm_up_reranker(),
    )

    # LLM depends on Ollama — start after HF models to avoid racing logs
    llm_result = await warm_up_llm()

    results = {
        "ner": ner_result,
        "embeddings": embedding_result,
        "llm": llm_result,
        "reranker": reranker_result,
    }

    _warmup_status["completed"] = True
    _warmup_status["in_progress"] = False

    # Summary
    logger.info("=" * 60)
    successful = sum(1 for v in results.values() if v)
    total = len(results)
    if successful == total:
        logger.info(f"[STARTUP] ✅ All {total} models ready!")
    else:
        logger.warning(
            f"[STARTUP] ⚠️  {total - successful}/{total} models failed to load"
        )
    logger.info("=" * 60)

    return results
