"""A balanced random forest: every tree learns from equal numbers of passes and fails.

Without balancing, the trees see about 14 passes for every fail, learn to say
"pass" every time, and every signal's importance comes out near zero
(see DECISIONS.md, D13).

This follows the published balanced random forest (Chen, Liaw and Breiman, 2004).
For each tree:
    1. draw as many fails as there are, at random with replacement,
    2. draw the same number of passes, at random with replacement,
    3. grow a full tree on those runs, trying sqrt(n signals) at each split.
A run is called a fail when more than half the trees say fail.

Run directly (python src/forest.py) to check that every tree really does see
equal numbers of passes and fails.
"""

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.tree import DecisionTreeClassifier

N_TREES = 500  # D13: more trees give steadier results; the only cost is time


def balanced_rows(fail, rng):
    """Pick the training rows for one tree: n fails and n passes, with replacement.

    fail is a boolean array (True = fail); n is the number of fails in it.
    """
    fails = np.flatnonzero(fail)
    passes = np.flatnonzero(~fail)
    n = len(fails)
    return np.concatenate([
        rng.choice(fails, size=n, replace=True),
        rng.choice(passes, size=n, replace=True),
    ])


class BalancedForest(ClassifierMixin, BaseEstimator):
    """A forest of trees, each grown on its own balanced sample of runs.

    It behaves like a scikit-learn model (fit, predict, predict_proba), so
    scikit-learn's tools, such as permutation_importance, work with it.
    """

    def __init__(self, n_trees=N_TREES, random_state=None):
        self.n_trees = n_trees
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(X)
        fail = np.asarray(y, dtype=bool)
        rng = np.random.default_rng(self.random_state)

        self.trees_ = []
        for _ in range(self.n_trees):
            rows = balanced_rows(fail, rng)
            # Each tree gets its own seed, so it tries a different random set of
            # signals at each split. The whole forest stays reproducible.
            tree = DecisionTreeClassifier(max_features="sqrt", random_state=int(rng.integers(2**31)))
            tree.fit(X[rows], fail[rows])
            self.trees_.append(tree)

        # scikit-learn expects the model to list its classes: False = pass, True = fail.
        self.classes_ = np.array([False, True])
        return self

    def predict_proba(self, X):
        """For each run, the share of trees voting pass and voting fail."""
        X = np.asarray(X)
        # Every tree saw both classes, so column 1 of each tree's output is "fail".
        fail_share = np.mean([tree.predict_proba(X)[:, 1] for tree in self.trees_], axis=0)
        return np.column_stack([1 - fail_share, fail_share])

    def predict(self, X):
        """True (fail) where more than half the trees vote fail. A tied vote counts as a pass."""
        return self.predict_proba(X)[:, 1] > 0.5


if __name__ == "__main__":
    # Check the sampling on a made-up label column with SECOM's mix:
    # 1463 passes and 104 fails.
    fail = np.array([False] * 1463 + [True] * 104)
    rng = np.random.default_rng(0)

    unique_fails_seen = []
    for _ in range(1000):
        rows = balanced_rows(fail, rng)
        n_fail = fail[rows].sum()
        n_pass = (~fail[rows]).sum()
        assert n_fail == n_pass == 104, f"unbalanced sample: {n_fail} fails, {n_pass} passes"
        unique_fails_seen.append(len(np.unique(rows[fail[rows]])))

    print("1000 samples drawn: every one has 104 fails and 104 passes.")
    print(f"Distinct fails per tree: about {np.mean(unique_fails_seen):.0f} of 104 "
          f"({np.mean(unique_fails_seen) / 104:.0%}); the rest are repeats.")
