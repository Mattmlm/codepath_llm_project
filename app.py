import os
import chainlit as cl
import base64
import openai

from dotenv import load_dotenv
from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import OpenAI

from prompts import SYSTEM_PROMPT, FUNCTION_KEYWORDS
from rag_utils import get_rag_data

# Load environment variables
load_dotenv()

#setup model options
configurations = {
    "openai_gpt-4o-mini": {
        "endpoint_url": "https://api.openai.com/v1",
        "api_key": os.getenv("OPENAI_API_KEY"),
        "model": "gpt-4o-mini"
    }
}
config_key ="openai_gpt-4o-mini"

# Get selected configuration
config = configurations[config_key]

# Initialize the OpenAI async client
client = wrap_openai(openai.AsyncClient(api_key=config["api_key"], base_url=config["endpoint_url"]))

# general model settings
model_kwargs = {
    "model": config["model"],
    "temperature": 0.3,
    "max_tokens": 500
}

#allow toggle of system prompt
ENABLE_SYSTEM_PROMPT = True

# add system prompt to message history if enabled
@traceable
@cl.on_chat_start
def on_chat_start(): 
    if ENABLE_SYSTEM_PROMPT:
        message_history = [{"role": "system", "content": SYSTEM_PROMPT}]
        cl.user_session.set("message_history", message_history)

@traceable
async def generate_response(client, message_history, gen_kwargs):
    full_response = ""
    stream = await client.chat.completions.create(messages=message_history, stream=True, **gen_kwargs)
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            full_response += token
    print("full response generated:")
    print(full_response)
    
    #try to remove the function call from the response
    print("checking for function call")
    if any(keyword in full_response for keyword in FUNCTION_KEYWORDS):
        # Remove the matching keyword from the full_response
        for keyword in FUNCTION_KEYWORDS:
            if keyword in full_response:
                function_start = full_response.find(keyword)
                function_end = full_response.find(")") + 1
                send_message = full_response[:function_start] + full_response[function_end:]
                print("function call removed")

                await cl.Message(content=send_message).send()
                break  # Assuming only one keyword match is expected
    return cl.Message(content=full_response)

def has_similar_query(message_history, current_query):
    # Define a similarity threshold (adjust as needed)
    similarity_threshold = 0.8

    # Extract previous user queries from the message history
    previous_queries = [msg['content'] for msg in message_history if msg['role'] == 'user']

    # Compare the current query with previous queries
    for query in previous_queries:
        # Calculate similarity (you can use more sophisticated methods here)
        similarity = difflib.SequenceMatcher(None, current_query.lower(), query.lower()).ratio()
        if similarity >= similarity_threshold:
            return True

    return False

@traceable
@cl.on_message
async def on_message(message: cl.Message):
    # Maintain an array of messages in the user session
    message_history = cl.user_session.get("message_history", [])

    # add system prompt in history if not exists
    if ENABLE_SYSTEM_PROMPT and (not message_history or message_history[0].get("role") != "system"):
        system_prompt_content = SYSTEM_PROMPT
        message_history.insert(0, {"role": "system", "content": system_prompt_content})

    # Processing images if they exist
    images = [file for file in message.elements if "image" in file.mime] if message.elements else []

    if images:
        # Read the first image and encode it to base64
        with open(images[0].path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
        message_history.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": message.content if message.content else "What’s in this image?"
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                }
            ]
        })
    else:
        # add in user information and current message for ease of use in API call
        message_history.append({"role": "user", "content": message.content})

    
    response_message = await generate_response(client, message_history, model_kwargs)
    print(f"initial response message: {response_message.content}")
    print("="*50)
    print("~~~~~ start of while loop")
    while any(keyword in response_message.content for keyword in FUNCTION_KEYWORDS):
        for keyword in FUNCTION_KEYWORDS:
            if keyword in response_message.content:
                match keyword:
                    case 'get_rag_data':
                        #get the argument to the function
                        function_start = response_message.content.find("(") + 1
                        function_end = response_message.content.find(")")
                        function_argument = response_message.content[function_start:function_end]
                        #get the rag data
                        rag_data = await get_rag_data(function_argument)
                        #add the rag data to the response message
                        print(f"rag_data:{rag_data[:500]}")
                        message_history.append({"role": "system", "content": f"Fetched Terms of Service data: {rag_data}"})

        # at this point, we've processed the function call and added the context to the message history
        # we can now generate a new response
        response_message = await generate_response(client, message_history, model_kwargs)                   
        print(f"response message after function call: {response_message.content}")
        print("="*50)   
    print("="*50)
    print("end of while loop")
    print(response_message.content)
    await response_message.send()

    # send message history along to model and stream response
    stream = await client.chat.completions.create(messages=message_history,
                                                  stream=True, **model_kwargs)
    # send over parts of response as stream as they're ready
    async for part in stream:
        if token := part.choices[0].delta.content or "":
            await response_message.stream_token(token)
    # finish the response message; no more updates
    await response_message.update()

    # Record the AI's response in the history
    message_history.append({"role": "assistant", "content": response_message.content})
    cl.user_session.set("message_history", message_history)
    await response_message.update()
