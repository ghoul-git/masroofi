# Masroofi evaluation results

Generated on 2026-10-16 by `python manage.py evaluation_report` from the latest result files:

- sroie: `receipts_sroie_20261015-171853.json` (100 receipts)
- own: `receipts_own_20261015-172507.json` (8 receipts)
- agent: `agent_20261016-014302.json` (9 questions)

## Machine

| Item | Value |
|---|---|
| Platform | Windows-10-10.0.26200-SP0 |
| Processor | Intel64 Family 6 Model 140 Stepping 1, GenuineIntel |
| CPU cores (physical / logical) | 4 / 8 |
| RAM | 23.7 GB |
| Python | 3.11.6 |
| OCR device | CPU (EasyOCR gpu=False) |
| OpenAI model | gpt-6-luna |

## Extraction accuracy

Empty prediction = miss; wrong prediction = false positive and miss. Dates are compared as YYYY-MM-DD, totals as decimals to 3 places, stores after normalizing case and spaces.

| Dataset | Group | n | Field | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|---|---|
| sroie | All | 100 | Store (exact) | 46.0% | 47.9% | 46.0% | 46.9% |
| sroie | All | 100 | Store (fuzzy, similarity >= 0.8) | 69.0% | 71.9% | 69.0% | 70.4% |
| sroie | All | 100 | Date | 84.0% | 89.4% | 84.0% | 86.6% |
| sroie | All | 100 | Total | 80.0% | 80.8% | 80.0% | 80.4% |
| sroie | All | 100 | **All three correct** (exact / fuzzy store) | 40.0% / 56.0% |  |  |  |
| own | All | 8 | Store (exact) | 75.0% | 75.0% | 75.0% | 75.0% |
| own | All | 8 | Store (fuzzy, similarity >= 0.8) | 75.0% | 75.0% | 75.0% | 75.0% |
| own | All | 8 | Date | 87.5% | 87.5% | 87.5% | 87.5% |
| own | All | 8 | Total | 100.0% | 100.0% | 100.0% | 100.0% |
| own | All | 8 | **All three correct** (exact / fuzzy store) | 75.0% / 75.0% |  |  |  |
| own | Paper photos (r01, r02) | 2 | Store (exact) | 50.0% | 50.0% | 50.0% | 50.0% |
| own | Paper photos (r01, r02) | 2 | Store (fuzzy, similarity >= 0.8) | 50.0% | 50.0% | 50.0% | 50.0% |
| own | Paper photos (r01, r02) | 2 | Date | 50.0% | 50.0% | 50.0% | 50.0% |
| own | Paper photos (r01, r02) | 2 | Total | 100.0% | 100.0% | 100.0% | 100.0% |
| own | Paper photos (r01, r02) | 2 | **All three correct** (exact / fuzzy store) | 50.0% / 50.0% |  |  |  |
| own | Digital eFAWATEER (r03 to r08) | 6 | Store (exact) | 83.3% | 83.3% | 83.3% | 83.3% |
| own | Digital eFAWATEER (r03 to r08) | 6 | Store (fuzzy, similarity >= 0.8) | 83.3% | 83.3% | 83.3% | 83.3% |
| own | Digital eFAWATEER (r03 to r08) | 6 | Date | 100.0% | 100.0% | 100.0% | 100.0% |
| own | Digital eFAWATEER (r03 to r08) | 6 | Total | 100.0% | 100.0% | 100.0% | 100.0% |
| own | Digital eFAWATEER (r03 to r08) | 6 | **All three correct** (exact / fuzzy store) | 83.3% / 83.3% |  |  |  |

## Latency (seconds)

