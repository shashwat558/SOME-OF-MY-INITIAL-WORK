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

app = FastAPI()

inngest.fast_api.serve(app, inngest_client, [rag_inngest_pdf])