import os
import time
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_NAME = "telemetry:requests"
GROUP_NAME = "ml_feature_engine"
CONSUMER_NAME = "collector_1"
FEATURE_STORE_PREFIX = "feature_store:service:"

r = redis.from_url(REDIS_URL, decode_responses=True)

def setup_consumer_group():
    try:
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id='0', mkstream=True)
        print(f"[INIT] Created Redis Consumer Group: {GROUP_NAME}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            print(f"[INIT] Consumer Group {GROUP_NAME} already exists. Resuming...")
        else:
            raise e

def process_micro_batch():
    stream_data = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: '>'}, count=2000, block=2000)
    
    if not stream_data:
        return

    stats = {}
    processed_ids = []

    # 1. Parse the batch
    for stream, messages in stream_data:
        for msg_id, payload in messages:
            service = payload.get('service', 'unknown')
            status = int(payload.get('status', 500))
            latency = float(payload.get('latency_ms', 0.0))

            if service not in stats:
                stats[service] = {'count': 0, 'errors': 0, 'total_latency': 0.0}
            
            stats[service]['count'] += 1
            stats[service]['total_latency'] += latency
            if status >= 400:
                stats[service]['errors'] += 1
            
            processed_ids.append(msg_id)

    # 2. Feature Engineering & Persistence via Redis Pipeline
    if processed_ids:
        # We use a pipeline to send all Redis write commands in a single network trip
        pipe = r.pipeline()
        
        for service, data in stats.items():
            avg_latency = data['total_latency'] / data['count']
            error_rate = data['errors'] / data['count']
            throughput = data['count']
            
            store_key = f"{FEATURE_STORE_PREFIX}{service}"
            
            # HSET updates the fields inside the Redis Hash
            pipe.hset(store_key, mapping={
                "avg_latency_ms": f"{avg_latency:.2f}",
                "error_rate": f"{error_rate:.4f}",
                "throughput": throughput,
                "last_updated": time.time()
            })
            # EXPIRE sets a 30-second Time-To-Live. If the service dies, its features evaporate.
            pipe.expire(store_key, 30)
            
            print(f"[STORED] {store_key:<30} | Err: {error_rate:.2%} | Latency: {avg_latency:.2f}ms")

        # XACK to clear the Pending Entries List
        pipe.xack(STREAM_NAME, GROUP_NAME, *processed_ids)
        
        # Execute the entire transaction
        pipe.execute()
        print(f"[ACK] Successfully processed and stored {len(processed_ids)} events.\n")

if __name__ == "__main__":
    setup_consumer_group()
    print("ML Feature Engine running. Awaiting telemetry...")
    while True:
        try:
            process_micro_batch()
        except Exception as e:
            print(f"[ERROR] Batch processing failed: {e}")
            time.sleep(2)