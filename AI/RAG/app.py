import ast
import builtins
import re
import threading

import numpy as np
import pandas as pd
import streamlit as st
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

MAX_RETRIES = 3
EXEC_TIMEOUT = 15        # seconds allowed for generated code
MAX_INDEX_ROWS = 10000    # cap rows embedded for the text path


# ------------------------------------------------------------------ LLM
# Provider presets: base_url + suggested models (any OpenAI-compatible API works)
PROVIDERS = {
    "DeepSeek": ("https://api.deepseek.com", ["deepseek-chat", "deepseek-reasoner"]),
    "OpenAI": ("https://api.openai.com/v1", ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]),
    "Gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/",
               ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.1-pro-preview"]),
    "Groq": ("https://api.groq.com/openai/v1",
             ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]),
    "OpenRouter": ("https://openrouter.ai/api/v1",
                   ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"]),
    "Together": ("https://api.together.xyz/v1",
                 ["meta-llama/Llama-3.3-70B-Instruct-Turbo"]),
    "Custom": ("", []),
}
CUSTOM_MODEL = "Custom (type below)"


def get_llm(key: str, model: str, base_url: str):
    from langchain_openai import ChatOpenAI
    # Works with any OpenAI-compatible endpoint
    return ChatOpenAI(
        model=model,
        api_key=key,
        base_url=base_url or None,
        temperature=0,
        timeout=60,
        max_retries=2,
    )

# Runtime open-source LLM, used automatically when no API key / model is provided
LOCAL_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
LOCAL_MAX_NEW_TOKENS = 512


@st.cache_resource(show_spinner=False)
def load_local_llm():
    from transformers import AutoModelForCausalLM, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(LOCAL_MODEL)
    model = AutoModelForCausalLM.from_pretrained(LOCAL_MODEL, torch_dtype="auto")
    model.eval()
    return tok, model


def get_local_llm():
    """Wraps the local HF model as a LangChain runnable (prompt value -> text)."""
    tok, model = load_local_llm()
    roles = {"human": "user", "system": "system", "ai": "assistant"}

    def generate(prompt_value) -> str:
        msgs = [{"role": roles.get(m.type, "user"), "content": m.content}
                for m in prompt_value.to_messages()]
        text = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        inputs = tok(text, return_tensors="pt").to(model.device)
        out = model.generate(**inputs, max_new_tokens=LOCAL_MAX_NEW_TOKENS,
                             do_sample=False)
        return tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

    return RunnableLambda(generate)


def resolve_llm(cfg: dict):
    if cfg["local"]:
        return get_local_llm()
    return get_llm(cfg["api_key"], cfg["model"], cfg["base_url"])



def read_csv(file) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [str(c).strip() for c in df.columns]
    return df.drop_duplicates().reset_index(drop=True)


def build_schema(df: pd.DataFrame) -> str:
    lines = [f"Rows: {len(df)}", f"Columns: {list(df.columns)}"]
    for c in df.columns:
        s = df[c]
        lines.append(
            f"- {c} ({s.dtype}), nulls={int(s.isna().sum())}, "
            f"unique={s.nunique()}, sample={s.dropna().unique()[:3].tolist()}"
        )
    return "\n".join(lines)



class TfidfRetriever:
    """No model download needed. Used as fallback."""

    def __init__(self, texts):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(ngram_range=(1, 2))
        self.mat = self.vec.fit_transform(texts)

    def search(self, query, k=5):
        from sklearn.metrics.pairwise import linear_kernel
        scores = linear_kernel(self.vec.transform([query]), self.mat).ravel()
        return [int(i) for i in scores.argsort()[::-1][:k] if scores[i] > 0]


@st.cache_resource
def load_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")


class FaissRetriever:
    """Semantic search. DeepSeek has no embeddings API, so embed locally."""

    def __init__(self, texts):
        from langchain_community.vectorstores import FAISS
        self.store = FAISS.from_texts(
            texts, load_embeddings(), metadatas=[{"i": i} for i in range(len(texts))]
        )

    def search(self, query, k=5):
        return [d.metadata["i"] for d in self.store.similarity_search(query, k=k)]


