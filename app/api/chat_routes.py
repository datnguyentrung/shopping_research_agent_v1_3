import json
import time
from datetime import datetime
from typing import Any
from fastapi import APIRouter
from sse_starlette import EventSourceResponse

# Chỉ import Orchestrator mới, tạm biệt file Native cũ!
from app.agents.adk_orchestrator import run_shopping_orchestrator
from app.models.ui_chunks import ChatRequest, ErrorChunk, DoneChunk
from app.utils.trace_log import is_trace_stream_enabled

router = APIRouter()


def _trace_log(trace_id: str, stage: str, **details: Any) -> None:
    if not is_trace_stream_enabled():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[chat/stream][{timestamp}][{trace_id}][{stage}]")
    if details:
        print(json.dumps(details, ensure_ascii=False, indent=2, default=str))


def _short_text(value: Any, max_len: int = 240) -> str:
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def _extract_product_preview(chunk_payload: dict[str, Any]) -> dict[str, Any] | None:
    if chunk_payload.get("type") != "a2ui":
        return None
    a2ui_payload = chunk_payload.get("a2ui") or {}
    if a2ui_payload.get("type") != "a2ui_interactive_product":
        return None
    product = (a2ui_payload.get("data") or {}).get("product") or {}
    return {
        "productId": product.get("productId") or product.get("product_id"),
        "name": product.get("name"),
        "priceCurrent": product.get("priceCurrent") or product.get("price_current"),
        "ratingStar": product.get("ratingStar") or product.get("rating_star"),
        "productUrl": product.get("productUrl") or product.get("product_url"),
    }


@router.post("/chat")
async def stream_chat(payload: ChatRequest) -> EventSourceResponse:
    async def _event_generator():
        trace_id = payload.sessionId or f"anonymous-{id(payload)}"
        start_time = time.perf_counter()
        received_count = 0
        sent_count = 0
        product_count = 0

        _trace_log(
            trace_id, "request_received", messagePreview=_short_text(payload.message),
            messageLength=len(payload.message or ""), hasHiddenEvents=payload.hidden_events is not None,
            hiddenAction=getattr(payload.hidden_events, "action", None),
        )

        try:
            # ---> FIX: Gọi Orchestrator của ADK tại đây <---
            async for chunk in run_shopping_orchestrator(payload):
                received_count += 1

                # Check nếu node trả ra dict cập nhật state thì bỏ qua không stream về FE
                if isinstance(chunk, dict) and "state_update" in chunk:
                    continue

                chunk_type = type(chunk).__name__

                if hasattr(chunk, "model_dump"):
                    chunk_payload = chunk.model_dump(exclude_none=True, by_alias=True)
                    root_type = chunk_payload.get("type")
                    a2ui_type = (chunk_payload.get("a2ui") or {}).get("type")
                    product_preview = _extract_product_preview(chunk_payload)

                    _trace_log(
                        trace_id, "chunk_received", index=received_count, modelType=chunk_type,
                        rootType=root_type, a2uiType=a2ui_type,
                    )

                    if product_preview:
                        product_count += 1
                        _trace_log(trace_id, "product_selected", index=received_count, product=product_preview)

                    event_data = chunk.model_dump_json(exclude_none=True, by_alias=True)
                    sent_count += 1
                    _trace_log(
                        trace_id, "chunk_sent_to_fe", index=received_count, sentCount=sent_count,
                        eventBytes=len(event_data.encode("utf-8")), eventPreview=_short_text(event_data),
                    )
                    yield {"data": event_data}
                    continue

                # Fallback xử lý string thô
                if isinstance(chunk, str):
                    event_data = json.dumps({"type": "message", "content": chunk})
                    yield {"data": event_data}
                    continue

            # Hoàn tất stream
            _trace_log(
                trace_id, "stream_completed", receivedCount=received_count, sentCount=sent_count,
                productCount=product_count, elapsedMs=round((time.perf_counter() - start_time) * 1000, 2),
            )
            done_chunk = DoneChunk().model_dump_json(exclude_none=True, by_alias=True)
            yield {"data": done_chunk}
            yield {"data": "[DONE]"}

        except Exception as exc:
            import traceback
            traceback.print_exc()
            _trace_log(
                trace_id, "stream_failed", errorType=type(exc).__name__, error=str(exc),
                receivedCount=received_count, sentCount=sent_count, productCount=product_count,
                elapsedMs=round((time.perf_counter() - start_time) * 1000, 2),
            )
            yield {"data": ErrorChunk(error=str(exc)).model_dump_json()}
            yield {"data": "[DONE]"}

    return EventSourceResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )