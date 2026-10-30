"""Run the full analysis: rank the signals in each time fold, check the ranking
against shuffled labels, and combine the folds into a list for engineers.

The steps, and the reasoning behind each one, are in DECISIONS.md:

    for each of 5 time folds (D3), using only the fold's training runs:
        clean the signals (D5-D10)
        build a balanced forest (D13) and score every signal's importance (D11)
        build a forest on the top 40 (D4) and work out its BER on the test runs
    repeat the forest steps 10 times with the pass/fail labels shuffled (D11)
    combine the folds into the list for engineers (D12)

Run with: python src/model.py   (about 20 minutes)
Results are written to results/.
"""

import time

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import TimeSeriesSplit

from clean import apply_cleaning, learn_cleaning
from forest import N_TREES, BalancedForest
from load import REPO_ROOT, load_data

N_FOLDS = 5      # D3
TOP_K = 40       # D4
N_SHUFFLES = 10  # D11: label shuffles that set the noise ceiling
N_REPEATS = 5    # D13: times each signal is scrambled when scoring it
RESULTS_DIR = REPO_ROOT / "results"


def ber(fail, predicted):
    """Balanced error rate: the average of the share of fails missed and the share
    of passes wrongly flagged. 0.5 = guessing, 0 = perfect (D11)."""
    return 1 - balanced_accuracy_score(fail, predicted)


def signal_number(signal):
    """Sort key so that s2 comes before s10."""
    return int(signal[1:])


def run_fold(X_train, fail_train, X_test, fail_test, seed, n_trees):
    """Forest, importance, top 40 and BER for one fold.

    Returns the importance of each signal kept in this fold, and the BER of the
    top-40 forest on the test runs.
    """
    forest = BalancedForest(n_trees=n_trees, random_state=seed).fit(X_train, fail_train)

    # Scramble each signal N_REPEATS times on the training runs (D11, option b)
    # and average the fall in balanced accuracy. Balanced accuracy is 1 - BER,
    # so its fall is the same number as the rise in BER.
    scores = permutation_importance(forest, X_train, fail_train, scoring="balanced_accuracy",
                                    n_repeats=N_REPEATS, random_state=seed, n_jobs=-1)
    importance = pd.Series(scores.importances_mean, index=X_train.columns)

    top = importance.nlargest(TOP_K).index
    top_forest = BalancedForest(n_trees=n_trees, random_state=seed).fit(X_train[top], fail_train)
    return importance, ber(fail_test, top_forest.predict(X_test[top]))


def fill_dropped(values, log, other_value):
    """Give the signals this fold's cleaning dropped a value, following D12.

    values covers the signals kept in this fold. A signal dropped as a twin takes
    its kept twin's value; a signal dropped for any other reason gets other_value.
    """
    filled = values.reindex(log.index)
    twins = log["reason"] == "twin"
    filled[twins] = values[log.loc[twins, "twin_of"]].to_numpy()
    return filled.fillna(other_value)


def twin_pairs(folds):
    """{signal: its twins} for every twin pair found in any fold's cleaning."""
    twins = {}
    for fold in folds:
        log = fold["log"]
        for dropped, kept in log.loc[log["reason"] == "twin", "twin_of"].items():
            twins.setdefault(dropped, set()).add(kept)
            twins.setdefault(kept, set()).add(dropped)
    return twins


