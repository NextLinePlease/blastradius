import os
import time
import signal
import logging
import redis
import xgboost as xgb
import pandas as pd

# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MODEL_PATH = os.getenv(
    "MODEL_PATH",
    "/app/models/xgboost_risk_model.json"
)

BASE_CAPACITY = int(os.getenv("BASE_CAPACITY", "100"))
BASE_RATE = int(os.getenv("BASE_RATE", "10"))
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1"))

# --------------------------------------------------
# 2. LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("blast-inference")

# --------------------------------------------------
# 3. REDIS CONNECTION
# --------------------------------------------------

r = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    health_check_interval=30
)

# --------------------------------------------------
# 4. LOAD XGBOOST MODEL
# --------------------------------------------------

logger.info("Loading XGBoost model artifact...")

model = xgb.XGBRegressor()
model.load_model(MODEL_PATH)

logger.info("Model loaded successfully from %s", MODEL_PATH)

# --------------------------------------------------
# 5. SHUTDOWN HANDLING
# --------------------------------------------------

running = True


def shutdown_handler(signum, frame):
    global running
    logger.info("Shutdown signal received.")
    running = False


signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# --------------------------------------------------
# 6. FEATURE EXTRACTION
# --------------------------------------------------

def extract_features(key):
    features = r.hgetall(key)

    latency = float(features.get("avg_latency_ms", 1200.0))
    error_rate = float(features.get("error_rate", 1.0))
    throughput = float(features.get("throughput", 0.0))

    return pd.DataFrame({
        "avg_latency_ms": [latency],
        "error_rate": [error_rate],
        "throughput": [throughput]
    })


# --------------------------------------------------
# 7. RISK PREDICTION
# --------------------------------------------------

def predict_risk(features):
    prediction = float(model.predict(features)[0])

    # Keep risk score within [0, 1].
    return max(0.0, min(1.0, prediction))


# --------------------------------------------------
# 8. DYNAMIC RATE-LIMIT CONFIGURATION
# --------------------------------------------------

def calculate_limits(risk_score):
    new_capacity = max(
        1,
        int(BASE_CAPACITY * (1.0 - risk_score))
    )

    new_rate = max(
        1,
        int(BASE_RATE * (1.0 - risk_score))
    )

    return new_capacity, new_rate


def publish_configuration(service_name, risk_score):
    capacity, rate = calculate_limits(risk_score)

    config_key = f"gatekeeper:config:{service_name}"

    r.hset(
        config_key,
        mapping={
            "capacity": str(capacity),
            "rate": str(rate),
            "risk": f"{risk_score:.4f}",
            "updated_at": str(time.time())
        }
    )

    logger.info(
        "%-12s | Risk: %.2f | Capacity: %d | Rate: %d req/sec",
        service_name,
        risk_score,
        capacity,
        rate
    )


# --------------------------------------------------
# 9. MAIN INFERENCE CONTROL LOOP
# --------------------------------------------------

def run_control_loop():

    logger.info("ML Inference Engine control loop started.")

    while running:

        try:
            # Discover active services in the feature store.
            service_keys = r.keys("feature_store:service:*")

            if not service_keys:
                time.sleep(POLL_INTERVAL)
                continue

            for key in service_keys:

                if not running:
                    break

                service_name = key.split(":")[-1]

                try:
                    # Extract latest service metrics.
                    features = extract_features(key)

                    # Predict deployment/service risk.
                    risk_score = predict_risk(features)

                    # Publish dynamic rate-limit configuration.
                    publish_configuration(
                        service_name,
                        risk_score
                    )

                except (ValueError, TypeError) as error:
                    logger.error(
                        "Invalid features for %s: %s",
                        service_name,
                        error
                    )

                except redis.RedisError as error:
                    logger.error(
                        "Redis error processing %s: %s",
                        service_name,
                        error
                    )

            time.sleep(POLL_INTERVAL)

        except redis.RedisError as error:
            logger.error("Redis connection error: %s", error)
            time.sleep(POLL_INTERVAL)

        except Exception:
            logger.exception("Unexpected inference loop failure.")
            time.sleep(POLL_INTERVAL)

    logger.info("ML Inference Engine stopped.")


# --------------------------------------------------
# 10. APPLICATION ENTRY POINT
# --------------------------------------------------

if __name__ == "__main__":

    try:
        r.ping()
        logger.info("Redis connection established.")

        run_control_loop()

    except redis.RedisError as error:
        logger.critical("Unable to connect to Redis: %s", error)
        raise

    finally:
        r.close()
        logger.info("Redis connection closed.")