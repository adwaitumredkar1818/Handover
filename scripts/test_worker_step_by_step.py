import sys
sys.path.insert(0, 'backend')
from app.core.config import get_settings
from app.worker import build_worker_service
import time

print("Building worker service...", flush=True)
settings = get_settings()
composite_worker, engine = build_worker_service(settings)
print(f"Worker built: {composite_worker.worker_id}", flush=True)

print("\n1. Testing ingestion_worker.process_next_job()...", flush=True)
t0 = time.time()
r1 = composite_worker.ingestion_worker.process_next_job()
print(f"Ingestion worker result: {r1} in {time.time()-t0:.2f}s", flush=True)

print("\n2. Testing sync_worker.process_next_job()...", flush=True)
t0 = time.time()
r2 = composite_worker.sync_worker.process_next_job()
print(f"Sync worker result: {r2} in {time.time()-t0:.2f}s", flush=True)

print("\n3. Testing reconstruction_worker.process_next_job()...", flush=True)
t0 = time.time()
r3 = composite_worker.reconstruction_worker.process_next_job() if composite_worker.reconstruction_worker else "None"
print(f"Reconstruction worker result: {r3} in {time.time()-t0:.2f}s", flush=True)

print("\n4. Testing relationship_worker.process_next_job()...", flush=True)
t0 = time.time()
r4 = composite_worker.relationship_worker.process_next_job() if composite_worker.relationship_worker else "None"
print(f"Relationship worker result: {r4} in {time.time()-t0:.2f}s", flush=True)

print("\n5. Testing indexing_worker.process_next_job()...", flush=True)
t0 = time.time()
r5 = composite_worker.indexing_worker.process_next_job() if composite_worker.indexing_worker else "None"
print(f"Indexing worker result: {r5} in {time.time()-t0:.2f}s", flush=True)
