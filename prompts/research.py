from langchain_core.prompts import ChatPromptTemplate


research_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
        You are an AI research assistant.

        Break a complex research question into
        smaller, specific research questions.

        Return only the research questions,
        one per line.
        """
    ),
    (
        "human",
        "{question}"
    )
])