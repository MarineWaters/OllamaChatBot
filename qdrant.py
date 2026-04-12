from qdrant_client import QdrantClient, models
import logging
from datetime import datetime, timedelta
from config_reader import config
client = None
api_key=config.api.get_secret_value()
url=config.url.get_secret_value()

model_name = "sentence-transformers/all-MiniLM-L6-v2"
collection_name = "news_collection"
pricing_collection_name = "prices_collection"

def get_client():
    global client
    if client is None:
        try:
            client = QdrantClient(
                url=url,
                api_key=api_key,
            )
            client.get_collections()
            logging.info("✅ Connected to remote Qdrant")
        except Exception as e:
            logging.warning(f"Remote Qdrant failed ({e})")
    return client

cl = get_client()

def insert_prices(payload):
    cl = get_client()
    payload = list(reversed(payload))
    docs = [models.Document(text=d["date"].isoformat(), model=model_name) for d in payload]
    if not cl.collection_exists(pricing_collection_name):
        cl.create_collection(
            pricing_collection_name,
            vectors_config=models.VectorParams(
                size=cl.get_embedding_size(model_name), distance=models.Distance.COSINE)
        )
    maxi = 0
    offset = 0
    try:
        while True:
            points = cl.scroll(collection_name=pricing_collection_name, offset=offset, limit=100, with_payload=False, with_vectors=False)
            if len(points[0]) == 0:
                break
            maxi=int(max(((point.id) for point in points[0])))
            offset += len(points[0])
    except Exception:
        pass
    new_ids = [maxi + 1 + i for i in range(len(payload))]
    logging.info(f"Added {new_ids} for pricing")
    cl.upload_collection(
        collection_name=pricing_collection_name,
        vectors=docs,
        ids=new_ids,
        payload=payload,
    )
    return len(payload)

def get_prices_by_date(date_str):
    cl = get_client()
    if not cl.collection_exists(pricing_collection_name):
        return []
    results = []
    offset = 0
    while True:
        scroll_result = cl.scroll(
            collection_name=pricing_collection_name,
            offset=offset,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        if not scroll_result or not scroll_result[0]:
            break
        for point in scroll_result[0]:
            payload = point.payload or {}
            date_iso = payload.get("date")
            if not date_iso:
                continue
            try:
                point_date = datetime.fromisoformat(date_iso).strftime("%d.%m.%y")
            except Exception:
                continue
            if point_date == date_str:
                results.append(point)
        if scroll_result[-1] is None:
            break
        offset = scroll_result[-1]
    return results

def delete_old_price_points():
    cl = get_client()
    cutoff = (datetime.now() - timedelta(days=8)).replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff_iso = cutoff.isoformat()
    if cl.collection_exists(pricing_collection_name):
        cl.delete(
            collection_name=pricing_collection_name,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="date",
                        range=models.DatetimeRange(lt=cutoff_iso)
                    )
                ]
            )
        )
        logging.info(f"Deleted points with 'date' before {cutoff_iso} from {pricing_collection_name}")
    else:
        cl.create_collection(
            pricing_collection_name,
            vectors_config=models.VectorParams(
                size=cl.get_embedding_size(model_name), distance=models.Distance.COSINE)
        )


def insert_documents(payload):
    cl = get_client()
    payload = list(reversed(payload))
    docs = [models.Document(text=d["title"] + "\n" + d["content"], model=model_name) for d in payload]
    if not cl.collection_exists(collection_name):
        cl.create_collection(
            collection_name,
            vectors_config=models.VectorParams(
                size=cl.get_embedding_size(model_name), distance=models.Distance.COSINE)
        )
    maxi = 0
    offset = 0
    try:
        while True:
            points = cl.scroll(collection_name=collection_name, offset=offset, limit=100, with_payload=False, with_vectors=False)
            if len(points[0]) == 0:
                break
            maxi=int(max(((point.id) for point in points[0])))
            offset += len(points[0])
    except Exception:
        pass
    new_ids = [maxi + 1 + i for i in range(len(payload))]
    logging.info(f"Added {new_ids}")
    cl.upload_collection(
        collection_name=collection_name,
        vectors=docs,
        ids=new_ids,
        payload=payload,
    )
    return len(payload)

def get_existing_titles():
    cl = get_client()
    if not cl.collection_exists(collection_name):
        return set()
    titles = set()
    offset = 0
    while True:
        scroll_result = cl.scroll(
            collection_name=collection_name,
            offset=offset,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        if not scroll_result:
            break
        for point in scroll_result[0]:
            payload = point.payload or {}
            title = payload.get("title")
            if title:
                titles.add(title)
        if scroll_result[-1] is None:
            break
        offset = scroll_result[-1]
    return titles

def get_available_dates():
    try:
        cl = get_client()
        if not cl.collection_exists(collection_name):
            return []
        dates = set()
        offset = 0
        while True:
            scroll_result = cl.scroll(
                collection_name=collection_name,
                offset=offset,
                limit=100,
                with_payload=True,
                with_vectors=False
            )
            if not scroll_result:
                break
            for point in scroll_result[0]:
                payload = point.payload or {}
                date = datetime.fromisoformat(payload.get("date")).strftime("%d.%m.%y")
                if date and date not in dates:
                    try:
                        dates.add(date)
                    except:
                        continue
            if scroll_result[-1] is None:
                break
            offset = scroll_result[-1]
        return sorted(dates, key=lambda x: datetime.strptime(x, "%d.%m.%y"))
    except Exception as e:
        logging.error(f"Dates acquirement failed: {e}")
        return []

def clear_collection():
    cl = get_client()
    if cl.collection_exists(collection_name):
        cl.delete_collection(collection_name)
        return True
    return False

def get_documents_by_date(date_str):
    cl = get_client()
    if not cl.collection_exists(collection_name):
        return []
    results = []
    offset = 0
    while True:
        scroll_result = cl.scroll(
            collection_name=collection_name,
            offset=offset,
            limit=100,
            with_payload=True,
            with_vectors=False
        )
        if not scroll_result or not scroll_result[0]:
            break

        for point in scroll_result[0]:
            payload = point.payload or {}
            date_iso = payload.get("date")
            if not date_iso:
                continue
            try:
                point_date = datetime.fromisoformat(date_iso).strftime("%d.%m.%y")
            except Exception:
                continue
            if point_date == date_str:
                results.append(point)

        if scroll_result[-1] is None:
            break
        offset = scroll_result[-1]
    return results