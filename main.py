import logging
from fastapi import FastAPI
import inngest
import inngest.fast_api
from dotenv import load_dotenv
import uuid
import os
import datetime
from inngest.experimental import ai
from data_loader import load_and_chunk_pdf , embed_texts
from vector_db import QdrantStorage
load_dotenv()
from custom_types import RAGChunkAndSrc, RAGQueryResult, RAGSearchResult, RAGUpsertResult
inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger= logging.getLogger("uvicorn"),
    is_production=False,
    serializer=inngest.PydanticSerializer()
)   

@inngest_client.create_function(
    fn_id="RAG: Inngest PDF",
    trigger=inngest.TriggerEvent(event="rag/inngest_pdf")
)



async def rag_inngest_pdf(ctx:inngest.Context):
    
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"];
        source_id = ctx.event.data.get("source_id", pdf_path);
        chunks = load_and_chunk_pdf(pdf_path)
        return RAGChunkAndSrc(chunks=chunks, source_id=source_id);
    
    def _upsert(chunk_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        chunks = chunk_and_src.chunks
        source_id = chunk_and_src.source_id
        vectors = embed_texts(chunks)
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, name=f"{source_id}: {i}")) for i in range(len(chunks))]
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]
        QdrantStorage().upsert(ids, vectors, payloads)
        return RAGUpsertResult(ingested=len(chunks))
    
    chunk_and_src = await ctx.step.run("load_and_chunk",lambda: _load(ctx=ctx), output_type=RAGChunkAndSrc)
    
    ingested = await ctx.step.run("upsert",lambda: _upsert(chunk_and_src), output_type=RAGUpsertResult)
    
    return ingested.model_dump()

@inngest_client.create_function(
    fn_id="RAG: Query",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)

async def rag_query_pdf_ai(ctx: inngest.Context) -> RAGSearchResult:
    def _search(question: str, top_k: int=5):
        query_vec = embed_texts([question])[0]
        store = QdrantStorage()
        found = store.search(query_vec, top_k)
        return RAGSearchResult(contexts=found["contexts"], sources=found["sources"])
        
    question = ctx.event.data["question"]
    top_k = int(ctx.event.data.get["top_k", 5])
    
    found = await ctx.step.run("embed_and_search", lambda: _search(question, top_k), output_type=RAGSearchResult);
    
    context_block = "\n\n".join(f"- {c}" for c in found.contexts)
    user_content = (
        "use the following context to answer the question.\n\n"
        f"Context: \n{context_block}\n\n"
        f"Question: {question}\n"
        "Answer concisely using Context above"
    )
    
    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini"
    )
    
    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter=adapter,
        body={
            "max_token": 1024,
            "temperature": 0.2,
            "messages": [
                    {'role': "system", "content": "You answer questions using only provided context."},
                    {"role": "user", "content": user_content}
            ]
        }
    )
    

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_inngest_pdf])