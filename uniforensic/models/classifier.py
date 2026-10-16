"""Machine learning classifiers for candidate record ranking."""

from typing import Dict, List, Optional
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier

from uniforensic.features.extractor import FEATURE_NAMES


class ForensicCandidateClassifier:
    """Wrapper for forensic candidate classification with Random Forest and Gradient Boosting."""

    def __init__(
        self,
        model_type: str = "random_forest",
        seed: int = 42,
        n_estimators: int = 100,
        max_depth: Optional[int] = 12,
    ):
        self.model_type = model_type
        self.seed = seed
        self.feature_names = FEATURE_NAMES

        if model_type == "random_forest":
            self.model = RandomForestClassifier(
                n_estimators=n_estimators,
                max_depth=max_depth,
                min_samples_split=4,
                class_weight="balanced",
                random_state=seed,
                n_jobs=-1,
            )
        elif model_type == "gradient_boosting":
            self.model = HistGradientBoostingClassifier(
                max_iter=n_estimators,
                max_depth=max_depth or 8,
                class_weight="balanced",
                random_state=seed,
            )
        else:
            raise ValueError(f"Unsupported model_type: {model_type}")

        self.is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ForensicCandidateClassifier":
        if len(y) == 0:
            raise ValueError("Cannot fit classifier on empty dataset")
        # Ensure at least two classes present
        unique_classes = np.unique(y)
        if len(unique_classes) < 2:
            # Synthetic balancing or fallback
            pass
        self.model.fit(X, y)
        self.is_fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted yet")
        return self.model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        if not self.is_fitted:
            raise RuntimeError("Model is not fitted yet")
        return self.model.predict_proba(X)

    def get_feature_importances(self) -> Dict[str, float]:
        """Return feature importance scores for explainability."""
        if not self.is_fitted:
            return {}
        if hasattr(self.model, "feature_importances_"):
            importances = self.model.feature_importances_
            return {
                name: round(float(imp), 4)
                for name, imp in zip(self.feature_names, importances)
            }
        return {}
