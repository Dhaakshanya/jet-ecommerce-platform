import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        self.user = self.scope['user']

        # Reject anonymous users
        if not self.user.is_authenticated:
            await self.close()
            return

        # Verify the user has access to this room
        has_access = await self.user_has_access()
        if not has_access:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data.get('message', '').strip()
        if not message:
            return

        # Save message to DB
        msg = await self.save_message(message)

        # Broadcast to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': self.user.username,
                'sender_id': self.user.id,
                'timestamp': msg['timestamp'],
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'message': event['message'],
            'sender': event['sender'],
            'sender_id': event['sender_id'],
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def user_has_access(self):
        from .models import ChatRoom
        try:
            room = ChatRoom.objects.select_related('product__producer').get(id=self.room_id)
        except ChatRoom.DoesNotExist:
            return False
        return self.user == room.buyer or self.user == room.product.producer

    @database_sync_to_async
    def save_message(self, message):
        from .models import ChatRoom, ChatMessage
        room = ChatRoom.objects.get(id=self.room_id)
        msg = ChatMessage.objects.create(room=room, sender=self.user, text=message)
        return {'timestamp': msg.timestamp.strftime('%I:%M %p')}