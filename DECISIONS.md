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

**Number of folds, decided 30 Oct 2026:**
- **Options considered:** 3, 5, 8 and 10 folds. The fail counts in each test block were checked before choosing:
  - 3 folds: 13 to 24 fails per block.
  - 5 folds: 6 to 22.
  - 8 folds: 4 to 26.
  - 10 folds: 2 to 23.
- **Choice:** 5 folds.
- **Why:** with 10 folds, one test block has only 2 fails, which is too few to tell a skilled model from a lucky one. With 3 folds there are only 3 checks. With 5, every test block has at least 6 fails.
- **Found while checking:** failures are not spread evenly over time. The first 262 runs (July to mid-August) have a 15% fail rate. From late August onwards it is about 2–5%.

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

**Status:** Decided, 30 Oct 2026

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

**Closed, 30 Oct 2026:** no result from plotting group 1 could change the decision to drop it. Whether that run passed or failed, it is one event. It is reported as F1 and not analysed further.

---

## D10. Twin signals (|r| > 0.95)

**Status:** Decided, 30 Oct 2026

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

**Measuring prediction, decided 30 Oct 2026:**
- **Options considered:**
  - Accuracy.
  - The balanced error rate (BER), which averages the share of fails missed and the share of passes wrongly flagged.
- **Choice:** BER. Guessing scores 0.5. Lower is better.
- **Why:**
  - Accuracy rewards a model that always says "pass". That model is 91.6% accurate in fold 1 and 97.7% in fold 2, so the accuracy baseline changes from block to block as the fail rate changes. BER gives that model 0.5 in every block, so folds can be compared meaningfully.
  - BER is also the measure used in the published baseline, so the results are comparable with it.
  - BER makes each missed fail cost about 14 times as much as each false alarm, because fails are about 14 times rarer. This ratio comes from the class sizes, not from a known cost. The real costs aren't known, so baseline comparability is the main defence.

**Number of label shuffles, provisionally 30 Oct 2026:** 10 to start with. To be confirmed before looking at which signals clear the ceiling.

**Importance score, decided 30 Oct 2026:** permutation importance is measured as the rise in BER when a signal is scrambled. This is more reliable than accuracy for the same reasons as above, and it is consistent with how the model is judged.

**Which runs importance is measured on, decided 30 Oct 2026:**
- **Options considered:**
  - (a) The test block. Rejected: the top 40 would be picked using the same runs that later grade the top-40 forest, so test data would leak into the check.
  - (b) The training runs.
  - (c) A "mock exam" held back from the end of each training period. Rejected: fold 3's mock exam would contain only 2 fails.
  - (d) The forest's built-in (impurity) importance. It's calculated on training runs like (b), and it favours signals with many distinct values.
- **Choice:** (b).
- **Why:** the scores are inflated, because the forest partly memorised these runs. But the label-shuffle forests memorise too, so a signal that beats its own noise scores is still linked to failure beyond what memorising plus luck can explain. The top-40 forest is graded on unseen test runs, which memorising can't help with, so a top 40 made of memorisation signals would show up as a BER near 0.5.
- **Limits accepted:**
  - The inflation in real and shuffled forests is probably similar but not identical. A forest with shuffled labels has nothing real to learn, so it relies on memorising entirely.
  - The prediction check tests the 40 as a group, so a few memorisation signals among them can still get through.

**Better than guessing, decided 30 Oct 2026:**
- **Options considered:**
  - BER below a fixed value.
  - BER lower than most of the shuffled-label models.
  - BER lower than every shuffled-label model.
- **Choice:** lower than every shuffled-label model.
- **Why:** shuffled-label models have no real information by design, so their BER values show how good a model can look by luck alone.
- **Applied to, decided 30 Oct 2026:** the BER averaged across the five folds, not each fold separately.
  - **Why:** requiring it in every fold is stricter, so a real but modest model could fail the check because of noise in one small fold (fold 2 has only 6 fails). Averaging fits D2's priority of not missing real signals.
  - **Trade-off accepted:** one strong fold can hide weak ones. Per-fold BERs are reported as well, so this stays visible.

**Noise ceiling, decided 30 Oct 2026:**
- **Options considered:**
  - (i) A ceiling for each signal, with 10 shuffles.
  - (ii) A ceiling for each signal, with about 100 shuffles (about 2 hours).
  - (iii) One shared ceiling for all signals.
