# Decision log

Each analysis decision in this project, with the options considered and the reason for the choice.
Entries marked **Open** are still being decided.

---

## D1. Main goal: rank signals, with prediction as a check

**Status:** Decided, 28 Oct 2026

**Options considered:**
- Rank signals by how strongly they are linked to failure.
- Build a model that predicts which units will fail.

**Choice:** ranking leads. Prediction is used only to check that the top-ranked signals are real and not chance results.

**Why:** a ranked list tells process engineers where to look, which helps them narrow down problems on the line. The other side of the argument was also considered: the signals are recorded before the downstream test, so a predictive model could flag failing units early and avoid spending further processing on them. That value is real, but diagnosing causes is the more useful output for an operations team.

---

## D2. Correcting for many tests: Benjamini–Hochberg

**Status:** Decided, 29 Oct 2026

**Options considered:**
- No correction. With 590 tests at the 5% level, about 30 signals would look significant by chance alone.
- Bonferroni: very strict, so almost no false leads, but weaker real signals get missed.
- Benjamini–Hochberg: controls the *proportion* of false leads in the final list.

**Choice:** Benjamini–Hochberg at **5%**, so on average no more than 5% of the flagged signals are flukes. It applies to the missingness tests (D7). The forest ranking has its own checks (D11).

**Why:** for an engineer, never hearing about a real signal is worse than occasionally chasing a false lead.

---

## D3. Train on earlier runs, test on later runs

**Status:** Decided, 29 Oct 2026

**Options considered:**
- A random 60:20:20 split into training, validation and test sets.
- A time-ordered split, using cross-validation with scikit-learn's `TimeSeriesSplit`.

**Choice:** `TimeSeriesSplit` cross-validation, with no separate validation set.

**Why:** in production a model is trained on past runs and used on future ones, so testing on later runs is the honest test. Random shuffling lets the model learn from the future, which overstates its performance, especially if the process drifted over the three months. With only 104 failures, a three-way split would leave about 21 failures per set, which is too few to measure anything reliably.

---

## D4. Number of top signals fixed at 40

**Status:** Decided, 29 Oct 2026

**Options considered:**
- Fix the number before the analysis starts.
- Tune the number inside cross-validation.

**Choice:** fixed at 40.

**Why:** 40 matches the baseline results published with the dataset, so the results can be compared with them. Fixing the number up front also avoids choosing it by looking at test performance.

---

## D5. Cleaning is learned from training data inside each fold

**Status:** Decided, 29 Oct 2026

**Options considered:**
- **A.** Clean the whole dataset once and write a single cleaned CSV, accepting and documenting a small leak.
- **B.** Learn every cleaning step from the training runs only, then apply it to the test runs, separately in each fold.

**Choice:** B.

**Why:** to prevent data leakage. No information from the test runs is used when building any part of the pipeline.

---

## D6. Filling gaps with the median from training runs

**Status:** Decided, 29 Oct 2026

**Options considered:**
- Fill gaps with the mean.
- Fill gaps with the median.

**Choice:** signals with 50% or less missing have their gaps filled with that signal's median. The median is calculated from the training runs only (see D5).

**Why:** the median is robust to outliers and skew. One wildly wrong reading can drag the mean away from typical values, but it barely moves the median, so the median stays a realistic value for the signal.

---

## D7. Signals with more than 50% missing

**Status:** Decided, 29 Oct 2026

