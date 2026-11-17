import os
from rich import print
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI

load_dotenv()

llm = ChatGoogleGenerativeAI(
   model="gemini-3.6-flash",
    api_key=os.getenv("GOOGLE_API_KEY")
)

# llm = ChatMistralAI(
#     model="mistral-small-latest",
#     api_key=os.getenv("MISTRAL_API_KEY")
# )



def gen_response(messages: str) -> str:
    response = llm.invoke(messages)
    return response.content
