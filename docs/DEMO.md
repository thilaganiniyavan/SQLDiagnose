# Demo guide

A 5–7 minute walkthrough of SQLDiagnose, plus answers to the questions reviewers usually ask.

## Before the demo

```bash
make frontend        # once, builds the web app
make api             # wait for "Classifier loaded", then open http://localhost:8000
```

Warm-up (so nothing loads during the demo): run one diagnosis, and one *Question → SQL* request — the
first NL2SQL request loads the generator (~10 s); on this laptop a question takes 10–60 s. Keep the laptop plugged in.
Clear old entries on the *History* page if you want a clean slate.

To let the audience open the app on their own devices, run `make demo` instead of `make api`: it prints a public
`https://<random>.trycloudflare.com` link (new each run, valid while it runs; Ctrl+C stops it). Live
PostgreSQL/MySQL schema import is disabled on this link, and the laptop must stay awake and online.

## Walkthrough

1. **The problem (30 s).** Database errors say *that* a query failed (`near "x": syntax error`), not *why*, and
   logically wrong queries (`= NULL`, missing join condition, non-grouped columns) often produce no error at all.

2. **Several errors at once (1 min).** *Diagnose & repair* → *Examples* → **Several errors at once** →
   *Analyze* (or `Ctrl+Enter`): `SELEC Name, count(*) FORM singr WHERE Age > 'thirty'`.
   - Verdict SYNTAX_ERROR (reported first, like a real engine).
   - Repair: five verified steps — two keyword typos, the unknown table `singr → singer`, `'thirty' → 30`,
     and the missing `GROUP BY Name`. The diff shows exactly what changed.
   - *Use this query* re-checks the fix (no problems found) and *Run query* shows the rows it returns from the
     real database.

3. **Why the model decided (1 min).** Load **Unknown table** or **Aggregate in WHERE** and
   point at the token attributions: the red tokens (`singers`, `avg`) are what pushed the model to its answer.
   Mention *decided by analyzer+model*: the verified analyzer and the learned classifier agree.

4. **Errors that run without complaint (1 min).** **Missing join condition** — SQLite would
   execute it and return a Cartesian product. The repair infers `ON T2.Stadium_ID = T1.Stadium_ID` from the
   foreign key.

5. **Access policy (30 s).** **Restricted table (stadium)** — the stadium table shows a lock in the schema panel
   (any table or column can be locked by clicking its lock icon); the verdict comes from the policy, and the
   engine deliberately does not "repair" it.

6. **Question → SQL (1 min).** Ask *"Which singers are older than the average age? Show their names and
   countries."* The progress panel shows each stage. Show the candidate table: rejected candidates are listed
   with the reason, the returned query is one that passed verification, and *Run query* answers the question.

7. **Your own database (30 s, optional).** *Schemas* → *CREATE TABLE* → paste a couple of tables → *Read schema*
   → *Save and use*; every page now checks against it. A SQLite file can be imported with its data.

8. **Results (1 min).** *Research results*: 87% accuracy on databases never seen in training (vs 53% for TF-IDF),
   the confusion matrix, and the NL2SQL comparison (the code LLM with verification + repair answers 55% of
   questions correctly vs 16% for the raw T5 baseline).

## Likely questions

**Why do you need a model if the analyzer is exact?**
The analyzer needs a schema. The model gives a calibrated opinion without one, explains itself with token
attributions, and is the research component (how well can a small transformer learn these verdicts from text?).
In the service, the analyzer's verified findings always take precedence.

**Aren't the labels circular?**
The labels come from the analyzer, so the analyzer is validated separately: 96.5% of 8,034 human-written Spider
queries pass, and the flagged 3.5% are genuine problems (listed in the report).

**Is the data leaking between train and test?**
No. Train, validation and test use different databases; the test set is the 20 Spider-dev databases.

**Why is UNKNOWN_COLUMN the weakest class?**
The model must notice that a plausible name (`Nmae`, `singer_name`) is *not* in the listed columns, which needs
character-level comparison a small model does imperfectly. Table names are few and short, so UNKNOWN_TABLE is
nearly perfect. A larger encoder (GPU notebook) is the expected fix.

**Why does NL2SQL accuracy stay moderate even after repair?**
Repair guarantees a *valid* query, not the *intended* one. Validity roughly doubles; correctness improves less
because the generator's understanding of the question is the limit.

**Could the repair change the meaning of my query?**
Every repair is verified to be valid, and each step is shown. When the intent is unrecoverable (e.g. the value
behind `age > 'young'`) the engine refuses rather than guesses.

**How is it run in production?**
One FastAPI service serves the React web app and the REST API (`/docs` has the interactive API); Docker image,
CSV batch processing, background jobs for NL→SQL, per-browser history and saved schemas, CLI.
