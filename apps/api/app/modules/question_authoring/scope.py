from __future__ import annotations

import re


# Terms that unambiguously identify post-secondary mathematics in this product.
# Keep this list narrow: the boundary must not reject legitimate high-school
# enrichment merely because it uses sophisticated wording.
UNIVERSITY_ONLY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"傅里叶(?:级数|变换|分析)", "傅里叶分析"),
    (r"拉普拉斯变换", "拉普拉斯变换"),
    (r"马尔可夫链", "马尔可夫链"),
    (r"随机过程", "随机过程"),
    (r"测度论", "测度论"),
    (r"泛函分析", "泛函分析"),
    (r"实变函数", "实变函数"),
    (r"复变函数", "复变函数"),
    (r"偏微分方程", "偏微分方程"),
    (r"抽象代数", "抽象代数"),
    (r"(?:群|环|域)的同态", "抽象代数同态"),
    (r"勒贝格(?:积分|测度)", "勒贝格理论"),
)


def university_only_terms(*values: str) -> list[str]:
    combined = "\n".join(value for value in values if value)
    return [
        label
        for pattern, label in UNIVERSITY_ONLY_PATTERNS
        if re.search(pattern, combined, flags=re.IGNORECASE)
    ]
