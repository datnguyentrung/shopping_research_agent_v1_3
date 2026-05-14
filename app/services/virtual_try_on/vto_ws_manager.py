from fastapi import WebSocket, WebSocketDisconnect

# Tương đương với ClassSessionWebSocketHandler
class VTOConnectionManager:
    def __init__(self):
        # Lưu trữ các kết nối đang active theo request_id
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, request_id: str):
        # Chấp nhận kết nối từ Frontend
        await websocket.accept()
        self.active_connections[request_id] = websocket
        print(f"🔌 Frontend đã kết nối lắng nghe request: {request_id}")

    def disconnect(self, request_id: str):
        # Xóa kết nối khi Frontend đóng hoặc mất mạng
        if request_id in self.active_connections:
            del self.active_connections[request_id]
            print(f"❌ Đã ngắt kết nối request: {request_id}")

    async def send_vto_result(self, request_id: str, data: dict):
        # Bắn dữ liệu thẳng về Frontend nếu họ đang online
        if request_id in self.active_connections:
            websocket = self.active_connections[request_id]
            await websocket.send_json(data)

# Khởi tạo một instance dùng chung (Singleton)
vto_ws_manager = VTOConnectionManager()