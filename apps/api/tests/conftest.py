import os
from pathlib import Path



# Synthetic commercial-safe fixtures replace the excluded data/pilot|curated sets.
# Paths are fixed at import time so the cached Settings/QuestionBank singletons
# see them on their first construction.
os.environ.setdefault(
    'MATH_AI_PILOT_BATCH_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'pilot' / 'batch-synthetic-set-probability-30q-v1.json'),
)
os.environ.setdefault(
    'MATH_AI_SET_CURATION_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'curated' / 'set-10q-synthetic-corrections-v1.json'),
)
os.environ.setdefault(
    'MATH_AI_PROBABILITY_CURATION_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'curated' / 'probability-4q-synthetic-corrections-v1.json'),
)
os.environ.setdefault(
    'MATH_AI_PROBABILITY_CURATION_2_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'curated' / 'probability-6q-synthetic-corrections-v1.json'),
)
os.environ.setdefault(
    'MATH_AI_FUNCTION_PILOT_BATCH_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'pilot' / 'function-properties-synthetic-5q-v1.json'),
)
os.environ.setdefault(
    'MATH_AI_FUNCTION_CURATION_JSON',
    str(Path(__file__).resolve().parents[3] / 'data' / 'test-fixtures' / 'question-bank' / 'curated' / 'function-properties-5q-synthetic-corrections-v1.json'),
)

# Test runs must be deterministic and must never consume a developer's local API quota.
os.environ["MATH_AI_DEEPSEEK_API_KEY"] = ""
os.environ["MATH_AI_LESSON_PLAN_PROVIDER"] = "local"
os.environ["MATH_AI_QUESTION_VARIANT_PROVIDER"] = "local"
os.environ["MATH_AI_SOLUTION_PROVIDER"] = "local"