def main(n_shuffles=N_SHUFFLES, n_trees=N_TREES, out_dir=RESULTS_DIR):
    start = time.time()
    df = load_data()
    rng = np.random.default_rng(0)

    # Cleaning doesn't use the labels (D5), so each fold is cleaned once and the
    # same cleaned runs are used by the real run and every shuffle.
    folds = []
    for train_idx, test_idx in TimeSeriesSplit(n_splits=N_FOLDS).split(df):
        train, test = df.iloc[train_idx], df.iloc[test_idx]
        rules = learn_cleaning(train)
        folds.append({
            "X_train": apply_cleaning(train, rules)[rules["keep"]],
            "X_test": apply_cleaning(test, rules)[rules["keep"]],
            "fail_train": train["fail"].to_numpy(),
            "fail_test": test["fail"].to_numpy(),
            "log": rules["log"],
        })
    fold_numbers = range(1, N_FOLDS + 1)

    # Run 0 uses the real labels. Runs 1 to n_shuffles shuffle the training labels
    # within each fold, which keeps each fold's number of fails the same as in the
    # real run. The test labels are never shuffled.
    importance = {}  # (run, fold) -> importance of every signal, filled as in D12
    positions = {}   # fold -> ranking position of every signal, real run only
    bers = {}        # (run, fold) -> BER of the top-40 forest on the test runs
    for run in range(n_shuffles + 1):
        for f, fold in zip(fold_numbers, folds):
            fail_train = fold["fail_train"] if run == 0 else rng.permutation(fold["fail_train"])
            imp, bers[run, f] = run_fold(fold["X_train"], fail_train, fold["X_test"],
                                         fold["fail_test"], seed=100 * run + f, n_trees=n_trees)
            # Dropped signals: the twin's importance, or zero if near-constant (D12).
            importance[run, f] = fill_dropped(imp, fold["log"], 0.0)
            if run == 0:
                # Position 1 = most important. Tied signals share the average position.
                # Dropped signals: the twin's position, or last place (D12).
                positions[f] = fill_dropped(imp.rank(ascending=False), fold["log"], len(imp) + 1)
        label = "real labels" if run == 0 else f"shuffle {run} of {n_shuffles}"
        # flush=True shows each line straight away, even when output goes to a file.
        print(f"{label}: done ({(time.time() - start) / 60:.1f} min)", flush=True)

    # Only signals kept in at least one fold can go on the list.
    kept_any = set().union(*[fold["log"].index[fold["log"]["action"] == "kept"] for fold in folds])
    candidates = sorted(kept_any, key=signal_number)

    # Each signal's importance averaged over the folds: one column per run (D12).
    averages = pd.DataFrame({
        run: pd.concat([importance[run, f] for f in fold_numbers], axis=1).mean(axis=1)
        for run in range(n_shuffles + 1)
    }).loc[candidates]
    ranks = pd.DataFrame({f"position_fold_{f}": positions[f] for f in fold_numbers}).loc[candidates]
    twins = twin_pairs(folds)

    summary = pd.DataFrame({
        "rank_sum": ranks.sum(axis=1),
        "importance": averages[0],
        # The highest of the 10 noise averages: the signal must beat all of them.
        "noise_ceiling": averages.drop(columns=0).max(axis=1),
    })
    summary["beats_noise"] = summary["importance"] > summary["noise_ceiling"]
    summary["twins"] = [", ".join(sorted(twins.get(s, ()), key=signal_number)) for s in candidates]
    summary = summary.join(ranks).sort_values("rank_sum")
    summary.index.name = "signal"
    engineer_list = summary[summary["beats_noise"]].head(TOP_K)

    # Prediction check: BER per fold and averaged, for the real run and each shuffle (D11).
    ber_table = pd.DataFrame(
        {f"fold_{f}": [bers[run, f] for run in range(n_shuffles + 1)] for f in fold_numbers},
        index=["real"] + [f"shuffle_{run}" for run in range(1, n_shuffles + 1)],
    )
    ber_table["average"] = ber_table.mean(axis=1)
    real_ber = ber_table.loc["real", "average"]
    best_shuffled_ber = ber_table.drop(index="real")["average"].min()

    cleaning_log = pd.concat([fold["log"].assign(fold=f) for f, fold in zip(fold_numbers, folds)])

    out_dir.mkdir(exist_ok=True)
    ber_table.to_csv(out_dir / "ber_by_fold.csv", float_format="%.4f")
    summary.to_csv(out_dir / "signal_summary.csv", float_format="%.5f")
    engineer_list.to_csv(out_dir / "engineer_list.csv", float_format="%.5f")
    cleaning_log.to_csv(out_dir / "cleaning_log.csv", float_format="%.4f")

    print(f"\nPrediction check: average BER {real_ber:.3f}, best shuffled average {best_shuffled_ber:.3f}")
    print(f"Better than every shuffle: {'yes' if real_ber < best_shuffled_ber else 'no'}")
    print(f"Signals beating their noise ceiling: {summary['beats_noise'].sum()} of {len(summary)}")
    print(f"Engineer list: {len(engineer_list)} signals, written to {out_dir / 'engineer_list.csv'}")
    print(f"Total time: {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
