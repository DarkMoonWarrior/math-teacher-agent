import os
from pathlib import Path
from tempfile import TemporaryDirectory


# Synthetic commercial-safe fixtures replace the excluded data/pilot|curated sets.
# Paths are fixed at import time so the cached Settings/QuestionBank singletons
# see them on their first construction.
_TEST_FIXTURES = Path(__file__).resolve().parents[3] / "data" / "test-fixtures" / "question-bank"
os.environ.setdefault(
    "MATH_AI_PILOT_BATCH_JSON",
    str(_TEST_FIXTURES / "pilot" / "batch-synthetic-set-probability-30q-v1.json"),
)
os.environ.setdefault(
    "MATH_AI_SET_CURATION_JSON",
    str(_TEST_FIXTURES / "curated" / "set-10q-synthetic-corrections-v1.json"),
)
os.environ.setdefault(
    "MATH_AI_PROBABILITY_CURATION_JSON",
    str(_TEST_FIXTURES / "curated" / "probability-4q-synthetic-corrections-v1.json"),
)
os.environ.setdefault(
    "MATH_AI_PROBABILITY_CURATION_2_JSON",
    str(_TEST_FIXTURES / "curated" / "probability-6q-synthetic-corrections-v1.json"),
)
os.environ.setdefault(
    "MATH_AI_FUNCTION_PILOT_BATCH_JSON",
    str(_TEST_FIXTURES / "pilot" / "function-properties-synthetic-5q-v1.json"),
)
os.environ.setdefault(
    "MATH_AI_FUNCTION_CURATION_JSON",
    str(_TEST_FIXTURES / "curated" / "function-properties-5q-synthetic-corrections-v1.json"),
)


# Test runs must be deterministic and must never consume a developer's local API quota.
os.environ["MATH_AI_DEEPSEEK_API_KEY"] = ""
os.environ["MATH_AI_LESSON_PLAN_PROVIDER"] = "local"
os.environ["MATH_AI_QUESTION_VARIANT_PROVIDER"] = "local"
os.environ["MATH_AI_SOLUTION_PROVIDER"] = "local"

# A developer may run the local app in Closed Beta mode. The general API suite
# exercises the local-development adapter unless an individual test explicitly
# overrides Settings to cover Closed Beta behavior.
os.environ["MATH_AI_BETA_ACCESS_ENABLED"] = "false"
os.environ["MATH_AI_BETA_ACCESS_ROSTER_JSON"] = "{}"

# Destructive lifecycle tests must never create a ledger beside developer data.
# The process-owned directory is removed automatically after pytest exits.
_TEST_LIFECYCLE_RUNTIME = TemporaryDirectory(prefix="math-ai-lifecycle-tests-")
os.environ["MATH_AI_OWNER_DELETION_LEDGER_DB"] = str(
    Path(_TEST_LIFECYCLE_RUNTIME.name) / "owner-deletions.sqlite3"
)
