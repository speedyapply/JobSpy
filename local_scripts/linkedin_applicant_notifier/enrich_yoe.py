from __future__ import annotations

import pandas as pd
from tqdm import tqdm

from yoe_llm_client import extract_yoe_requirement


def enrich_jobs_with_yoe(
    df: pd.DataFrame,
    description_col: str,
    checkpoint_path: str = "yoe_checkpoint.csv",
    checkpoint_every: int = 10,
) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    work = df.copy()
    for column in ["company", "title", description_col]:
        if column not in work.columns:
            work[column] = ""

    for column in ["yoe_required", "extracted_time"]:
        if column not in work.columns:
            work[column] = ""

    for index, row in tqdm(work.iterrows(), total=len(work), desc="YOE LLM"):
        info = extract_yoe_requirement(
            company=str(row.get("company", "") or ""),
            title=str(row.get("title", "") or ""),
            job_description=str(row.get(description_col, "") or ""),
        )
        work.at[index, "yoe_required"] = info.get("yoe_required", 0)
        work.at[index, "extracted_time"] = info.get("extracted_time", "")

        if checkpoint_every and (int(index) + 1) % checkpoint_every == 0:
            work.to_csv(checkpoint_path, index=False)

    work.to_csv(checkpoint_path, index=False)
    return work
