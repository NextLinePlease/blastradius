import os
import time
import redis
import xgboost as xgb
import pandas as pd

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

print("[INIT] Loading XGBoost Model artifact...")
model = xgb.XGBRegressor()
model.load_model("xgboost_risk_model.json")

# The absolute maximum limits when a service is perfectly healthy
BASE_CAPACITY = 100
BASE_RATE = 10

def run_control_loop():
    print("[START] ML Inference Engine control loop active.")
    while True:
        try:
            # 1. Discover all active services in the Feature Store
            service_keys = r.keys("feature_store:service:*")
            
            if not service_keys:
                time.sleep(1)
                continue
                
            for key in service_keys:
                service_name = key.split(":")[-1]
                
                # 2. Fetch the latest feature vector
                features = r.hgetall(key)
                
                # 3. Imputation (Fail-Safe Defaulting)
                # If a field is missing, we assume catastrophic failure.
                latency = float(features.get('avg_latency_ms', 1200.0))
                error_rate = float(features.get('error_rate', 1.0))
                throughput = float(features.get('throughput', 0.0))
                
                # 4. Format for XGBoost
                df = pd.DataFrame({
                    'avg_latency_ms': [latency],
                    'error_rate': [error_rate],
                    'throughput': [throughput]
                })
                
                # 5. Predict Risk Score
                risk_score = float(model.predict(df)[0])
                risk_score = max(0.0, min(1.0, risk_score)) # Clamp between 0.0 and 1.0
                
                # 6. Dynamic Throttling Math
                # If risk is 0.90, we reduce capacity by 90%.
                # We use max(1, ...) to ensure we never set capacity to 0, which would permanently lock the system.
                new_capacity = max(1, int(BASE_CAPACITY * (1.0 - risk_score)))
                new_rate = max(1, int(BASE_RATE * (1.0 - risk_score)))
                
                # 7. Push Configuration to the Gatekeeper
                config_key = f"gatekeeper:config:{service_name}"
                r.hset(config_key, mapping={
                    "capacity": str(new_capacity),
                    "rate": str(new_rate),
                    "risk": f"{risk_score:.2f}"
                })
                
                print(f"[CONTROL] {service_name:<12} | Risk: {risk_score:5.2f} | Throttle set to: {new_rate} req/sec")
                
            time.sleep(1) # Run the reconciliation loop every 1 second
            
        except Exception as e:
            print(f"[ERROR] Inference loop failed: {e}")
            time.sleep(1)

if __name__ == "__main__":
    run_control_loop()