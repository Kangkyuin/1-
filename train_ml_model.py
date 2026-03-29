#!/usr/bin/env python3
"""학습용 CSV를 읽어 분류 모델을 학습/저장합니다."""

from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix


DEFAULT_FEATURES = [
    "ret_1",
    "ret_3",
    "ret_6",
    "ma_gap_pct",
    "ema_gap_pct",
    "rsi_14",
    "atr_pct",
    "vol_z_20",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="선물 시그널 분류 모델 학습")
    parser.add_argument(
        "--data",
        default="data/btcusdt_5m_training.csv",
        help="학습 데이터 CSV 경로",
    )
    parser.add_argument(
        "--model-out",
        default="models/btc_signal_model.pkl",
        help="모델 저장 경로",
    )
    parser.add_argument(
        "--test-ratio",
        type=float,
        default=0.2,
        help="검증 데이터 비율 (시간순 마지막 구간)",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="난수 시드",
    )
    parser.add_argument(
        "--features",
        default=",".join(DEFAULT_FEATURES),
        help="사용할 피처 컬럼 목록 (comma-separated)",
    )
    return parser.parse_args()


def train_time_split(
    df: pd.DataFrame,
    feature_cols: list[str],
    test_ratio: float,
    random_state: int,
) -> tuple[RandomForestClassifier, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    split_idx = int(len(df) * (1 - test_ratio))
    if split_idx <= 10 or split_idx >= len(df):
        raise ValueError("test_ratio 값이 비정상입니다. (0.05~0.5 권장)")

    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()

    x_train = train_df[feature_cols]
    y_train = train_df["signal"].astype(int)
    x_test = test_df[feature_cols]
    y_test = test_df["signal"].astype(int)

    model = RandomForestClassifier(
        n_estimators=400,
        max_depth=10,
        min_samples_leaf=5,
        class_weight="balanced_subsample",
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)
    return model, x_train, y_train, x_test, y_test


def main() -> None:
    args = parse_args()
    data_path = Path(args.data)
    model_path = Path(args.model_out)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise FileNotFoundError(f"데이터 파일이 없습니다: {data_path}")

    df = pd.read_csv(data_path)
    feature_cols = [c.strip() for c in args.features.split(",") if c.strip()]
    required = feature_cols + ["signal"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"CSV에 필요한 컬럼이 없습니다: {missing}")

    df = df.dropna(subset=required).reset_index(drop=True)
    if len(df) < 300:
        raise ValueError("학습 샘플이 너무 적습니다. collect_ml_data.py로 데이터를 더 수집하세요.")

    model, _, _, x_test, y_test = train_time_split(
        df=df,
        feature_cols=feature_cols,
        test_ratio=args.test_ratio,
        random_state=args.random_state,
    )

    pred = model.predict(x_test)
    report = classification_report(y_test, pred, digits=4)
    matrix = confusion_matrix(y_test, pred, labels=[-1, 0, 1])

    payload = {
        "model": model,
        "features": feature_cols,
        "labels": [-1, 0, 1],
        "meta": {
            "rows": int(len(df)),
            "test_ratio": args.test_ratio,
            "random_state": args.random_state,
        },
    }
    joblib.dump(payload, model_path)

    print(f"[완료] 모델 저장: {model_path}")
    print(f"[정보] 전체 데이터 수: {len(df)}")
    print("[평가] classification_report")
    print(report)
    print("[평가] confusion_matrix labels=[-1, 0, 1]")
    print(matrix)


if __name__ == "__main__":
    main()
