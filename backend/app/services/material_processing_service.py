from backend.app.services import (
    embedding_provider,
    material_ai_service,
    material_store,
    model_usage_service,
    rate_limit_service,
    store,
)


def generate_material_chunks(material: dict, user_id: str | None = None) -> list[dict]:
    chunks = build_material_chunks(material)
    if not chunks:
        return material_store.replace_chunks_for_material(material["id"], [])
    persisted_chunks = material_store.replace_chunks_for_material(material["id"], chunks)
    try:
        return embed_material_chunks(material, persisted_chunks, user_id, strict=False)
    except Exception:
        return persisted_chunks


def build_material_chunks(material: dict) -> list[dict]:
    located_chunks = material_store.split_material_content_with_locations(material)
    now = store.now_iso()
    return [
        {
            "id": store.make_id("chunk"),
            "materialId": material["id"],
            "chunkIndex": index,
            "content": located["content"],
            "keywords": material_store.extract_keywords(f"{material['title']} {located['content']}"),
            "embedding": [],
            "pageNumber": located.get("pageNumber"),
            "headingPath": located.get("headingPath", ""),
            "paragraphIndex": located.get("paragraphIndex"),
            "createdAt": now,
            "updatedAt": now,
        }
        for index, located in enumerate(located_chunks)
    ]


def embed_material_chunks(
    material: dict,
    chunks: list[dict],
    user_id: str | None = None,
    *,
    strict: bool,
) -> list[dict]:
    if not chunks:
        return []
    now = store.now_iso()
    provider = embedding_provider.get_embedding_provider()
    with model_usage_service.user_usage_scope(user_id):
        if user_id:
            rate_limit_service.consume_embedding_chunk_quota(user_id, len(chunks))
        with model_usage_service.embedding_usage_scope("chunk", prepaid_chunks=bool(user_id)):
            embedded_chunks = []
            for chunk in chunks:
                source = f"{material['title']} {chunk['content']}"
                try:
                    embedding = provider.embed(source) if strict else embedding_provider.embed_text(source)
                except Exception:
                    if strict:
                        raise
                    embedding = []
                embedded_chunks.append({**chunk, "embedding": embedding, "updatedAt": now})
    return material_store.update_chunk_embeddings(material["id"], embedded_chunks)


def summarize_material(material: dict, user_id: str | None = None) -> dict:
    material_id = material["id"]
    now = store.now_iso()
    existing_summary = material_store.get_material_summary(material_id)
    with model_usage_service.user_usage_scope(user_id):
        summary = {
            "materialId": material_id,
            **material_ai_service.summarize_material(material),
            "createdAt": existing_summary["createdAt"] if existing_summary else now,
            "updatedAt": now,
        }
    return material_store.save_material_summary(material_id, summary)