**Choice:** their gaps are not filled and their values are not analysed. Instead, whether a value is present or missing is tested for a link to failure (Fisher's exact test, corrected with Benjamini–Hochberg). Any significant results are noted.

**Why:** whether a reading exists can carry information in its own right. Dropping these signals outright could throw that information away.

**Update, 29 Oct 2026:** the missingness test now applies to **every signal with gaps**, not just those over 50% missing. Filling a gap with the median erases the fact that the value was missing, so this information has to be captured before imputation.

**Minimum gaps, decided 29 Oct 2026:** only signals with **more than 50 missing runs** are tested. At the overall fail rate of 6.6%, 50 runs should contain about 3 failures by chance. That is enough to see a real difference, and it avoids hundreds of tests that could never reach significance, each of which makes the correction stricter. On the full dataset, 60 signals pass this bar. Signals below it have their gaps filled and their missingness information is not used, which is an accepted trade-off.

Because the test uses pass/fail labels, it runs on training data only, inside each fold (D5).

**Separate test or flag columns, decided 29 Oct 2026:**
- **Options considered:**
  - Keep this as a separate test, using Fisher's exact test with Benjamini–Hochberg.
  - Add "was missing" flag columns and let the random forest rank missingness alongside the signal values.
- **Choice:** keep the separate test.
- **Why:** it is simpler to explain to an engineer: "when this signal is missing, the fail rate is X% instead of 6.6%."
- **Trade-off accepted:** combinations of missingness with other signals are not examined.

---

## D8. Missing values over time: plot before deciding

**Status:** Decided, 29 Oct 2026

**Options considered:**
- Set a rule in advance, such as ignoring failures that occur during sensor outages.
- Plot missingness and failures against time first, then decide.

**Choice:** plot first. No failures are removed.

**Why:** a failure during an outage still happened, so deleting it would bias the data. If a sensor was offline during a stretch with many failures, that signal gets a closer look. It could be coincidence, or losing the reading could have reduced control of the process and made it vary more.

---

## D9. Near-constant signals

**Status:** Open

**Facts:**
- 116 signals are exactly constant.
- 122 have one value covering more than 99% of runs.
- 126 have one value covering more than 95% of runs.

**Proposed:** drop signals where one value covers more than 99% of runs.

**Manual check of the 10 near-constant signals** (looking only at their values and timestamps, not at pass/fail):
- **s74, s206, s209, s342, s347, s478** are zero on every run except one, the same run (11 Oct 07:39). A single run can't support any statistical test.
- **s114, s249, s387, s521** are zero on about 98.6% of runs. They are non-zero on about 22 runs spread from July to October: 2 in July, 9 in August, 6 in September and 5 in October. s114, s249 and s387 are non-zero on exactly the same runs. They look like an intermittent event rather than noise.

The 99% cut-off drops the first group and keeps the second.

**Choice (decided 29 Oct 2026):** drop signals where one value covers more than 99% of runs. The cut-off is applied to the training data inside each fold.

**Why group 1 is dropped:** six signals that are non-zero in only one run can't be tested. Even in the most extreme case, where that run failed, a random run fails 6.6% of the time, so the result isn't significant. A model would just memorise that one example. The run itself is reported as a finding (F1).

**Pass/fail labels:** they were not used to make this decision. The rule was fixed first, and labels may be looked at afterwards for reporting only.

---

## D10. Twin signals (|r| > 0.95)

**Status:** Partly open

**Options considered:**
- Keep all twins.
- Drop one of each pair, then swap twins in and out to compare scores.
- Drop one of each pair, log the pair, and report the twins together.

**Choice:** drop one of each pair before modelling, log the pair, and report both together. For example: "A ranks highly; B moves almost identically."

**Why:** inside a single model, twins split their importance, so a real signal can fall out of the top 40. Swapping twins would only pick up chance differences, because the data can't tell twins apart. Telling them apart needs process knowledge.

**Which twin is kept, decided 29 Oct 2026:**
- **Options considered:**
  - The one with fewer missing values.
  - The lower column number.
  - The one more linked to failure.
- **Choice:** the one with fewer missing values. On a tie, the lower column number is kept.
- **Why:** it is the more complete measurement, so fewer of its values are filled-in medians. The choice doesn't use pass/fail.

**When twins are found, decided 29 Oct 2026:**
- **Options considered:**
  - Before gaps are filled, using only runs where both signals were recorded.
  - After gaps are filled.
- **Choice:** before.
- **Why:** filling gaps puts one repeated value into every gap, which distorts correlation. Usually it weakens it, but not always. On the full data, every pair of remaining signals shares at least 621 runs with real readings.

**Why a single model:** a single model can show the effect of *combinations* of signals that are linked to failure. Testing signals one at a time can't.

**Model choice, 29 Oct 2026:** a random forest, which ranks the signals itself and supplies the top 40. A plain logistic regression was considered and rejected: it adds the signals' effects together and misses combinations unless they are built in.

**Why a random forest:** it can show the effect of combinations of signals, and it is fairly robust to outliers.

---

## D11. Checking the ranking against chance results

**Status:** Partly open

**Background:** random-forest importance scores have no p-values, so D2's correction covers the missingness tests (D7) but not the ranking. The ranking needs its own check.

**Options considered:**
- (a) Count a signal as real if it stays in the top 40 across folds. Rejected: with `TimeSeriesSplit` the training sets overlap, since July is in every one. A chance result in early data would therefore look consistent in every fold.
- (b) A forest built on the top 40 must predict failures in each test block better than guessing. The test blocks don't overlap, so each one is genuinely new data.
- (c) A label shuffle: rerun with pass/fail randomly shuffled to see what importance scores pure noise produces.

**Choice:** (b) and (c) together.

**Why:**
- (b) shows that the top 40 *as a group* carry real information about failure, using data the model has never seen. Some of the 40 may still be false positives. That is acceptable, because engineers can start targeting fixes as long as the real signals are on the list.
- (c) measures how much importance pure noise can produce, which sets a ceiling for noise. A signal that scores clearly above it is linked to failure beyond what noise explains. This is a check on each signal individually.

**Open:** what "better than guessing" means, given that the failures are rare.

---

## D12. The final list given to engineers

**Status:** Decided, 29 Oct 2026 (exact method for combining folds still to be set)

**Options considered:**
- (a) Rerun the whole pipeline on all the data and report that top 40.
- (b) Combine the per-fold results.

**Choice:** (b). Signals that rank highly across folds *and* score above the noise ceiling (D11) go on the list.

**Why:** a signal that keeps ranking highly and stays above what noise can produce is strongly linked to failure in a way noise alone can't explain. Consistency across folds is used here to *order* the list, not as proof that a signal is real. Because the training sets overlap, it can't serve as proof on its own (see D11).

---

## Findings to report

- **F1.** On 11 Oct 2008 at 07:39, six signals that are zero on every other run (s74, s206, s209, s342, s347 and s478) all fired in the same run. This looks like a one-off event, such as maintenance, a recalibration, an alarm or a logging glitch. It's worth checking against maintenance logs.

---

## Open, not yet discussed

- Whether `requirements.txt` should pin exact package versions, so results are reproducible later.
