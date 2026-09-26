"""
IntelliFlow 2.0 — Specialized Model Training Pipeline
Trains separate, dedicated models for:
1. Traffic Impact Simulator (models/impact/impact_regressor.pkl)
2. Traffic Anomaly Detector (models/anomaly/anomaly_detector.pkl)
3. Network Ripple Predictor (models/optimizer/ripple_predictor.pkl)

Does NOT overwrite existing BEST_classifier.pkl or BEST_regressor.pkl.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor, IsolationForest
from sklearn.multioutput import MultiOutputRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(BASE_DIR, "dataset", "Banglore_traffic_Dataset.csv")
MODELS_DIR = os.path.join(BASE_DIR, "models")
METADATA_DIR = os.path.join(BASE_DIR, "metadata")

os.makedirs(os.path.join(MODELS_DIR, "impact"), exist_ok=True)
os.makedirs(os.path.join(MODELS_DIR, "anomaly"), exist_ok=True)
os.makedirs(os.path.join(MODELS_DIR, "optimizer"), exist_ok=True)

def load_and_preprocess_dataset():
    print(f"Loading raw dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    
    # Standardize column names
    col_map = {
        'Traffic Volume': 'vehicle_count',
        'Average Speed': 'avg_speed',
        'Travel Time Index': 'travel_time_index',
        'Congestion Level': 'congestion_level',
        'Road Capacity Utilization': 'capacity_utilization',
        'Incident Reports': 'incident_reports',
        'Environmental Impact': 'env_impact',
        'Public Transport Usage': 'pt_usage',
        'Traffic Signal Compliance': 'signal_compliance',
        'Pedestrian and Cyclist Count': 'ped_count',
        'Weather Conditions': 'weather',
        'Roadwork and Construction Activity': 'roadwork',
    }
    df = df.rename(columns=col_map)
    
    # Fill NAs
    df['vehicle_count'] = df['vehicle_count'].fillna(df['vehicle_count'].median())
    df['avg_speed'] = df['avg_speed'].fillna(df['avg_speed'].median())
    df['travel_time_index'] = df['travel_time_index'].fillna(1.2)
    df['congestion_level'] = df['congestion_level'].fillna(df['congestion_level'].median())
    df['capacity_utilization'] = df['capacity_utilization'].fillna(df['capacity_utilization'].median())
    df['incident_reports'] = df['incident_reports'].fillna(0)
    df['signal_compliance'] = df['signal_compliance'].fillna(80.0)
    
    # Compute physical queuing and delay ground truths using Webster's traffic formulation
    # Delay per vehicle (seconds): Free flow speed assumed 50 km/h in urban Bangalore
    free_flow_speed = 50.0
    speed_ratio = np.clip(df['avg_speed'] / free_flow_speed, 0.1, 1.0)
    df['base_delay_sec'] = (df['travel_time_index'] * 30.0) * (1.0 - speed_ratio) + (df['capacity_utilization'] / 100.0) * 45.0
    
    # Queue length (vehicles waiting per cycle):
    # Proportional to volume, capacity utilization, and compliance
    df['base_queue_len'] = (df['vehicle_count'] * (df['capacity_utilization'] / 100.0) / 40.0) * (1.5 - df['signal_compliance'] / 200.0)
    df['base_queue_len'] = np.clip(df['base_queue_len'], 5.0, 350.0)
    
    # Hourly throughput (vehicles / hour):
    df['base_throughput'] = df['vehicle_count'] * np.clip(df['avg_speed'] / 25.0, 0.3, 1.5)
    
    print(f"Loaded {len(df)} records. Base metrics derived successfully.")
    return df

def generate_impact_training_data(df):
    """
    Synthesizes physical control-action pairs (State, G_curr, G_prop) -> (Queue, Delay, Throughput)
    based on Greenshields continuity and Webster delay equation.
    """
    print("Generating control-action impact training data across timing spectrum...")
    records = []
    np.random.seed(42)
    
    # Sample 4000 representative records to build diverse control perturbations
    sample_df = df.sample(min(4500, len(df)), random_state=42)
    
    for _, row in sample_df.iterrows():
        # Current green timing typically 30 - 65s
        g_curr = float(np.random.choice([35, 40, 45, 50, 55, 60]))
        # Proposed timing in safe range 30 - 75s
        g_prop = float(np.random.choice([30, 35, 40, 45, 50, 55, 60, 65, 70, 75]))
        delta_g = g_prop - g_curr
        
        # Greenshields & Webster queuing adjustment:
        # Increasing green time: discharges more queue (-0.65% queue per +1s green up to saturation)
        # However if delta_g is too high on an oversaturated link, gains diminish
        occ_factor = row['capacity_utilization'] / 100.0
        green_ratio = g_prop / g_curr
        
        # Simulated resulting queue:
        # Higher green decreases queue, but diminishing returns if capacity is flooded
        queue_multiplier = 1.0 - (delta_g / g_curr) * (0.55 * (1.0 - 0.3 * occ_factor))
        sim_queue = max(3.0, row['base_queue_len'] * queue_multiplier)
        
        # Simulated resulting delay:
        # Delay decreases with optimal green, increases if queue backs up
        delay_multiplier = 1.0 - (delta_g / g_curr) * (0.45 * (1.0 - 0.25 * occ_factor))
        sim_delay = max(5.0, row['base_delay_sec'] * delay_multiplier)
        
        # Simulated resulting throughput:
        # Throughput increases with green time up to saturation
        tp_multiplier = 1.0 + (delta_g / g_curr) * (0.40 * (1.0 - 0.15 * occ_factor))
        sim_throughput = max(100.0, row['base_throughput'] * tp_multiplier)
        
        # Resulting congestion level (0-100):
        sim_congestion = np.clip(row['congestion_level'] - (delta_g * 0.7), 5.0, 98.0)
        
        records.append({
            'vehicle_count': row['vehicle_count'],
            'avg_speed': row['avg_speed'],
            'travel_time_index': row['travel_time_index'],
            'capacity_utilization': row['capacity_utilization'],
            'incident_reports': row['incident_reports'],
            'signal_compliance': row['signal_compliance'],
            'current_green': g_curr,
            'proposed_green': g_prop,
            'delta_green': delta_g,
            'green_ratio': green_ratio,
            'sim_queue_len': sim_queue,
            'sim_delay_sec': sim_delay,
            'sim_throughput': sim_throughput,
            'sim_congestion': sim_congestion,
        })
        
    impact_df = pd.DataFrame(records)
    print(f"Generated {len(impact_df)} impact simulation training pairs.")
    return impact_df

def train_impact_model(impact_df):
    print("Training Multi-Output Impact Regressor...")
    feature_cols = [
        'vehicle_count', 'avg_speed', 'travel_time_index', 'capacity_utilization',
        'incident_reports', 'signal_compliance', 'current_green', 'proposed_green',
        'delta_green', 'green_ratio'
    ]
    target_cols = ['sim_queue_len', 'sim_delay_sec', 'sim_throughput', 'sim_congestion']
    
    X = impact_df[feature_cols]
    y = impact_df[target_cols]
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Multi-output Random Forest regressor
    base_rf = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42, n_jobs=-1)
    model = MultiOutputRegressor(base_rf)
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    
    metrics = {}
    for i, target in enumerate(target_cols):
        mae = mean_absolute_error(y_test.iloc[:, i], y_pred[:, i])
        rmse = np.sqrt(mean_squared_error(y_test.iloc[:, i], y_pred[:, i]))
        r2 = r2_score(y_test.iloc[:, i], y_pred[:, i])
        metrics[target] = {
            'MAE': float(round(mae, 4)),
            'RMSE': float(round(rmse, 4)),
            'R2': float(round(r2, 4))
        }
        print(f"  Target '{target}': MAE={mae:.2f}, RMSE={rmse:.2f}, R2={r2:.4f}")
        
    model_path = os.path.join(MODELS_DIR, "impact", "impact_regressor.pkl")
    joblib.dump({
        'model': model,
        'feature_cols': feature_cols,
        'target_cols': target_cols,
        'metrics': metrics,
        'trained_at': datetime.now().isoformat()
    }, model_path, compress=3)
    print(f"Saved Impact Regressor to {model_path}")
    return metrics, feature_cols

def train_anomaly_model(df):
    print("Training Traffic Anomaly Detection Model (Isolation Forest)...")
    feature_cols = ['vehicle_count', 'avg_speed', 'travel_time_index', 'capacity_utilization', 'incident_reports']
    X = df[feature_cols].copy()
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 5% contamination baseline for anomalous conditions
    iso = IsolationForest(n_estimators=150, contamination=0.05, random_state=42, n_jobs=-1)
    iso.fit(X_scaled)
    
    # Compute anomaly scores
    scores = iso.decision_function(X_scaled)
    preds = iso.predict(X_scaled)
    anomaly_count = int(np.sum(preds == -1))
    print(f"  Anomaly baseline: {anomaly_count} / {len(X)} records flagged as anomalies ({anomaly_count/len(X)*100:.1f}%)")
    
    model_path = os.path.join(MODELS_DIR, "anomaly", "anomaly_detector.pkl")
    joblib.dump({
        'model': iso,
        'scaler': scaler,
        'feature_cols': feature_cols,
        'contamination': 0.05,
        'score_threshold': float(np.percentile(scores, 5)),
        'trained_at': datetime.now().isoformat()
    }, model_path)
    print(f"Saved Anomaly Detector to {model_path}")
    return {'contamination': 0.05, 'flagged_count': anomaly_count, 'records_total': len(X)}, feature_cols

def train_ripple_model(df):
    print("Training Network Ripple Predictor...")
    # Models how an upstream discharge delta affects downstream congestion
    np.random.seed(42)
    records = []
    
    for _ in range(3000):
        upstream_delta_g = float(np.random.uniform(-15, 25))
        upstream_vol = float(np.random.uniform(8000, 35000))
        link_dist_km = float(np.random.uniform(0.8, 4.5))
        downstream_occ = float(np.random.uniform(20, 95))
        
        # Propagation physics:
        # Additional discharge = (delta_g / 45) * volume_flow
        # If downstream occupancy is high (>75%), extra flow accumulates as congestion
        spillback_susceptibility = np.clip((downstream_occ - 60) / 40.0, 0.0, 1.0)
        distance_attenuation = np.exp(-0.35 * link_dist_km)
        
        downstream_congestion_delta_pct = (upstream_delta_g * 0.85) * (1.0 + 1.2 * spillback_susceptibility) * distance_attenuation
        
        # Add slight stochastic noise
        downstream_congestion_delta_pct += np.random.normal(0, 0.5)
        
        records.append({
            'upstream_delta_g': upstream_delta_g,
            'upstream_volume': upstream_vol,
            'link_distance_km': link_dist_km,
            'downstream_occupancy': downstream_occ,
            'downstream_congestion_delta_pct': downstream_congestion_delta_pct
        })
        
    ripple_df = pd.DataFrame(records)
    feature_cols = ['upstream_delta_g', 'upstream_volume', 'link_distance_km', 'downstream_occupancy']
    X = ripple_df[feature_cols]
    y = ripple_df['downstream_congestion_delta_pct']
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    gbr = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
    gbr.fit(X_train, y_train)
    
    y_pred = gbr.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    print(f"  Ripple Predictor: MAE={mae:.3f}%, RMSE={rmse:.3f}%, R2={r2:.4f}")
    
    model_path = os.path.join(MODELS_DIR, "optimizer", "ripple_predictor.pkl")
    joblib.dump({
        'model': gbr,
        'feature_cols': feature_cols,
        'metrics': {'MAE': float(round(mae, 4)), 'RMSE': float(round(rmse, 4)), 'R2': float(round(r2, 4))},
        'trained_at': datetime.now().isoformat()
    }, model_path)
    print(f"Saved Network Ripple Predictor to {model_path}")
    return {'MAE': float(round(mae, 4)), 'RMSE': float(round(rmse, 4)), 'R2': float(round(r2, 4))}, feature_cols

def main():
    print("=" * 60)
    print("IntelliFlow 2.0 — Specialized AI Model Training Pipeline")
    print("=" * 60)
    
    df = load_and_preprocess_dataset()
    impact_df = generate_impact_training_data(df)
    
    impact_metrics, impact_features = train_impact_model(impact_df)
    anomaly_metrics, anomaly_features = train_anomaly_model(df)
    ripple_metrics, ripple_features = train_ripple_model(df)
    
    metadata = {
        'version': '2.0.0',
        'pipeline': 'IntelliFlow 2.0 Self-Learning Decision Engine',
        'trained_at': datetime.now().isoformat(),
        'dataset': 'Banglore_traffic_Dataset.csv',
        'models': {
            'impact_regressor': {
                'path': 'models/impact/impact_regressor.pkl',
                'features': impact_features,
                'metrics': impact_metrics
            },
            'anomaly_detector': {
                'path': 'models/anomaly/anomaly_detector.pkl',
                'features': anomaly_features,
                'metrics': anomaly_metrics
            },
            'ripple_predictor': {
                'path': 'models/optimizer/ripple_predictor.pkl',
                'features': ripple_features,
                'metrics': ripple_metrics
            }
        }
    }
    
    meta_path = os.path.join(METADATA_DIR, "intelliflow2_metadata.json")
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"\nAll models trained and metadata written to {meta_path}!")
    print("=" * 60)

if __name__ == '__main__':
    main()
