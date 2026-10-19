"""
CSV RAG Agent: Streamlit + LangChain + DeepSeek
Run: streamlit run app.py
"""
import ast
import builtins

import numpy as np
import pandas as pd
import streamlit as st
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

MAX_RETRIES = 3

st.set_page_config(page_title="CSV RAG Agent", page_icon="📊")
st.title("📊 CSV RAG Agent")

# ------------------------------------------------------------------ SIDEBAR
with st.sidebar:
    api_key = st.text_input("DeepSeek API Key", type="password")
    uploaded = st.file_uploader("Upload CSV", type="csv")


# ------------------------------------------------------------------ LLM
def get_llm(key: str) -> ChatOpenAI:
    # DeepSeek exposes an OpenAI-compatible API
    return ChatOpenAI(
        model="deepseek-chat",
        api_key=key,
        base_url="https://api.deepseek.com",
        temperature=0,
    )


# ------------------------------------------------------------------ INGESTION
@st.cache_resource
def load_embeddings():
    # DeepSeek has no embeddings API, so use a local model
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


def build_schema(df: pd.DataFrame) -> str:
    lines = [f"Rows: {len(df)}"]
    for c in df.columns:
        s = df[c]
        lines.append(
            f"- {c} ({s.dtype}), nulls={s.isna().sum()}, "
            f"unique={s.nunique()}, sample={s.dropna().unique()[:3].tolist()}"
        )
    return "\n".join(lines)


def build_index(df: pd.DataFrame) -> FAISS:
    docs = [
        Document(
            page_content=", ".join(f"{k}={v}" for k, v in row.items()),
            metadata={"row_id": int(i)},
        )
        for i, row in df.iterrows()
    ]
    return FAISS.from_documents(docs, load_embeddings())


# ------------------------------------------------------------------ SANDBOX
SAFE_NAMES = ["len", "sum", "min", "max", "round", "abs", "sorted", "range",
              "list", "dict", "set", "str", "int", "float", "enumerate", "zip"]
SAFE_BUILTINS = {n: getattr(builtins, n) for n in SAFE_NAMES}
BLOCKED = {"eval", "exec", "open", "compile", "__import__", "os", "sys",
           "subprocess", "getattr", "globals", "locals"}


def validate(code: str):
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Imports are not allowed")
        if isinstance(node, ast.Name) and node.id in BLOCKED:
            raise ValueError(f"Blocked name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder access is not allowed")


def run_code(code: str, df: pd.DataFrame):
    validate(code)
    env = {"df": df.copy(), "pd": pd, "np": np}
    exec(code, {"__builtins__": SAFE_BUILTINS}, env)
    return env["result"]


# ------------------------------------------------------------------ CHAINS
def make_chains(llm):
    route_chain = ChatPromptTemplate.from_template(
        """Classify the question about a CSV dataset.
Schema:
{schema}

math = calculation, aggregation, counting, ranking, filtering over many rows
text = lookup of specific rows or descriptive/free-text content

Reply with ONE word only: math or text.
Question: {query}"""
    ) | llm | StrOutputParser()

    code_chain = ChatPromptTemplate.from_template(
        """Write pandas code to answer the question.
DataFrame `df` is already loaded. Schema:
{schema}

Rules: use only pd and np; no imports; no file or network access;
assign the final answer to a variable named `result`;
return raw code only, no markdown.
{feedback}
Question: {query}"""
    ) | llm | StrOutputParser()

    math_explain_chain = ChatPromptTemplate.from_template(
        """Question: {query}
Exact result computed by code: {result}

Explain the answer in 1-3 short sentences. Do not recompute; trust the result."""
    ) | llm | StrOutputParser()

    text_chain = ChatPromptTemplate.from_template(
        """Answer the question using ONLY the rows below.
Cite row ids like [row 12]. If the answer is not present, reply "Not found in the data".

Rows:
{context}

Question: {query}"""
    ) | llm | StrOutputParser()

    return route_chain, code_chain, math_explain_chain, text_chain


# ------------------------------------------------------------------ AGENT
def text_path(query, store, text_chain):
    docs = store.similarity_search(query, k=5)
    ctx = "\n".join(f"[row {d.metadata['row_id']}] {d.page_content}" for d in docs)
    return text_chain.invoke({"query": query, "context": ctx}), docs


def answer_query(query, df, schema, store, chains):
    route_chain, code_chain, math_explain_chain, text_chain = chains
    route = route_chain.invoke({"schema": schema, "query": query}).strip().lower()
    route = "math" if "math" in route else "text"

    if route == "math":
        code, error = "", ""
        for _ in range(MAX_RETRIES):
            feedback = (f"Previous code:\n{code}\nFailed with: {error}\nFix it."
                        if error else "")
            code = code_chain.invoke(
                {"schema": schema, "query": query, "feedback": feedback}
            ).replace("```python", "").replace("```", "").strip()
            try:
                result = run_code(code, df)
                explanation = math_explain_chain.invoke(
                    {"query": query, "result": str(result)}
                )
                return {"route": "math", "answer": explanation,
                        "code": code, "result": result}
            except Exception as e:  # self-correction loop
                error = f"{type(e).__name__}: {e}"
        # fallback after repeated failures
        answer, docs = text_path(query, store, text_chain)
        return {"route": "text (fallback)", "answer": answer, "docs": docs}

    answer, docs = text_path(query, store, text_chain)
    return {"route": "text", "answer": answer, "docs": docs}


# ------------------------------------------------------------------ UI
if not api_key or not uploaded:
    st.info("Enter your DeepSeek API key and upload a CSV in the sidebar.")
    st.stop()

if st.session_state.get("file_name") != uploaded.name:
    df = pd.read_csv(uploaded).drop_duplicates()
    with st.spinner("Indexing CSV..."):
        st.session_state.update(
            file_name=uploaded.name, df=df, schema=build_schema(df),
            store=build_index(df), messages=[],
        )

df, schema, store = st.session_state.df, st.session_state.schema, st.session_state.store
chains = make_chains(get_llm(api_key))

with st.expander("Data preview and schema"):
    st.dataframe(df.head(10))
    st.code(schema)

# Replay chat history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if query := st.chat_input("Ask a question about your data"):
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                out = answer_query(query, df, schema, store, chains)
            except Exception as e:
                out = {"route": "error", "answer": f"Error: {e}"}

        st.caption(f"Route: {out['route']}")
        st.markdown(out["answer"])
        if "code" in out:
            with st.expander("Generated code"):
                st.code(out["code"], language="python")
            if isinstance(out["result"], (pd.DataFrame, pd.Series)):
                st.dataframe(out["result"])
        if "docs" in out:
            with st.expander("Retrieved rows"):
                for d in out["docs"]:
                    st.write(f"**row {d.metadata['row_id']}**: {d.page_content}")

    st.session_state.messages.append({"role": "assistant", "content": out["answer"]})
