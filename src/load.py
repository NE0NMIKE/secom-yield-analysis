"""Load the raw SECOM files into a single tidy DataFrame.

Run directly (python src/load.py) to print a summary of the raw data.
Other scripts import load_data() from here.
"""

from pathlib import Path

import pandas as pd

# Paths are built relative to this file, so the script works from any folder.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


def load_features(path=DATA_DIR / "secom.data"):
    """Read the sensor columns, named s0 to s589.

    The UCI notes say 591 features, but every row of the file has 590 values.
    """
    # The file is space-separated with no header row; "NaN" is read as missing.
    features = pd.read_csv(path, sep=r"\s+", header=None)
    features.columns = [f"s{i}" for i in range(features.shape[1])]
    return features


def load_labels(path=DATA_DIR / "secom_labels.data"):
    """Read pass/fail labels and timestamps."""
    # The timestamp is quoted because it contains a space; read_csv handles
    # the quotes, so each line still splits into exactly two columns.
    labels = pd.read_csv(path, sep=" ", header=None, names=["label", "timestamp"])
    labels["timestamp"] = pd.to_datetime(labels["timestamp"], format="%d/%m/%Y %H:%M:%S")
    # In the raw file -1 means pass and 1 means fail.
    labels["fail"] = labels["label"] == 1
    return labels[["timestamp", "fail"]]


def load_data():
    """Return one DataFrame: timestamp, fail, then the sensor columns.

    Row i of the labels file describes row i of the features file,
    so the two are joined side by side.
    """
    features = load_features()
    labels = load_labels()
    if len(features) != len(labels):
        raise ValueError(f"Row mismatch: {len(features)} feature rows, {len(labels)} label rows")
    return pd.concat([labels, features], axis=1)


def summarise(df):
    """Print the dataset's key numbers."""
    sensors = df.drop(columns=["timestamp", "fail"])
    n_runs = len(df)
    n_fail = int(df["fail"].sum())

    print(f"Shape: {n_runs} runs x {sensors.shape[1]} sensors")
    print(f"Pass: {n_runs - n_fail}  Fail: {n_fail}  Fail rate: {n_fail / n_runs:.1%}")
    print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

    # Fraction of runs missing a value, for each sensor.
    missing = sensors.isna().mean()
    print("\nSensors by fraction of missing values:")
    print(f"  0%:      {(missing == 0).sum()}")
    print(f"  <5%:     {((missing > 0) & (missing < 0.05)).sum()}")
    print(f"  5-50%:   {((missing >= 0.05) & (missing <= 0.5)).sum()}")
    print(f"  >50%:    {(missing > 0.5).sum()}")


if __name__ == "__main__":
    summarise(load_data())