- **Choice:** (i).
- **Why:** each signal has its own noise level, because trees use some signals more often than others, and those signals pick up more chance importance.
- **Trade-off accepted:** a pure-noise signal beats all 10 of its own shuffled scores about 1 time in 11, so about 25 of the 271 signals can clear the ceiling by luck. The requirement to rank highly across folds (D12) is relied on to filter most of these out.

---

## D12. The final list given to engineers

**Status:** Decided, 29 Oct 2026 (exact method for combining folds still to be set)

**Options considered:**
- (a) Rerun the whole pipeline on all the data and report that top 40.
- (b) Combine the per-fold results.

**Choice:** (b). Signals that rank highly across folds *and* score above the noise ceiling (D11) go on the list.

**Why:** a signal that keeps ranking highly and stays above what noise can produce is strongly linked to failure in a way noise alone can't explain. Consistency across folds is used here to *order* the list, not as proof that a signal is real. Because the training sets overlap, it can't serve as proof on its own (see D11).

---

## D13. Handling the class imbalance (about 14 passes per fail)

**Status:** Partly open

**The problem:** a forest trained without any adjustment is rewarded mostly for getting passes right, so it predicts "pass" almost every time. Its predictions then barely change when any one signal is scrambled, so every signal's importance comes out near zero and the ranking is noise.

**Options considered:**
- A. Class weighting (`class_weight="balanced"`).
- B. Undersample the passes.
- C. Oversample the fails.

**Choice, 30 Oct 2026:** A.

**Why:** each fail counts about 14 times as much as each pass. That matches how BER scores the model (D11), so the forest is trained on the same terms it is judged by. No data is thrown away (B) and none is copied (C).

**Found on 30 Oct 2026, while timing one fold:** with class weighting alone, the forest predicted 0 of the 14 fails in fold 5's test block. Weighting by itself is not enough. Still open.

**Follow-up options considered, 30 Oct 2026:**
- A1. Stop trees growing earlier (`min_samples_leaf`).
- A2. Lower the probability cut-off for calling a run a fail.
- A3. Balanced trees: each tree trains on all fails plus an equal-sized sample of passes.

**Choice, 30 Oct 2026:** A3, balanced trees. This replaces A1, which was provisional (at least 14 runs per leaf, later 50).

**Why:**
- It's a published method, the "balanced random forest", and there is no leaf size to choose and justify.
- A1 was rejected because its leaf size couldn't be justified. Leaves aren't random samples of runs, so "expected fails per leaf" arithmetic doesn't hold. Large leaves (50 runs) would also leave fold 1's trees with at most 5 leaves, which can't capture the combinations of signals that the forest was chosen for (D10).
- Each tree learns from fewer runs (78 to 180), but averaging many trees smooths that out.

**Trade-off accepted:** sklearn doesn't include balanced trees, so it has to be written and tested in this project.

**Effect on option A:** each tree already sees equal numbers of passes and fails, so `class_weight="balanced"` is no longer needed.

**Check on training data only (fold 5, out-of-bag predictions):**
- With leaves of 1 run, the forest flagged 4 runs as fails and caught 4 of the 90 fails. BER 0.48.
- With leaves of at least 14 runs, it flagged 97 runs and caught 9 of the 90 fails. BER 0.49.

---

## Findings to report

- **F1.** On 11 Oct 2008 at 07:39, six signals that are zero on every other run (s74, s206, s209, s342, s347 and s478) all fired in the same run. This looks like a one-off event, such as maintenance, a recalibration, an alarm or a logging glitch. It's worth checking against maintenance logs.
- **F2.** On the full dataset, 169 pairs of signals are near-duplicates (|r| > 0.95). Only about 5 pairs are close to exact copies (|r| > 0.9999), and none is exactly 1, so most pairs are not simple unit conversions or duplicate logging. About three-quarters of the pairs (125 of 169) sit 135–138 or 272–273 columns apart. This suggests the signals are arranged in repeating blocks of about 136 measurements. The data is anonymised, so it can't show why. Possible explanations include repeated process cycles, identical tool chambers, or different summaries of the same readings.

---

## Open, not yet discussed

- Whether `requirements.txt` should pin exact package versions, so results are reproducible later.
