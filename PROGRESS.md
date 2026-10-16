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

- [x] **Milestone 4: Structural SQLite Page Parsing**
  - Implemented `uniforensic.parser.varint`: 1-9 byte varint decoder/encoder with overflow protection and boundary limits.
  - Implemented `uniforensic.parser.record`: Full serial-type decoder (NULL, INT 1-8B, FLOAT, TEXT, BLOB, RESERVED) and record payload parser with diagnostics.
  - Implemented `uniforensic.parser.page`: B-tree page header parsing (0x02, 0x05, 0x0a, 0x0d), cell pointer array parser, freeblock linked-list traverser with cycle detection, unallocated space ranges.
  - Implemented `uniforensic.parser.wal`: 32-byte WAL header parser, 24-byte frame header extractor with salt & checksum verification.
  - Implemented `uniforensic.parser.integrity`: Database header (Page 1) and freelist trunk/leaf page traverser.
  - Verified with 6 unit tests in `tests/test_parser.py`.

- [x] **Milestone 5: Structural Candidate Carver**
  - Implemented `uniforensic.carver.candidate`: `CandidateRecord` model tracking file offsets, page number, region type (FREEBLOCK, UNALLOCATED_SPACE, FREELIST_PAGE, WAL_FRAME, LIVE_CELL), diagnostics, and raw payload references.
  - Implemented `uniforensic.carver.schema_matcher`: Type affinity and column structure compatibility matching.
  - Implemented `uniforensic.carver.btree_carver`: Carves deleted cells and records from freeblock chains, page unallocated slack, and freelist leaf pages.
  - Implemented `uniforensic.carver.wal_carver`: Carves records, freeblocks, and historical transactions from Write-Ahead Log frames.
  - Verified defensive handling against masquerading freeblock headers and zeroed payloads under `secure_delete=1`.
  - Verified with 3 integration tests in `tests/test_carver.py`.

- [x] **Milestone 6: Candidate Feature Extraction & Structural Baseline**
  - Implemented `uniforensic.features.extractor`: 30 explainable SQLite structural features covering header validity, serial types, payload truncation, UTF-8 validity, timestamp plausibility, Shannon byte entropy, zero-byte fraction, schema compatibility, and storage regions.
  - Ensured strict zero-leakage of ground-truth labels.
  - Implemented `uniforensic.features.baseline_rules`: Deterministic `StructuralOnlyClassifier` enforcing SQLite invariants and heuristic constraints.
  - Verified with 4 unit tests in `tests/test_features.py`.

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
