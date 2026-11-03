import os
import logging

import numpy as np
import pandas as pd
import xgboost as xgb

from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score


# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

RANDOM_STATE = 42
NUM_SAMPLES = 10000

MODEL_DIR = os.getenv("MODEL_DIR", "/app/models")
MODEL_PATH = os.path.join(MODEL_DIR, "xgboost_risk_model.json")

FEATURE_COLUMNS = [
    "avg_latency_ms",
    "error_rate",
    "throughput"
]

TARGET_COLUMN = "target_risk"


# --------------------------------------------------
# 2. LOGGING
# --------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("blast-training")


# --------------------------------------------------
# 3. SYNTHETIC TELEMETRY GENERATION
# --------------------------------------------------

def generate_training_data():

    logger.info("Generating synthetic microservice telemetry...")

    np.random.seed(RANDOM_STATE)

    # Healthy State: 60%
    n_healthy = int(NUM_SAMPLES * 0.6)

    healthy_latency = np.random.normal(20, 5, n_healthy)
    healthy_errors = np.zeros(n_healthy)
    healthy_throughput = np.random.normal(500, 50, n_healthy)
    healthy_risk = np.random.uniform(0.0, 0.1, n_healthy)

    # Degraded State: 30%
    n_degraded = int(NUM_SAMPLES * 0.3)

    degraded_latency = np.random.normal(150, 30, n_degraded)
    degraded_errors = np.random.uniform(0.01, 0.05, n_degraded)
    degraded_throughput = np.random.normal(800, 100, n_degraded)
    degraded_risk = np.random.uniform(0.3, 0.6, n_degraded)

    # Cascading Failure State: 10%
    n_failure = NUM_SAMPLES - n_healthy - n_degraded

    failure_latency = np.random.normal(1200, 200, n_failure)
    failure_errors = np.random.uniform(0.20, 0.99, n_failure)
    failure_throughput = np.random.normal(100, 50, n_failure)
    failure_risk = np.random.uniform(0.8, 1.0, n_failure)

    # Combine all states.
    data = pd.DataFrame({
        "avg_latency_ms": np.concatenate([
            healthy_latency,
            degraded_latency,
            failure_latency
        ]),
        "error_rate": np.concatenate([
            healthy_errors,
            degraded_errors,
            failure_errors
        ]),
        "throughput": np.concatenate([
            healthy_throughput,
            degraded_throughput,
            failure_throughput
        ]),
        "target_risk": np.concatenate([
            healthy_risk,
            degraded_risk,
            failure_risk
        ])
    })

    logger.info("Generated %d synthetic samples.", len(data))

    return data


# --------------------------------------------------
# 4. MODEL TRAINING
# --------------------------------------------------

def train_model(data):

    logger.info("Preparing training and testing datasets...")

    X = data[FEATURE_COLUMNS]
    y = data[TARGET_COLUMN]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE
    )

    logger.info("Training samples: %d", len(X_train))
    logger.info("Testing samples: %d", len(X_test))

    logger.info("Initializing XGBoost Regressor...")

    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=100,
        max_depth=4,
        learning_rate=0.1,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )

    logger.info("Training model...")

    model.fit(X_train, y_train)

    return model, X_test, y_test


# --------------------------------------------------
# 5. MODEL EVALUATION
# --------------------------------------------------

def evaluate_model(model, X_test, y_test):

    logger.info("Evaluating trained model...")

    predictions = model.predict(X_test)

    rmse = np.sqrt(
        mean_squared_error(y_test, predictions)
    )

    r2 = r2_score(y_test, predictions)

    logger.info("Evaluation Results")
    logger.info("RMSE: %.6f", rmse)
    logger.info("R2 Score: %.6f", r2)

    return predictions


# --------------------------------------------------
# 6. FEATURE IMPORTANCE
# --------------------------------------------------

def display_feature_importance(model):

    importance = model.feature_importances_

    importance_df = pd.DataFrame({
        "feature": FEATURE_COLUMNS,
        "importance": importance
    })

    importance_df = importance_df.sort_values(
        by="importance",
        ascending=False
    )

    logger.info("Feature Importance:")

    for _, row in importance_df.iterrows():

        logger.info(
            "%-20s : %.4f",
            row["feature"],
            row["importance"]
        )


# --------------------------------------------------
# 7. MODEL EXPORT
# --------------------------------------------------

def save_model(model):

    logger.info("Exporting trained model...")

    os.makedirs(MODEL_DIR, exist_ok=True)

    model.save_model(MODEL_PATH)

    if not os.path.exists(MODEL_PATH):
        raise RuntimeError("Model export failed.")

    file_size = os.path.getsize(MODEL_PATH)

    logger.info("Model successfully saved.")
    logger.info("Model path: %s", MODEL_PATH)
    logger.info("Model size: %d bytes", file_size)


# --------------------------------------------------
# 8. MAIN EXECUTION
# --------------------------------------------------

def main():

    logger.info("========================================")
    logger.info("BlastRadius ML Training Pipeline")
    logger.info("========================================")

    try:

        # Generate synthetic training data.
        data = generate_training_data()

        # Train XGBoost model.
        model, X_test, y_test = train_model(data)

        # Evaluate model.
        evaluate_model(model, X_test, y_test)

        # Display feature importance.
        display_feature_importance(model)

        # Export model artifact.
        save_model(model)

        logger.info("Training pipeline completed successfully.")

    except Exception:
        logger.exception("Training pipeline failed.")
        raise


if __name__ == "__main__":
    main()