"""Labeled explanation for every experiment the agent picks (plan Section 8.3).

Levels: mechanistic (a pathway in these cells, with predicted responder lines),
cross_cancer (worked in other tumor types), statistical (similar drugs behaved this way).
A pick labeled mechanistic whose hypothesis names no responder lines is downgraded to
statistical, so every mechanistic explanation carries a testable prediction."""


def explain(pick, book):
    """Log fields for one pick: hypothesis_id, explanation_level, explanation_text, retrieved_source_ids."""
    h = book.items.get(pick.hypothesis_id)
    level, text = pick.level, pick.reason
    if h is not None:
        text = f"{h.statement} | Why this experiment: {pick.reason}"
        if level == "mechanistic":
            if h.predicted_responders:
                text += f" | Predicted responders: {', '.join(h.predicted_responders)}"
            else:
                level = "statistical"
                text += " | (downgraded from mechanistic: no predicted responder lines)"
    elif level == "mechanistic":
        level = "statistical"  # "explore" picks have no hypothesis to carry a prediction
    return {
        "hypothesis_id": pick.hypothesis_id,
        "explanation_level": level,
        "explanation_text": text,
        "retrieved_source_ids": "; ".join(h.evidence_ids) if h else "",
    }