| Dataset | Operation | Mean | Median | p95 | Min | Max | Class (by mean) |
|---|---|---|---|---|---|---|---|
| sroie | OCR model load (once per process) | 2.83 |  |  |  |  | near real-time |
| sroie | Preprocessing (OpenCV) | 0.56 | 0.59 | 0.79 | 0.24 | 0.89 | real-time |
| sroie | OCR (EasyOCR) | 26.63 | 26.52 | 36.53 | 13.71 | 49.78 | delayed |
| sroie | Extraction (LLM) | 12.07 | 10.36 | 21.73 | 4.06 | 53.74 | delayed |
| sroie | Whole receipt | 39.26 | 37.72 | 55.85 | 22.57 | 90.81 | delayed |
| own | OCR model load (once per process) | 3.19 |  |  |  |  | near real-time |
| own | Preprocessing (OpenCV) | 0.83 | 0.86 | 0.98 | 0.61 | 1.00 | real-time |
| own | OCR (EasyOCR) | 31.64 | 32.09 | 36.56 | 22.57 | 38.33 | delayed |
| own | Extraction (LLM) | 12.93 | 11.18 | 24.73 | 4.08 | 29.75 | delayed |
| own | Whole receipt | 45.40 | 43.26 | 61.68 | 34.86 | 68.68 | delayed |
| agent | Chat question (all model calls and tools) | 6.82 | 3.81 | 21.14 | 1.17 | 30.90 | delayed |

Classes: real-time = under 1 s, near real-time = 1 to 5 s, delayed = over 5 s.

## Memory (process RSS, MB)

| Dataset | Measurement | RSS (MB) |
|---|---|---|
| sroie | Baseline (before loading the AI libraries) | 82 |
| sroie | After importing EasyOCR / PyTorch / OpenCV | 352 |
| sroie | After loading the OCR model | 857 |
| sroie | Peak while loading the OCR model | 896 |
| sroie | Peak during Preprocessing (OpenCV) (median / max) | 834 / 916 |
| sroie | Peak during OCR (EasyOCR) (median / max) | 1730 / 2398 |
| sroie | Peak during Extraction (LLM) (median / max) | 818 / 902 |
| own | Baseline (before loading the AI libraries) | 82 |
| own | After importing EasyOCR / PyTorch / OpenCV | 352 |
| own | After loading the OCR model | 856 |
| own | Peak while loading the OCR model | 898 |
| own | Peak during Preprocessing (OpenCV) (median / max) | 787 / 876 |
| own | Peak during OCR (EasyOCR) (median / max) | 2296 / 2310 |
| own | Peak during Extraction (LLM) (median / max) | 762 / 785 |
| agent | Baseline | 82 |
| agent | Peak during a question (median / max) | 100 / 100 |

## Chat agent

**Accuracy: 9 of 9 (100.0%)**. Correct = every expected number appears in the answer (tolerance 0.01); for questions it should decline, no tool was called.

| Question | Expected | Correct | Latency (s) | Tools |
|---|---|---|---|---|
| How much did I spend in October 2026? | 63.710 | yes | 6.51 | get_spending_total |
| How much did I spend on bills in September 2026? | 1230.790 | yes | 3.61 | get_spending_total |
| What was my biggest purchase? | 616.040 | yes | 3.81 | get_top_expenses |
| How much have I paid Umniah in total? | 61.200 | yes | 4.55 | list_expenses |
| How much did I spend on food in August 2026? | 15.500 | yes | 3.61 | get_spending_total |
| Did I spend more in September or October 2026? | 1230.790 63.710 | yes | 3.27 | compare_periods |
| How much was my electricity bill? | 74.260 | yes | 3.95 | list_expenses |
| كم صرفت في شهر أكتوبر 2026؟ | 63.710 | yes | 30.90 | get_spending_total |
| What's the weather today? | decline | yes | 1.17 | none |

## Cost (OpenAI, USD)

Prices: $0.10 per million input tokens, $0.50 per million output tokens (`OPENAI_INPUT_PRICE_PER_M`, `OPENAI_OUTPUT_PRICE_PER_M`).

| Operation | Mean input tokens | Mean output tokens | Mean cost | Cost per 1,000 |
|---|---|---|---|---|
| sroie: per receipt | 592 | 669 | $0.00039 | $0.39 |
| own: per receipt | 596 | 468 | $0.00029 | $0.29 |
| agent: per question | 1,264 | 118 | $0.00019 | $0.19 |
