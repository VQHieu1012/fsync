from underthesea import sent_tokenize


def chunking_by_sentences(
    text: str, chunk_size: int = 3, overlap: int = 1
) -> list[str]:
    sentences = sent_tokenize(text)

    if not sentences:
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size > 0")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap >= 0 and < chunk_size")

    chunks = []
    i = 0
    total_sentences = len(sentences)

    while i < total_sentences:
        selected_sentences = sentences[i : i + chunk_size]

        chunk_text = " ".join(selected_sentences)
        chunks.append(chunk_text)

        if i + chunk_size >= total_sentences:
            break

        i += chunk_size - overlap

    return chunks


def embed(texts: list[str], model: str = "gemini-embedding-001") -> list[list[float]]:
    from google import genai

    client = genai.Client()
    response = client.models.embed_content(model=model, contents=texts)
    return list(map(lambda n: n.values, response.embeddings))


def embed_voyage(
    texts: list[str], model: str = "voyage-multilingual-2", input_type: str = "document"
) -> list[list[float]]:
    import voyageai

    # VOYAGE_API_KEY
    client = voyageai.Client()
    response = client.embed(texts=texts, model=model, input_type=input_type)
    return response.embeddings


def generate_stream(
    user_message: str, system_message: str = None, model: str = "gemini-2.5-flash"
):
    from google import genai
    from google.genai import types

    client = genai.Client()

    # system instruction
    config = None
    if system_message:
        config = types.GenerateContentConfig(system_instruction=system_message)

    stream = client.models.generate_content_stream(
        model=model, contents=user_message, config=config
    )

    result = ""
    for chunk in stream:
        result += chunk.text or "" + " "
        print(chunk.text or "", end="", flush=True)
    return result.strip()


def generate_embeddings_voyage(
    texts: list[str], input_type: str = "query", model: str = "voyage-3"
) -> list[list[float]]:
    import voyageai

    client = voyageai.Client()

    response = client.embed(texts=texts, model=model, input_type=input_type)

    return response.embeddings


def generate_rerank_stream(
    query: str, documents: list[str], model: str = "rerank-2", top_k: int = 3
):
    import voyageai

    client = voyageai.Client()

    response = client.rerank(query=query, documents=documents, model=model, top_k=top_k)

    results = []
    for idx, r in enumerate(response.results):
        doc_text = documents[r.index]
        score = r.relevance_score

        output = f"\n[Top {idx+1}] Score: {score:.4f} | Text: {doc_text[:100]}...\n"
        print(output, end="", flush=True)

        results.append({"text": doc_text, "score": score, "index": r.index})

    return results
