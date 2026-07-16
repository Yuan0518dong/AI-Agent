from backend.app.services import (
    embedding_provider,
    material_ai_service,
    material_store,
    model_usage_service,
    rate_limit_service,
    store,
)


def generate_material_chunks(material: dict, user_id: str | None = None) -> list[dict]:
    source_text = material["content"] or material["url"]
    chunk_texts = material_store.split_material_content(source_text)
    now = store.now_iso()
    with model_usage_service.user_usage_scope(user_id):
        if user_id:
            rate_limit_service.consume_embedding_chunk_quota(user_id, len(chunk_texts))
        with model_usage_service.embedding_usage_scope("chunk", prepaid_chunks=bool(user_id)):
            chunks = [
                {
                    "id": store.make_id("chunk"),
                    "materialId": material["id"],
                    "chunkIndex": index,
                    "content": chunk,
                    "keywords": material_store.extract_keywords(f"{material['title']} {chunk}"),
                    "embedding": embedding_provider.embed_text(f"{material['title']} {chunk}"),
                    "createdAt": now,
                    "updatedAt": now,
                }
                for index, chunk in enumerate(chunk_texts)
            ]
    return material_store.replace_chunks_for_material(material["id"], chunks)


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
