import asyncio
import httpx
import time

# Service A (our Gateway) is exposed on localhost port 8000
TARGET_URL = "http://localhost:8000/api/data"
CONCURRENT_REQUESTS = 50
TOTAL_REQUESTS = 500

async def make_request(client: httpx.AsyncClient, req_id: int):
    start_time = time.time()
    try:
        response = await client.get(TARGET_URL, timeout=10.0)
        latency = (time.time() - start_time) * 1000
        return response.status_code, latency
    except Exception as e:
        return 500, 0.0

async def worker(client: httpx.AsyncClient, queue: asyncio.Queue, results: list):
    """Workers constantly pull tasks from the queue and execute them."""
    while not queue.empty():
        req_id = await queue.get()
        status, latency = await make_request(client, req_id)
        results.append((status, latency))
        queue.task_done()

async def main():
    print(f"Starting Load Test: {TOTAL_REQUESTS} requests, {CONCURRENT_REQUESTS} concurrent workers.")
    
    # We use a single client for the load generator to avoid TCP exhaustion on our end!
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=CONCURRENT_REQUESTS)) as client:
        queue = asyncio.Queue()
        for i in range(TOTAL_REQUESTS):
            queue.put_nowait(i)
            
        results = []
        start_time = time.time()
        
        # Spin up exactly CONCURRENT_REQUESTS workers
        tasks = []
        for _ in range(CONCURRENT_REQUESTS):
            task = asyncio.create_task(worker(client, queue, results))
            tasks.append(task)
            
        # Wait for all queue items to be processed
        await queue.join()
        
        # Clean up worker tasks
        for task in tasks:
            task.cancel()
            
        total_time = time.time() - start_time
        
    # Tally results
    status_counts = {}
    total_latency = 0
    for status, latency in results:
        status_counts[status] = status_counts.get(status, 0) + 1
        total_latency += latency
        
    avg_latency = total_latency / len(results) if results else 0
    req_per_sec = TOTAL_REQUESTS / total_time
    
    print("\n--- Load Test Results ---")
    print(f"Total Time: {total_time:.2f} seconds")
    print(f"Throughput: {req_per_sec:.2f} req/sec")
    print(f"Average Latency: {avg_latency:.2f} ms")
    print("Status Codes:")
    for status, count in status_counts.items():
        print(f"  HTTP {status}: {count}")

if __name__ == "__main__":
    asyncio.run(main())