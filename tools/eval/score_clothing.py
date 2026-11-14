"""Score a held-out-session predictions CSV: truth,prediction columns.

predictions may be outer, none, or uncertain. Report coverage and accuracy
both with and without abstentions so uncertainty cannot inflate the result.
"""
import argparse
import csv
from collections import Counter


def score(path):
    with open(path, newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("No prediction rows")
    counts = Counter()
    for row in rows:
        truth, pred = row.get("truth"), row.get("prediction")
        if truth not in ("outer", "none") or pred not in ("outer", "none", "uncertain"):
            raise ValueError(f"Invalid truth/prediction: {row}")
        counts[truth, pred] += 1
    n = len(rows)
    correct = sum(counts[c, c] for c in ("outer", "none"))
    covered = n - sum(counts[c, "uncertain"] for c in ("outer", "none"))
    print(f"Held-out samples: {n}; coverage: {covered}/{n} ({covered/n:.1%})")
    print(f"Accuracy counting uncertain as incorrect: {correct}/{n} ({correct/n:.1%})")
    print(f"Accuracy when classified: {correct}/{covered} ({correct/covered:.1%})" if covered else
          "Accuracy when classified: undefined (zero classified samples)")
    print("truth\\prediction,outer,none,uncertain")
    for truth in ("outer", "none"):
        print(truth + "," + ",".join(str(counts[truth, p]) for p in ("outer", "none", "uncertain")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions_csv")
    score(parser.parse_args().predictions_csv)
