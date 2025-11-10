import os
import streamlit as st
from dotenv import load_dotenv
from haystack import Pipeline
from haystack.utils import Secret
from haystack.components.embedders import SentenceTransformersTextEmbedder
from haystack.components.builders import ChatPromptBuilder
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses import ChatMessage
from haystack_integrations.document_stores.mongodb_atlas import MongoDBAtlasDocumentStore
from haystack_integrations.components.retrievers.mongodb_atlas import MongoDBAtlasEmbeddingRetriever
from haystack_experimental.chat_message_stores.in_memory import InMemoryChatMessageStore
from haystack_experimental.components.retrievers import ChatMessageRetriever
from haystack_experimental.components.writers import ChatMessageWriter

# Load Environment Variables

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
MONGO_CONN = os.getenv("MONGO_CONNECTION_STRING")

if not OPENAI_KEY or not MONGO_CONN:
    st.error("Missing environment variables. Please check your .env file.")
    st.stop()

# MongoDB Connections

product_store = MongoDBAtlasDocumentStore(
    database_name="depato_store",
    collection_name="products",
    vector_search_index="vector_index",
    full_text_search_index="search_index",
)

common_store = MongoDBAtlasDocumentStore(
    database_name="depato_store",
    collection_name="common_information",
    vector_search_index="vector_index_common",
    full_text_search_index=None,
)

# Define Prompt Templates

SYSTEM_PROMPT = ChatMessage.from_system(
    "You are SmartShopper — a world-class AI shopping assistant that helps users explore products, answer FAQs, and make decisions effortlessly."
)

USER_PROMPT_TEMPLATE = """
Relevant information:
{% for doc in documents %}
{{ doc.content }}
{% endfor %}

Conversation so far:
{% for mem in memories %}
{{ mem.sender }}: {{ mem.text }}
{% endfor %}

User request: {{query}}

Respond in a warm, concise, and conversational tone — as a professional shopping assistant would.
"""
USER_PROMPT = ChatMessage.from_user(USER_PROMPT_TEMPLATE)

# Build Independent Pipelines

def build_pipeline(document_store):
    memory_store = InMemoryChatMessageStore()
    memory_retriever = ChatMessageRetriever(memory_store)
    memory_writer = ChatMessageWriter(memory_store)

    pipe = Pipeline()
    pipe.add_component("memory_retriever", memory_retriever)
    pipe.add_component("embedder", SentenceTransformersTextEmbedder(model="sentence-transformers/all-mpnet-base-v2"))
    pipe.add_component("retriever", MongoDBAtlasEmbeddingRetriever(document_store=document_store, top_k=5))
    pipe.add_component("prompt_builder", ChatPromptBuilder(template=[SYSTEM_PROMPT, USER_PROMPT]))
    pipe.add_component("generator", OpenAIChatGenerator(model="gpt-4.1", api_key=Secret.from_token(OPENAI_KEY)))
    pipe.add_component("memory_writer", memory_writer)

    pipe.connect("memory_retriever", "prompt_builder.memories")
    pipe.connect("embedder", "retriever.query_embedding")
    pipe.connect("retriever", "prompt_builder.documents")
    pipe.connect("prompt_builder.prompt", "generator.messages")
    pipe.connect("generator.replies", "memory_writer.messages")

    return pipe


product_pipeline = build_pipeline(product_store)
common_pipeline = build_pipeline(common_store)

# Streamlit UI — Premium Gold Theme

st.set_page_config(page_title="SmartShopper AI", page_icon="🛍️", layout="wide")

st.markdown(
    """
    <style>
    body {
        background: linear-gradient(to bottom right, #FFF9E6, #FFF3C4);
        font-family: 'Inter', sans-serif;
        color: #3C3C3C;
    }
    .stChatInput input {
        background-color: #FFFDF3;
        border: 1px solid #E0C97F;
        border-radius: 12px;
        padding: 10px;
        font-size: 16px;
        color: #3C3C3C;
    }
    .stChatMessage {
        border-radius: 16px;
        padding: 12px 16px;
        background-color: #FFFAE1 !important;
    }
    .stMarkdown, .stText {
        font-family: 'Inter', sans-serif;
        color: #3C3C3C;
    }
    h1 {
        text-align: center;
        color: #6E5B28;
        font-weight: 800;
        margin-bottom: 0.2em;
    }
    .subtitle {
        text-align: center;
        color: #8B7E45;
        font-size: 16px;
        margin-bottom: 2em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("<h1>🛍️ SmartShopper Assistant</h1>", unsafe_allow_html=True)
st.markdown("<p class='subtitle'>Your intelligent shopping & FAQ companion✨</p>", unsafe_allow_html=True)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Routing Logic (Semantic Intent)

def route_pipeline(query: str):
    q = query.lower()
    faq_keywords = ["refund", "return", "delivery", "payment", "order", "cancel", "shipping", "support", "account"]
    product_keywords = ["buy", "price", "color", "size", "material", "product", "jacket", "shirt", "dress", "recommend", "cotton", "brand"]

    if any(word in q for word in faq_keywords):
        return common_pipeline, "📦 FAQ Query"
    elif any(word in q for word in product_keywords):
        return product_pipeline, "🧢 Product Query"
    else:
        return product_pipeline, "🧠 General Query"

# Chat Input + Processing

user_input = st.chat_input("Ask me anything about our products or store policies...")

if user_input:
    st.session_state.chat_history.append({"role": "user", "content": user_input})
    chosen_pipeline, pipeline_type = route_pipeline(user_input)

    with st.spinner(f"🔍 Processing your {pipeline_type}..."):
        try:
            response = chosen_pipeline.run(
                data={
                    "embedder": {"text": user_input},
                    "prompt_builder": {"query": user_input},
                },
                include_outputs_from=["generator"]
            )
            ai_reply = response["generator"]["replies"][0].text.strip()
            st.session_state.chat_history.append({"role": "assistant", "content": ai_reply})
        except Exception as e:
            st.error(f"Error while processing {pipeline_type}: {e}")

# Chat Display — Clean Bubble UI

for chat in st.session_state.chat_history:
    if chat["role"] == "user":
        with st.chat_message("user"):
            st.markdown(f"<b>You:</b> {chat['content']}", unsafe_allow_html=True)
    else:
        with st.chat_message("assistant"):
            st.markdown(f"<b>SmartShopper:</b> {chat['content']}", unsafe_allow_html=True)