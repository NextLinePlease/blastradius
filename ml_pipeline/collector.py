import os
import time
import redis

# Connect to Redis (Synchronous is fine here as it runs a dedicated batch loop)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_NAME = "telemetry:requests"
GROUP_NAME = "ml_feature_engine"
CONSUMER_NAME = "collector_1"

# decode_responses=True ensures we get Python strings, not raw bytes
r = redis.from_url(REDIS_URL, decode_responses=True)

def setup_consumer_group():
    try:
        # id='0' means start consuming from the very beginning of the stream
        # mkstream=True creates the stream if no data has been pushed to it yet
        r.xgroup_create(STREAM_NAME, GROUP_NAME, id='0', mkstream=True)
        print(f"[INIT] Created Redis Consumer Group: {GROUP_NAME}")
    except redis.exceptions.ResponseError as e:
        if "BUSYGROUP" in str(e):
            print(f"[INIT] Consumer Group {GROUP_NAME} already exists. Resuming...")
        else:
            raise e

def process_micro_batch():
    # XREADGROUP pulls up to 2000 messages. 
    # block=2000 means if the stream is empty, wait up to 2 seconds before returning.
    # '>' means "give me messages that have NEVER been delivered to any consumer in this group."
    stream_data = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: '>'}, count=2000, block=2000)
    
    if not stream_data:
        return

    stats = {}
    processed_ids = []

    # Parse the batch
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

    # Feature Engineering: Convert raw counts into ML-ready metrics
    for service, data in stats.items():
        avg_latency = data['total_latency'] / data['count']
        error_rate = data['errors'] / data['count']
        throughput = data['count']
        
        # In production, this dictionary is written to a Feature Store (like Redis or Postgres) 
        # so the XGBoost inference endpoint can query the latest state instantly.
        print(f"[FEATURE_VEC] {service:<12} | Avg Latency: {avg_latency:6.2f}ms | Error Rate: {error_rate:6.2%} | Throughput: {throughput}")

    # XACK explicitly tells Redis we successfully engineered these features, safe to remove from PEL
    if processed_ids:
        r.xack(STREAM_NAME, GROUP_NAME, *processed_ids)
        print(f"[ACK] Successfully processed and acknowledged {len(processed_ids)} telemetry events.\n")

if __name__ == "__main__":
    setup_consumer_group()
    print("ML Feature Engine running. Awaiting telemetry...")
    while True:
        try:
            process_micro_batch()
        except Exception as e:
            print(f"[ERROR] Batch processing failed: {e}")
            time.sleep(2)