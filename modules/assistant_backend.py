#!/usr/bin/env python

# RagAiAgent - (c) Eric Dodémont, 2024.

"""
This function runs the backend. It instanciates the tools and the agent.
"""

# Only to be able to run on Github Codespace
__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import streamlit as st
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_openai import AzureChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_vertexai import ChatVertexAI
from langchain_community.chat_models import ChatOllama
from langchain_chroma import Chroma
import chromadb
from chromadb.config import Settings
import os
from langchain.tools.retriever import create_retriever_tool
from langchain_community.tools.tavily_search import TavilySearchResults
from langgraph.prebuilt import create_react_agent
#from langgraph.checkpoint.sqlite import SqliteSaver  # on disk checkpointer (memory)
#from langgraph.checkpoint import MemorySaver  # an in-memory checkpointer (memory)
from langgraph.checkpoint.memory import MemorySaver  # an in-memory checkpointer (memory)
from langchain_core.tools import tool

from config.config import *


@tool
def tavily_search_with_images(query: str):
    """Search the Internet for answers and images related to the question."""
    search = TavilySearchResults(
        max_results=2,
        include_answer=False,
        include_raw_content=False,
        include_images=True,
        #response_format="content_and_artifact",
    )
    answer = search.invoke({"args": {'query': query}, "type": "tool_call", "id": "ragai1234", "name": "tavily"})
    return(answer)


@tool
def fake_tool(query: str):
    """Fake tool."""
    return(query)


@st.cache_resource
def instanciate_ai_assistant_graph_agent(model, temperature, enable_tavily, enable_rag):
    """
    Instantiate tools (retrievers, web search) and graph agent.
    Steps: Retrieve and generate.
    """

    try:

        embedding_model = OpenAIEmbeddings(model=EMBEDDING_MODEL)  # 3072 dimensions vectors used to embed the PDF and Web pages and the questions

        if CHROMA_SERVER:

            # Run the Chroma server (the app and the db can run on different servers)

            chroma_server_password = os.getenv("CHROMA_SERVER_AUTHN_CREDENTIALS", "YYYY")
            chroma_client = chromadb.HttpClient(host=CHROMA_SERVER_HOST, port=CHROMA_SERVER_PORT, settings=Settings(chroma_client_auth_provider="chromadb.auth.token_authn.TokenAuthClientProvider", chroma_client_auth_credentials=chroma_server_password))
            vector_db = Chroma(embedding_function=embedding_model, collection_name=CHROMA_COLLECTION_NAME, client=chroma_client)

        else:

            # Save the DB on the local filesystem (the app has to run on the same server)

            vector_db = Chroma(embedding_function=embedding_model, collection_name=CHROMA_COLLECTION_NAME, persist_directory="./chromadb")

        docs = vector_db.get()
        documents = docs["documents"]

    except Exception as e:
        st.write("Error: Cannot instanciate the DB!")
        st.write(f"Error: {e}")        

    # Instanciate the model

    try:

        if model == OLLAMA_MENU:
            llm = ChatOllama(model=OLLAMA_MODEL, temperature=temperature, base_url=OLLAMA_URL)
        elif model == ANTHROPIC_MENU:
            llm = ChatAnthropic(model_name=ANTHROPIC_MODEL, temperature=temperature, max_tokens=4000)
        elif model == VERTEXAI_MENU:
            llm = ChatVertexAI(model_name=VERTEXAI_MODEL, temperature=temperature, max_output_tokens=4000)
        elif model == OPENAI_MENU:
            llm = ChatOpenAI(model=OPENAI_MODEL, temperature=temperature)
        elif model == AZURE_MENU:
            llm = AzureChatOpenAI(
                azure_deployment=AZURE_MODEL,
                api_version="2023-03-15-preview",
                temperature=0,
                max_tokens=None,
                timeout=None,
                max_retries=2,
                # organization="...",
                # model="gpt-35-turbo",
                # model_version="0125",
                # other params...
            )
        elif model == GOOGLE_MENU:
            llm = ChatGoogleGenerativeAI(model=GOOGLE_MODEL, temperature=temperature)
        else:
            st.write("Error: No model available!")
            st.write("Model: {model}")
            quit()

    except Exception as e:
        st.write("Error: Cannot instanciate any model!")
        st.write(f"Error: {e}")

    # Instanciate the retrievers (RAG)

    try:

        vector_retriever = vector_db.as_retriever(search_type="similarity", search_kwargs={"k": VECTORDB_MAX_RESULTS})

        keyword_retriever = BM25Retriever.from_texts(documents)
        keyword_retriever.k = BM25_MAX_RESULTS

        ensemble_retriever = EnsembleRetriever(retrievers=[keyword_retriever, vector_retriever], weights=[0.5, 0.5])

    except Exception as e:
        st.write("Error: Cannot instanciate the retrievers! Is the DB available?")
        st.write(f"Error: {e}")

    # Instanciate the tools and the agent

    try:

        #search = TavilySearchResults(max_results=2, include_images=True, include_answer=False)

        rag = create_retriever_tool(
            ensemble_retriever,
            "belgian_monarchy_art_explorer_retriever",
            "Search the Knowledge Base for artworks related to the Belgian monarchy."
        )

        if enable_rag and enable_tavily:
            tools = [tavily_search_with_images, rag]
        elif enable_tavily:
            tools = [tavily_search_with_images]
        elif enable_rag:
            tools = [rag]
        else:
            tools = [fake_tool]
            
        #memory = SqliteSaver.from_conn_string(":memory:")
        memory = MemorySaver()

        ai_assistant_graph_agent = create_react_agent(model=llm, tools=tools, checkpointer=memory, messages_modifier=SYSTEM_PROMPT)

    except Exception as e:
        st.write("Error: Cannot instanciate the agent!")
        st.write(f"Error: {e}")
        ai_assistant_graph_agent = None

    return ai_assistant_graph_agent
