class FakeModel:
    """Stands in for laya.Agent. answers maps a level's option keys (tuple) to (choice, confidence)."""

    def __init__(self, answers: dict[tuple[str, ...], tuple[str, float]]):
        self.answers = answers
        self.calls = 0

    def predict(self, state: dict, questions: dict) -> dict:
        self.calls += 1
        keys = tuple(questions["c"]["criteria"])
        choice, conf = self.answers[keys]
        return {"answers": {"c": {"choice": choice, "answer_confidence": conf}}}
