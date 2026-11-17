from prompts.research import research_prompt
from backend.llm import llm
from langchain_core.output_parsers import StrOutputParser
from rich import print

parser = StrOutputParser()

chain = research_prompt | llm | parser

context = """ 

RAG stands for Retrieval-Augmented Generation.
It combines information retrieval with text generation.

"""

 

question = "What is RAG?"

answer = chain.invoke({
    "context": context,
    "question" : question
})



print(answer)