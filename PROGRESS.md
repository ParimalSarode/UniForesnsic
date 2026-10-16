# UniForensic N3: ML-Assisted SQLite Deleted Record Recovery — Progress Log

## Status: COMPLETED
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

- [x] **Milestone 7: Machine Learning Ranker & Probability Calibration**
  - Implemented `uniforensic.models.classifier`: Random Forest and Gradient Boosted Trees (HistGradientBoosting) with balanced weighting.
  - Implemented `uniforensic.models.calibration`: CalibratedRanker wrapping CalibratedClassifierCV with FrozenEstimator support (scikit-learn 1.7+ compliant).
  - Implemented quantitative calibration evaluation: Brier score, Expected Calibration Error (ECE), and reliability bin analytics.
  - Verified with 2 unit tests in `tests/test_models.py`.

- [x] **Milestone 8: Live-Row False-Positive Control**
  - Implemented `uniforensic.filter.live_filter`: `LiveRowFilter` extracting active SQLite tables, primary keys, and normalized tuple hashes.
  - Implemented multi-tier collision detection: exact primary key match, exact tuple match, and partial payload overlap.
  - Implemented `compute_segregated_metrics`: isolates true positives, live-row false positives ($FP_{live}$), ghost/slack noise ($FP_{ghost}$), and filtered precision.
  - Excluded freelist leaf and trunk pages from active B-tree cell carving in `uniforensic.carver.btree_carver`.
  - Verified with 2 integration tests in `tests/test_live_filter.py`.

- [x] **Milestone 9: Controlled Experiments & Comparative Evaluation**
  - Implemented `uniforensic.evaluation.adapters`: Unified benchmark adapter interface for 6 systems:
    1. `Structural-Only Carver` (baseline)
    2. `Random Forest (Uncalibrated)`
    3. `Random Forest (Calibrated)`
    4. `Gradient Boosted Trees`
    5. `sqlite_dissect` (DoD Cyber Crime Center)
    6. `bring2lite` (Christian Meng & Harald Baier, DFRWS)
  - Implemented `BenchmarkExperimentRunner` executing across 5 controlled SQLite configurations:
    - Default scattered freeblock deletions
    - Anti-forensics: `secure_delete=1`
    - Space reclamation: `auto_vacuum=1`
    - WAL uncheckpointed frames
    - Heavy corpus distractor noise
  - Machine-readable export to JSON (`out/artifacts/benchmark_results.json`) and CSV (`out/artifacts/benchmark_results.csv`).
  - Verified with 2 integration tests in `tests/test_evaluation.py`.

- [x] **Milestone 10: Research Report & Final Deliverables**
  - Implemented `uniforensic.reporting.plots`: Reliability curves (ECE comparison), system comparison bar charts, and scenario breakdowns.
  - Implemented `uniforensic.reporting.report_generator`: Synthesizes comprehensive publication-grade markdown report `RESEARCH_REPORT.md`.
  - Verified all 22 automated tests passing across the entire test suite.
  - Generated and saved publication plots to `out/artifacts/`.
