"""Learn cleaning rules from training runs, then apply them to any runs.

Cleaning is split into two steps so that it can run inside each
cross-validation fold without leaking test data (see DECISIONS.md, D5):

    rules = learn_cleaning(train)              # looks at training runs only
    train_clean = apply_cleaning(train, rules)
    test_clean = apply_cleaning(test, rules)

Nothing here uses the pass/fail labels. Tests that do use them, such as the
missingness test (D7), belong in the analysis scripts.

Run directly (python src/clean.py) to see what the rules do on the full dataset.
"""

import pandas as pd

from load import load_data

# Thresholds. The reasoning behind each one is in DECISIONS.md.
MAX_MISSING = 0.5     # D7: drop signals missing on more than half the runs
MAX_TOP_SHARE = 0.99  # D9: drop signals where one value covers more than 99% of runs
TWIN_CORR = 0.95      # D10: two signals with |r| above this are twins

# Every other column is a sensor signal.
NON_SENSOR_COLS = ["timestamp", "fail"]


def sensor_columns(df):
    """Names of the sensor columns in df."""
    return [col for col in df.columns if col not in NON_SENSOR_COLS]


def top_value_share(values):
    """Fraction of a signal's recorded values taken up by its most common value.

    1.0 means the signal never changes. Missing values are ignored.
    """
    recorded = values.dropna()
    if recorded.empty:
        return 1.0
    return recorded.value_counts(normalize=True).iloc[0]


def find_twins(sensors):
    """Return {dropped signal: the kept signal it is a twin of}.

    Signals are visited from fewest missing values to most, so that in each
    pair the more complete one is kept; ties are broken by column order (D10).
    Correlations are worked out before any gaps are filled, using only the runs
    where both signals were recorded.
    """
    corr = sensors.corr().abs()
    # A stable sort keeps the original column order for signals with equal counts.
    order = sensors.isna().sum().sort_values(kind="stable").index

    kept = []
    twins = {}
    for signal in order:
        if kept:
            # The already-kept signal this one moves most closely with.
            # fillna(0): a pair with no usable correlation is treated as unrelated.
            closeness = corr.loc[signal, kept].fillna(0)
            closest = closeness.idxmax()
            if closeness[closest] > TWIN_CORR:
                twins[signal] = closest
                continue
        kept.append(signal)
    return twins


def learn_cleaning(train):
    """Learn which signals to keep, and each one's median, from training runs only.

    Returns a dict with:
        keep:    the signals that survive cleaning
        medians: each kept signal's median, used to fill its gaps (D6)
        log:     one row per signal, saying whether it was kept and if not, why
    """
    sensors = train[sensor_columns(train)]

    log = pd.DataFrame({
        "missing_frac": sensors.isna().mean(),
        "top_value_share": sensors.apply(top_value_share),
    })
    log.index.name = "signal"
    log["action"] = "kept"
    log["reason"] = ""
    log["twin_of"] = ""

    # D7: too many gaps to fill sensibly. (Whether these signals are missing is
    # still tested against failure, but that happens in the analysis, not here.)
    too_sparse = log["missing_frac"] > MAX_MISSING
    log.loc[too_sparse, ["action", "reason"]] = ["dropped", "over 50% missing"]

    # D9: (almost) never changes, so it can't tell passes from fails.
    near_constant = ~too_sparse & (log["top_value_share"] > MAX_TOP_SHARE)
    log.loc[near_constant, ["action", "reason"]] = ["dropped", "near-constant"]

    # D10: of each pair of twins, keep the more complete one.
    remaining = log.index[log["action"] == "kept"]
    for signal, partner in find_twins(sensors[remaining]).items():
        log.loc[signal, ["action", "reason", "twin_of"]] = ["dropped", "twin", partner]

    keep = list(log.index[log["action"] == "kept"])
    medians = sensors[keep].median()
    return {"keep": keep, "medians": medians, "log": log}


def apply_cleaning(df, rules):
    """Keep only the signals in rules, and fill their gaps with the learned medians.

    df can be training or test runs: the rules never change once learned.
    """
    other = [col for col in NON_SENSOR_COLS if col in df.columns]
    # fillna with a Series fills each column with its own median.
    cleaned = df[rules["keep"]].fillna(rules["medians"])
    return pd.concat([df[other], cleaned], axis=1)


if __name__ == "__main__":
    # For inspection only. Here the rules are learned from all the runs; the
    # real analysis learns them separately inside each fold (D5).
    df = load_data()
    rules = learn_cleaning(df)
    cleaned = apply_cleaning(df, rules)
    log = rules["log"]

    print(f"Signals before cleaning: {len(log)}")
    print(log["reason"].replace("", "kept").value_counts().to_string())
    print(f"Signals after cleaning: {len(rules['keep'])}")
    print(f"Gaps left after filling: {cleaned[rules['keep']].isna().sum().sum()}")

    print("\nFirst few twins (dropped -> kept):")
    print(log.loc[log["reason"] == "twin", "twin_of"].head(8).to_string())
