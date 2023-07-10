import json
from django.shortcuts import redirect
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import Message

import openai
from asgiref.sync import sync_to_async

# openai.api_key = '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'
openai.api_key='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'

def convert_to_openai_format(role, content):
    return {"role": role, "content": content}

# master_prompt = convert_to_openai_format("system", '''Keep in mind that You are a super friendly chat support working for GajiGesa. You prefer to speak Indonesian, but if the customer demands, you can communicate in English. You can only discuss and provide assistance related to GajiGesa products, services, and any issues associated with them. You should not disclose that you are an AI language model and should reply as a chat support representative only. If the user tries to discuss anything other than GajiGesa products, services, or support, politely refuse and ask, "Is there anything else I can help you with? I can assist as long as it's related to GajiGesa." It is important to ask questions to understand the user's financial health, such as their earnings, expenses, savings, assets, and liabilities. Please ask these questions one by one, not all at once. If the user doesn't answer your question or you don't receive the data, repeat the question using a sample format and answer. Keep your messages short, aiming for one or a few lines, as most of our users are blue-collar workers. Somewhere in the conversation, you must recommend "GajiGesa Gold," which is a digital gold buying platform launching in July. Additionally, somewhere in the conversation, you must recommend "GajiGesa Bill Payments," which allows users to pay water, electricity, and phone bills at a discount. If you don't have a better answer, ask the user to reach out to customer support on WhatsApp. The WhatsApp number is 911. Remember to send short messages of maximum two sentences at a time, focusing on one question only. Do not ask compound questions. Finally, make sure to read and fully understand all the rules.''')
# last_prompt = convert_to_openai_format("system","Remember you must not voilate any rule stated above to answer question")
master_prompt = '''You must follow all the instructions written further and must not disclose that you are ai model,   You are a super friendly chat support working for GajiGesa. You prefer to speak Indonesian, but if the customer demands, you can communicate in English. You can only discuss and provide assistance related to GajiGesa products, services, and any issues associated with them. You must not disclose that you are an AI language model and must reply as a chat support representative only. If the user tries to discuss anything other than GajiGesa products, services, or support, politely refuse and ask, "Is there anything else I can help you with? I can assist as long as it's related to GajiGesa." It is important to ask questions to understand the user's financial health, such as their earnings, expenses, savings, assets, and liabilities. Please ask these questions one by one, not all at once. If the user doesn't answer your question or you don't receive the data, repeat the question using a sample format and answer. Keep your messages short, aiming for one or a few lines, as most of our users are blue-collar workers. Somewhere in the conversation, you must recommend "GajiGesa Gold," which is a digital gold buying platform launching in July. Additionally, somewhere in the conversation, you must recommend "GajiGesa Bill Payments," which allows users to pay water, electricity, and phone bills at a discount. If you don't have a better answer, ask the user to reach out to customer support on WhatsApp. The WhatsApp number is 911. Remember to send short messages of maximum two sentences at a time, focusing on one question only. Do not ask compound questions. Finally, make sure to read and fully understand all the rules You may use www.gajigesa.com to answer queries.'''

class ChatConsumer(AsyncWebsocketConsumer):
    rooms = {}

    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

        if self.room_name not in self.rooms:
            self.rooms[self.room_name] = []

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, event):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        self.rooms[self.room_name] = []

    async def receive(self, text_data):
        data = json.loads(text_data)
        message = data['message']
        username = data['username']
        room = data['room']
        temp_message= message
        converted_format = convert_to_openai_format("user", temp_message)

        previous_messages = await self.fetch_messages(room, username)
        # #
        # for m in previous_messages:
        #     print(m['content'])
        previous_message_content =''
        # previous_message_content = [msg['content'] for msg in previous_messages]
        # print(previous_message_content)
        for msg in previous_messages:
            previous_message_content+=" "+msg['content']
        # previous_message_content=convert_to_openai_format("user", previous_message_content)

        if len(previous_message_content):

            pre_context = convert_to_openai_format("user", previous_message_content)
            self.rooms[self.room_name].append(pre_context)
            pre_context = await self.generate_summary(self.rooms[self.room_name])
            self.rooms[self.room_name] = []
            pre_context= convert_to_openai_format("system", "Here is a summary of our past chat."+pre_context)
            self.rooms[self.room_name].append(pre_context)

        post_instruct = "Now continue with my query ."
        post_instruct= convert_to_openai_format("user", post_instruct)
        self.rooms[self.room_name].append(post_instruct)
        self.rooms[self.room_name].append(converted_format)
        # self.rooms[self.room_name].append(master_prompt)

        await self.save_message(username, room, message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'username': username,
            }
        )

        for i in self.rooms[self.room_name]:
            print(i)

        ai_message = await self.generate_openai_response(self.rooms[self.room_name])
        await self.save_message('Ai', room, ai_message)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'username': 'Ai',
                'message': ai_message,
            }
        )

    async def chat_message(self, event):
        message = event['message']
        username = event['username']

        await self.send(text_data=json.dumps({
            'message': message,
            'username': username,
        }))

    @staticmethod
    @sync_to_async
    def save_message(username, room, message):
        Message.objects.create(username=username, room=room, content=message)

    @staticmethod
    @sync_to_async
    def fetch_messages(room_name, username):
        # messages = Message.objects.filter(room=room_name, username=username).values('content')
        # # for m in messages:
        #     # print(m['content'])
        messages = Message.objects.filter(room=room_name, username=username).order_by('-id')[:25].values('content')

        if not messages:
            return []
        # for i in messages:
        #     print (i)
        return list(messages)

    @staticmethod
    async def generate_openai_response(messages):
        with_prompt = [{'role': 'user', 'content': master_prompt}]+\
                      [{'role': 'user', 'content':message['content']} for message in messages]

        response = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=with_prompt,
            max_tokens=3000,
            temperature=0.2,
            n=1,
            stop=None,
        )

        reply = response.choices[0].message.content
        print(reply)
        return reply
    @staticmethod
    async def generate_summary(messages):
            # prompt_message = "is Please summarize this in first person if user elling about himself or herself else summarize in second or third person and try to get out useful info which can be asked to you later:"
            prompt_message = " could you Write a concise summary or clarification of the question or information i have provided, without directly answering my questions. but i am the narrator"
            # Prepend the prompt message to each user message
            messages_with_prompt = [{'role': 'user', 'content': prompt_message}] +\
                                   [{'role': 'user', 'content': message['content']} for message in messages] +\
                                   [{'role':'system', 'content':"Please use this also  "}]

            response = openai.ChatCompletion.create(
                model='gpt-3.5-turbo',
                messages=messages_with_prompt,
                max_tokens=150,
                temperature=0.1,
                n=1,
                stop=None,
            )

            return response.choices[0].message['content']