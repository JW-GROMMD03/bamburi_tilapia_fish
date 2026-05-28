import json
from channels.generic.websocket import AsyncWebsocketConsumer

class MenuUpdateConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_group_name = 'menu_updates'
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        pass

    async def menu_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'menu_updated',
            'message': event['message']
        }))