from fastapi import APIRouter, WebSocket, WebSocketDisconnect # ✅ ĐÚNG

from app.services.virtual_try_on.vto_ws_manager import vto_ws_manager
router = APIRouter()

@router.websocket("/ws/vto/{request_id}")
async def websocket_vto_endpoint(websocket: WebSocket, request_id: str):
    await vto_ws_manager.connect(websocket, request_id)
    try:
        # Vòng lặp giữ kết nối sống (Keep-alive)
        while True:
            # Lắng nghe nếu FE có gửi gì lên (ví dụ ping/pong)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        vto_ws_manager.disconnect(request_id)