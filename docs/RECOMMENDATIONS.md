# Recommendation engine: design and upgrade path

Written when the keyword-overlap matcher (`app/matching/`) was replaced with
`app/recommendations/`. Explains what data actually exists, why the model
takes the shape it does, and what to build next once real usage data exists.

## 1. What data is actually available today

- `profiles.skills`, `profiles.industries` -- free-text lists the user enters.
- `profiles.job_type`, `profiles.experience_level` -- coarse enums, always populated (defaults exist).
- `profiles.location`, `profiles.open_to_remote`, `profiles.desired_salary_min/max` -- present but frequently null.
- `listings.required_skills` -- keyword-tagged at ingestion (`app/listings/ingestion/skills.py`).
- `listings.category` -- Adzuna's own `category.label`, a genuine structured field (not text-mined).
- `listings.listing_type`, `location`, `salary_min/max`, `title`, `description`.
- `saved_opportunities`, `applications`, `tailored_documents` -- binary interaction signals per user.
- `cv_versions.candidate_facts_json` -- structured facts extracted by Gemini, but only populated *after* a tailoring request against a specific listing. Not usable as a browse-time signal for a new user.

## 2. What's missing

- No click/impression/view tracking at all.
- No outcome data anywhere in the schema -- no "got an interview", no "got hired". There is currently no ground truth to fit a model against, for any approach, PGM or otherwise.
- No negative signal (a dismissed/skipped listing) -- only positive signals exist, and even those are sparse for a brand-new product.
- `education_level` is free text with no ordinal mapping.

## 3. Why not a trained/learned Bayesian network

A Bayesian network whose conditional probability tables are *fit* from data needs both volume and labels. Neither exists yet: interaction counts will be near-zero at launch, and there is no "successful match" label in the schema at all. Fitting parameters against that would not be more rigorous than guessing them by hand -- it would just look more rigorous while being equally unfalsifiable. That's a worse position than an honest heuristic, not a better one.

## 4. What was built instead

A **naive-Bayes-shaped scoring function** (`app/recommendations/`):

- `features.py` -- pure functions, each producing an independent P(good fit | this one factor) in `[0, 1]`: skill overlap, experience-level match, job-type match, location match, industry match, salary overlap, and an optional "similar to what you've engaged with" factor.
- `scoring.py` -- combines the factors via a **logarithmic opinion pool**: each factor's logit, averaged weighted by hand-set importance, mapped back through a sigmoid. This is the standard way to fuse independent probabilistic estimates, and is exactly a naive Bayes combination up to the normalizing constant.
- `service.py` -- orchestrates DB access, cold-start factor omission, and the human-readable explanation.

This is a genuine (if simple) probabilistic graphical model: a set of conditionally-independent evidence nodes feeding one latent "suitability" node -- just with hand-calibrated rather than data-fitted parameters, which is stated as such everywhere in the code rather than presented as more rigorous than it is.

**Missing data is never a penalty.** Every factor returns 0.5 (neutral -- "no evidence") when its inputs are absent, never 0. The old keyword matcher's worst bug was scoring an under-tagged listing as a hard 0 and burying it; this cannot happen here.

**Cold start works by construction**, not as a bolted-on special case: every factor except `engagement` needs nothing but the profile and the listing, both of which exist the moment either is created. `engagement` (the one factor that depends on interaction history) is *omitted*, not scored at neutral, when a user has none -- appending a neutral opinion to the pool would dilute confidence for every new user for no reason connected to actual fit.

## 5. What was deliberately deferred

- **Collaborative filtering** (user-user or item-item similarity) -- needs interaction density this product won't have for a long time post-launch.
- **Fitting the weights/curves from data** (e.g. logistic regression on saved/applied as weak labels) -- the factor structure above does not need to change for this; only the hand-set numbers in `scoring.FACTOR_WEIGHTS` and the curves in `features.py` would move from priors to fitted values, once there's enough labeled interaction volume to fit against without overfitting to noise.
- **Click/impression tracking** -- needs a new events table and real traffic; not built now because there's nothing to populate it with yet.
- **A full (non-naive) Bayesian network** with learned dependencies between factors -- needs enough data to estimate joint distributions, which is further out than even the univariate calibration above.
- **Embeddings / semantic similarity** between profile and listing text -- the natural "smarter" upgrade once keyword matching is validated in production, but it adds a model-hosting/inference dependency that isn't justified before launch.

## 6. Where to look

- `app/recommendations/features.py` -- one function per factor, each with its own docstring explaining the calibration choice.
- `app/recommendations/scoring.py` -- the combination math.
- `app/recommendations/service.py` -- orchestration, cold-start handling, human-readable summaries.
- `tests/test_recommendations_*.py` -- deterministic unit coverage for all of the above.
