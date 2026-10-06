"""Train the lead-scoring classifier from data/labeled_leads.csv and save it to models/.

    python train_classifier.py

CSV columns: name,phone,email,need,budget,timeline (1 = visitor shared it, 0 = not),
user_text (everything the visitor typed), qualified (1 = owner judged it a real sales lead).
Add real labeled conversations from /admin to the CSV and re-run to improve the model.
"""
import csv

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from app.classifier import DATA_PATH, FEATURE_NAMES, FIELDS, MODEL_PATH, features


def load_data():
    X, y = [], []
    with DATA_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lead = {k: row[k] == "1" for k in FIELDS}
            X.append(features(lead, row["user_text"]))
            y.append(int(row["qualified"]))
    return X, y


def main():
    X, y = load_data()
    print(f"{len(y)} labeled leads ({sum(y)} qualified, {len(y) - sum(y)} not)\n")

    model = LogisticRegression(class_weight="balanced", max_iter=1000)

    # Honest evaluation: each lead is predicted by a model that never saw it in training.
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    pred = cross_val_predict(model, X, y, cv=cv)
    print("5-fold cross-validation:")
    print(classification_report(y, pred, target_names=["not qualified", "qualified"], digits=2))

    model.fit(X, y)
    print("Learned weights (positive = more likely qualified):")
    for name, w in sorted(zip(FEATURE_NAMES, model.coef_[0]), key=lambda p: -p[1]):
        print(f"  {name:<24} {w:+.2f}")

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    print(f"\nSaved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
