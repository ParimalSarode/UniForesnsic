# UniForensic N3: ML-Assisted SQLite Deleted Record Recovery — Progress Log

## Status: IN PROGRESS
**Author:** Digital Forensics & SQLite Internals Research Team  
**Environment:** Windows 11, Python 3.10.20 (uv managed), SQLite 3.x, scikit-learn, pandas, numpy, pytest  

---

### Milestone Tracker

- [x] **Milestone 1: Workspace & Environment Inspection**
  - Confirmed Python 3.10.20 via `uv`.
  - Installed core ML & forensics packages: `scikit-learn`, `pandas`, `numpy`, `pytest`, `matplotlib`, `scipy`, `tabulate`.
  - Verified baseline external tools:
    - `sqlite_dissect` (DoD Cyber Crime Center) installed via PyPI.
    - `bring2lite` (Christian Meng & Harald Baier, DFRWS) cloned into `third_party/bring2lite`.
    - SQLite Forensic Corpus (FAU Erlangen-Nürnberg / Digital Corpora) identified on AWS S3 (`sqlite_forensic_corpus_v1.0.zip`).
  - Added `.gitignore` rules for Python and local venv.

- [x] **Milestone 2: Architecture & Acceptance Criteria**
  - Defined modular package layout: `generator/`, `parser/`, `carver/`, `features/`, `models/`, `filter/`, `evaluation/`, `reporting/`.
  - Created data models for `GroundTruthRecord` and `DatabaseGroundTruth`.
  - Established cryptographic SHA-256 evidence hashing for evidence preservation.

- [x] **Milestone 3: Synthetic Forensic Database Generator & Ground Truth**
  - Implemented realistic mobile forensic schemas: `messages` (SMS), `call_history` (calls), `browser_history` (web).
  - Implemented scenario variations:
    - Freeblock scattered deletions (B-tree leaf freeblocks).
    - Freelist burst deletions (unallocated/freelist pages).
    - In-place updates causing residual old payload slack.
    - WAL uncheckpointed frames vs committed databases.
    - Anti-forensics: `secure_delete=1` (overwritten/zeroed) vs `secure_delete=0` (recoverable).
    - Auto-vacuum: `auto_vacuum=0` (freelist intact) vs `auto_vacuum=1` (truncated).
  - Implemented independent ground truth catalogs preventing label leakage.
  - Verified with 3 automated unit/integration tests in `tests/test_generator.py`.

- [ ] **Milestone 4: Structural SQLite Page Parsing**
  - SQLite 1-9 byte varint decoder with overflow checks.
  - Serial type interpreter (0-9, 12+ even/odd string/blob lengths).
  - B-tree page header parsing (leaf table, interior table, leaf index, interior index).
  - Freelist trunk and leaf page navigation.
  - WAL header and frame parsing (salt, checksum, page number).
  - Strict buffer bounds checking and defensive parsing.

- [ ] **Milestone 5: Structural Candidate Carver**
  - Freeblock linked-list scanning.
  - Unallocated space scanning within B-tree leaf pages.
  - Freelist page residual payload carver.
  - WAL frame uncommitted/checkpoint-overwritten carver.
  - Candidate metadata model: byte offset, page_id, cell offset, region type, raw payload.

- [ ] **Milestone 6: Candidate Feature Extraction & Structural Baseline**
  - Structural consistency features (varint lengths, serial type sequence, declared vs available length, UTF-8 validity, timestamp plausibility, entropy, region type).
  - Strict prevention of ground-truth label leakage.
  - Structural-only rule-based recovery baseline.

- [ ] **Milestone 7: Machine Learning Ranker & Probability Calibration**
  - Database-level cross-validation split (Train / Calibration / Validation / Test).
  - Random Forest classifier baseline.
  - Gradient boosting comparison (HistGradientBoosting).
  - Probability calibration via CalibratedClassifierCV (isotonic / sigmoid).
  - Brier score, Expected Calibration Error (ECE), reliability diagrams.

- [ ] **Milestone 8: Live-Row False-Positive Control**
  - Separate live-row filtering engine.
  - Primary key matching, exact tuple collision, partial payload overlap detection.
  - Segregated metrics: Live-row FP rate vs ghost/noise FP rate.

- [ ] **Milestone 9: Controlled Experiments & Comparative Evaluation**
  - Comparative benchmarking:
    1. Structural-Only Carver
    2. ML-Assisted Ranker (Uncalibrated)
    3. ML-Assisted Ranker (Calibrated Confidence)
    4. `sqlite_dissect` (DoD Cyber Crime Center)
    5. `bring2lite` (Meng & Baier, DFRWS)
  - External corpus test on SQLite Forensic Corpus sample.
  - Precision, Recall, F1, Live-Row FP rate, Brier score, Runtime across SQLite configurations.

- [ ] **Milestone 10: Research Report & Final Deliverables**
  - Automated tests passing.
  - Machine-readable CSV/JSON experiment logs.
  - Calibration plots and reliability curves.
  - Research report answering the core hypothesis.