def build_retriever(df: pd.DataFrame):
    texts = [
        ", ".join(f"{k}={v}" for k, v in r.items())
        for r in df.head(MAX_INDEX_ROWS).to_dict("records")
    ]
    try:
        return FaissRetriever(texts), "FAISS + all-MiniLM-L6-v2 (semantic)"
    except Exception as e:  # safety net if embedding packages/model are unavailable
        return TfidfRetriever(texts), f"TF-IDF fallback ({type(e).__name__})"


SAFE_NAMES = ["len", "sum", "min", "max", "round", "abs", "sorted", "range", "list",
              "dict", "set", "tuple", "str", "int", "float", "bool", "enumerate", "zip",
              "any", "all", "map", "filter", "reversed", "isinstance", "pow", "divmod"]
SAFE_BUILTINS = {n: getattr(builtins, n) for n in SAFE_NAMES}
BLOCKED = {"eval", "exec", "open", "compile", "__import__", "os", "sys",
           "subprocess", "getattr", "setattr", "globals", "locals", "input"}


def validate(code: str):
    for node in ast.walk(ast.parse(code)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise ValueError("Imports are not allowed; only df, pd and np are available")
        if isinstance(node, ast.Name) and node.id in BLOCKED:
            raise ValueError(f"Blocked name: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attribute access is not allowed")


def run_code(code: str, df: pd.DataFrame):
    validate(code)
    env = {"__builtins__": SAFE_BUILTINS, "df": df.copy(), "pd": pd, "np": np}
    box = {}

    def target():
        try:
            exec(code, env)
        except BaseException as e:
            box["err"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(EXEC_TIMEOUT)
    if t.is_alive():
        raise TimeoutError(f"Code ran longer than {EXEC_TIMEOUT}s")
    if "err" in box:
        raise box["err"]
    if "result" not in env:
        raise ValueError("Code did not assign the answer to a variable named `result`")
    return env["result"]


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def to_text(result) -> str:
    if isinstance(result, (pd.DataFrame, pd.Series)):
        return result.head(30).to_string()
    return str(result)


def make_chains(llm):
    parse = StrOutputParser()
    route = ChatPromptTemplate.from_template(
        """Classify the question about a CSV dataset.
Schema:
{schema}

math = calculation, aggregation, counting, ranking, filtering over many rows
text = lookup of specific rows or descriptive/free-text content

Reply with ONE word only: math or text.
Question: {query}"""
    ) | llm | parse

    code = ChatPromptTemplate.from_template(
        """Write pandas code to answer the question.
DataFrame `df` is already loaded. Schema:
{schema}

Rules: use only df, pd and np; no imports; no file or network access;
use the exact column names from the schema;
assign the final answer to a variable named `result`;
return raw Python code only, no explanation.
{feedback}
Question: {query}"""
    ) | llm | parse

    explain = ChatPromptTemplate.from_template(
        """Question: {query}
Exact result computed by code:
{result}

Explain the answer in 1-3 short sentences. Do not recompute; trust the result."""
    ) | llm | parse

    text = ChatPromptTemplate.from_template(
        """Answer the question using ONLY the rows below.
Cite row ids like [row 12]. If the answer is not present, reply "Not found in the data".

Rows:
{context}

Question: {query}"""
    ) | llm | parse

    return route, code, explain, text


def text_path(query, df, retriever, text_chain):
    ids = retriever.search(query, k=5)
    rows = [(i, ", ".join(f"{k}={v}" for k, v in df.iloc[i].items())) for i in ids]
    if not rows:
        return "Not found in the data", rows
    ctx = "\n".join(f"[row {i}] {t}" for i, t in rows)
    return text_chain.invoke({"query": query, "context": ctx}), rows


def answer_query(query, df, schema, retriever, chains):
    route_c, code_c, explain_c, text_c = chains
    route = route_c.invoke({"schema": schema, "query": query}).strip().lower()
    route = "math" if "math" in route else "text"
    errors = []

    if route == "math":
        code, error = "", ""
        for _ in range(MAX_RETRIES):
            feedback = (f"Previous code:\n{code}\nIt failed with: {error}\nFix it."
                        if error else "")
            code = extract_code(code_c.invoke(
                {"schema": schema, "query": query, "feedback": feedback}))
            try:
                result = run_code(code, df)
                answer = explain_c.invoke({"query": query, "result": to_text(result)})
                return {"route": "math", "answer": answer, "code": code,
                        "result": result, "errors": errors}
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                errors.append(error)
        answer, rows = text_path(query, df, retriever, text_c)
        return {"route": "text (math failed, fallback)", "answer": answer,
                "rows": rows, "errors": errors, "code": code}

    answer, rows = text_path(query, df, retriever, text_c)
    return {"route": "text", "answer": answer, "rows": rows, "errors": errors}


def render(out: dict):
    st.caption(f"Route: {out['route']}")
    st.markdown(out["answer"])
    if isinstance(out.get("result"), (pd.DataFrame, pd.Series)):
        st.dataframe(out["result"])
    if out.get("code"):
        with st.expander("Generated code"):
            st.code(out["code"], language="python")
    if out.get("errors"):
        with st.expander(f"Code errors ({len(out['errors'])})"):
            for e in out["errors"]:
                st.code(e)
    if out.get("rows"):
        with st.expander("Retrieved rows"):
            for i, t in out["rows"]:
                st.write(f"**row {i}**: {t}")


def main():
    st.set_page_config(page_title="RAG Data Analytics", page_icon="📊")
    st.title("📊 Data Analytics")

    with st.sidebar:
        provider = st.selectbox("Provider (OpenAI-compatible)", list(PROVIDERS))
        default_url, models = PROVIDERS[provider]
        base_url = st.text_input("Base URL", value=default_url, key=f"url_{provider}",
                                 help="Any OpenAI-compatible endpoint")
        api_key = st.text_input(
            "API Key (optional)", type="password",
            help=f"Leave empty to run the open model {LOCAL_MODEL} locally")
        choice = st.selectbox("Model", models + [CUSTOM_MODEL], key=f"model_{provider}")
        if choice == CUSTOM_MODEL:
            model = st.text_input("Model name", key=f"custom_{provider}",
                                  placeholder="e.g. gpt-4o-mini").strip()
        else:
            model = choice
        uploaded = st.file_uploader("Upload CSV", type="csv")
        use_local = not (api_key.strip() and model)
        st.caption(f"LLM: local {LOCAL_MODEL}" if use_local else f"LLM: {model} via API")

        ready = bool(uploaded)
        configure = st.button("⚙️ Configure & Index", type="primary",
                              disabled=not ready, use_container_width=True,
                              help="Reads the CSV, builds the semantic index and loads the LLM")

    s = st.session_state

    if configure:
        try:
            df = read_csv(uploaded)
        except Exception as e:
            st.error(f"Could not read CSV: {e}")
            st.stop()
        with st.spinner("Indexing CSV (all-MiniLM-L6-v2 embeddings)..."):
            retriever, label = build_retriever(df)
        if use_local:
            with st.spinner(f"Loading local model {LOCAL_MODEL} (first run downloads it)..."):
                try:
                    load_local_llm()
                except Exception as e:
                    st.error(f"Could not load the local model: {type(e).__name__}: {e}")
                    st.stop()
        s.update(configured=True, df=df, schema=build_schema(df),
                 retriever=retriever, label=label, messages=[],
                 cfg={"api_key": api_key, "model": model, "base_url": base_url,
                      "file": uploaded.name, "local": use_local})

    if not s.get("configured"):
        st.info("Upload a CSV (add an API key and model, or leave empty for the local model) "
                "and click **Configure & Index**.")
        st.stop()

    cfg = s.cfg
    active = f"{LOCAL_MODEL} (local)" if cfg["local"] else cfg["model"]
    st.sidebar.success(f"Active: {active} | {cfg['file']}")
    st.sidebar.caption(f"Retriever: {s.label}")
    current = {"api_key": api_key, "model": model, "base_url": base_url,
               "file": uploaded.name if uploaded else None, "local": use_local}
    if current != cfg:
        st.sidebar.warning("Settings changed. Click Configure & Index to apply.")
    chains = make_chains(resolve_llm(cfg))

    with st.expander("Data preview and schema"):
        st.dataframe(s.df.head(10))
        st.code(s.schema)

    for m in s.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"]) if m["role"] == "user" else render(m["out"])

    if query := st.chat_input("Ask a question about your data"):
        s.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    out = answer_query(query, s.df, s.schema, s.retriever, chains)
                except Exception as e:
                    out = {"route": "error", "answer": f"**Error:** {type(e).__name__}: {e}"}
            render(out)
        s.messages.append({"role": "assistant", "out": out})


if __name__ == "__main__":
    main()
