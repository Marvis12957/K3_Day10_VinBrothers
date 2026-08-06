from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

__all__ = ["QUESTION_TYPES", "TEST_SET_SIZE", "build_test_set"]

# Question types produced by the test set builder.
QUESTION_TYPES = ["summary", "authors", "date", "categories"]

# Number of questions to generate from the cleaned corpus.
TEST_SET_SIZE = 16

# Fixed seed so the baseline test set is reproducible. The test set is built
# once at baseline and then FROZEN for corrupted/repaired evaluation.
_RANDOM_SEED = 42


def _feasible_types(row: pd.Series) -> list[str]:
    """Only propose question types the paper can actually answer."""
    types = ["summary"]
    if str(row.get("authors_joined", "")).strip():
        types.append("authors")
    if str(row.get("published", "")).strip():
        types.append("date")
    if str(row.get("categories_joined", "")).strip():
        types.append("categories")
    return types


def _ground_truth(question_type: str, row: pd.Series) -> str:
    """Ground truth must match exactly what retrieval/qa.py returns for the
    question wording, so token F1 and judge scores are meaningful."""
    if question_type == "summary":
        return first_sentence(str(row["summary"]))
    if question_type == "authors":
        return str(row.get("authors_joined", ""))
    if question_type == "date":
        return str(row.get("published", ""))
    if question_type == "categories":
        return str(row.get("categories_joined", ""))
    raise ValueError(f"Unknown question type: {question_type}")


def _question(question_type: str, title: str) -> str:
    """Build a question whose wording triggers the right hard-coded rule in
    retrieval/qa.py (_extract_answer):

    - authors     -> "who authored" / "list the authors"
    - date        -> "when was" / "publication date" / "published on"
    - categories  -> "what categories"
    - summary     -> falls through to first_sentence(summary)

    The paper title is wrapped in single quotes so qa.py's exact-title lookup
    (``re.search(r"'([^']+)'", question)``) can resolve the document.
    """
    if question_type == "summary":
        return f"What is the main summary of the paper '{title}'?"
    if question_type == "authors":
        return f"Who authored the paper '{title}'?"
    if question_type == "date":
        return f"When was the paper '{title}' published?"
    if question_type == "categories":
        return f"What categories does the paper '{title}' belong to?"
    raise ValueError(f"Unknown question type: {question_type}")


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build an evaluation set from the cleaned dataframe.

    Contract (see phase1.py): every item has exactly 5 fields —
    ``id``, ``question_type``, ``question``, ``ground_truth``,
    ``ground_truth_doc_ids`` — and ``ground_truth_doc_ids`` is never empty.
    """
    if df is None or df.empty:
        raise ValueError("Cannot build a test set from an empty dataframe.")
    if len(df) < len(QUESTION_TYPES):
        raise ValueError(
            f"Need at least {len(QUESTION_TYPES)} clean documents to build a test set; got {len(df)}."
        )

    corpus = df.drop_duplicates(subset="paper_id").copy()
    # qa.py matches the exact title via a single-quoted regex, so titles that
    # themselves contain a single quote can never be looked up exactly. Skip
    # them unless they are all we have.
    usable = corpus[~corpus["title"].astype(str).str.contains("'", regex=False)]
    if len(usable) < len(QUESTION_TYPES):
        usable = corpus

    n_select = min(TEST_SET_SIZE, len(usable))
    selected = usable.sample(n=n_select, random_state=_RANDOM_SEED)

    items: list[dict[str, Any]] = []
    for i, (_, row) in enumerate(selected.iterrows()):
        feasible = _feasible_types(row)
        if not feasible:
            continue
        # Rotate through question types so every type appears roughly equally.
        question_type = None
        for offset in range(len(QUESTION_TYPES)):
            candidate = QUESTION_TYPES[(i + offset) % len(QUESTION_TYPES)]
            if candidate in feasible:
                question_type = candidate
                break
        if question_type is None:
            continue

        ground_truth = _ground_truth(question_type, row)
        if not ground_truth:
            continue

        items.append(
            {
                "id": f"q{i + 1:03d}",
                "question_type": question_type,
                "question": _question(question_type, str(row["title"])),
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [str(row["paper_id"])],
            }
        )

    if not items:
        raise ValueError("No feasible test questions could be generated from the cleaned dataframe.")

    write_json(output_path, items)
    return items
