import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

print("[INIT] Generating synthetic microservice telemetry data...")

# Set random seed for reproducibility
np.random.seed(42)
num_samples = 10000

# 1. GENERATE SYNTHETIC DATA
# Healthy State (60% of data): Low latency, 0 error rate, normal throughput
n_healthy = int(num_samples * 0.6)
healthy_latency = np.random.normal(20, 5, n_healthy)
healthy_errors = np.zeros(n_healthy)
healthy_throughput = np.random.normal(500, 50, n_healthy)
healthy_risk = np.random.uniform(0.0, 0.1, n_healthy)

# Degraded State (30% of data): Elevated latency, minor errors, high throughput (retries)
n_degraded = int(num_samples * 0.3)
degraded_latency = np.random.normal(150, 30, n_degraded)
degraded_errors = np.random.uniform(0.01, 0.05, n_degraded)
degraded_throughput = np.random.normal(800, 100, n_degraded)
degraded_risk = np.random.uniform(0.3, 0.6, n_degraded)

# Cascading Failure (10% of data): Extreme latency (TCP timeout territory), massive errors
n_failure = num_samples - n_healthy - n_degraded
failure_latency = np.random.normal(1200, 200, n_failure)
failure_errors = np.random.uniform(0.20, 0.99, n_failure)
failure_throughput = np.random.normal(100, 50, n_failure) # Throughput drops as threads block
failure_risk = np.random.uniform(0.8, 1.0, n_failure)

# Combine into a Pandas DataFrame
data = pd.DataFrame({
    'avg_latency_ms': np.concatenate([healthy_latency, degraded_latency, failure_latency]),
    'error_rate': np.concatenate([healthy_errors, degraded_errors, failure_errors]),
    'throughput': np.concatenate([healthy_throughput, degraded_throughput, failure_throughput]),
    'target_risk': np.concatenate([healthy_risk, degraded_risk, failure_risk])
})

# 2. TRAIN THE XGBOOST MODEL
print("[TRAIN] Splitting data and training Gradient Boosted Trees...")
X = data[['avg_latency_ms', 'error_rate', 'throughput']]
y = data['target_risk']

# Split into 80% training data, 20% testing data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Initialize the XGBoost Regressor
# max_depth=4 prevents overfitting on our synthetic data
# n_estimators=100 means we are building an ensemble of 100 sequential decision trees
model = xgb.XGBRegressor(
    objective='reg:squarederror',
    n_estimators=100,
    max_depth=4,
    learning_rate=0.1
)

model.fit(X_train, y_train)

# 3. EVALUATE AND EXPORT
predictions = model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, predictions))
print(f"[EVAL] Model Root Mean Squared Error (RMSE): {rmse:.4f}")

# Save the trained model artifact
model_path = "xgboost_risk_model.json"
model.save_model(model_path)
print(f"[EXPORT] Model successfully saved to {model_path}")