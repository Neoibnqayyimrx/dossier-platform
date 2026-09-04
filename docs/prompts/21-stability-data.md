# P21 — Stability as data, not a paragraph

**Before starting:** read `docs/target-toc.yaml` (`stability_timepoints`), `app/models/stability.py`, the `shelf_life_within_stability` rule in `app/validation/rules.py`, `backend/templates/stability_summary.docx`, and `reference/kb_sources/ich/Q1A_R2_stability_testing.pdf` for the study design vocabulary. Depends on P20 — stability results are checked against specifications.

## Goal

Unblock **4 leaves** and upgrade an existing validation rule from a duration check into a real out-of-specification check.

## The problem, stated precisely

`StabilityStudy` carries `study_type`, `condition` (e.g. "30C/65%RH"), `duration_months`, `protocol` and `result_summary` — and `result_summary` is free text.

3.2.S.7.3 and 3.2.P.8.3 are not prose. They are **data tables**: timepoint by test by result, against the acceptance criterion, per batch, per storage condition, per pack. A text blob cannot be rendered into that table, and more importantly it cannot be checked. Today `shelf_life_within_stability` can confirm only that a claimed shelf life does not exceed the study duration. It cannot notice that dissolution failed at 6 months.

## Tasks

### P21a — Timepoint-level results (backend)

1. **A `StabilityResult` model**: study FK, timepoint in months, the `SpecificationTest` it answers, the result value, and whether it meets the criterion. Pointing results at specification tests rather than free-text test names is what makes the check possible, and it is the same move P20 makes for batch analyses.

2. **Model the axes a real study has.** A stability study is per batch, per storage condition, per pack presentation. If the current model flattens any of these, fix it now — 3.2.P.8.3 tables are organised along exactly those axes and a flattened model cannot produce them.

3. **Register the sections**: **3.2.S.7.3** (per drug substance), **3.2.P.8.3**, and the post-approval protocol and commitment leaves **3.2.S.7.2** and **3.2.P.8.2** as hybrid.

4. **Strengthen the rules.** A failing result inside the claimed shelf life is an ERROR naming the timepoint, test, result and limit. A shelf life claimed beyond the longest passing timepoint is an ERROR. Accelerated-only data supporting a long shelf life is at least a WARNING. Keep each rule a small independently testable function registered by decorator, per the existing registry design.

5. **Wire 3.2.S.7.1 and 3.2.P.8.1 to the same data.** The summary sections currently take prose. They must be generated from the timepoint data with a narrative slot for the conclusion only — otherwise the summary can contradict the table beneath it, which is the exact defect class this platform exists to eliminate.

### P21b — Entering stability data without misery (frontend)

6. **A grid, not a form.** Stability data arrives as a table — timepoints across, tests down. Entering it one field at a time through the standard wizard pattern would be unusable for a real study with 5 timepoints and 8 tests. This is the one place where deviating from `wizard-steps.ts`'s generic shape is justified; record why.

7. **Paste from a spreadsheet.** Every stability dataset in existence starts life in Excel. Accepting a paste of tabular data and mapping the columns will save more user time than any other single feature in this phase.

8. **Flag failures at entry**, against the specification, the moment a value is typed.

## Definition of done

- `scripts/check_target_toc.py` gains 4 leaves.
- A test proves a failing result inside the claimed shelf life blocks export and names the timepoint and test.
- A test proves the rendered 3.2.P.8.1 summary cannot state a shelf life the 3.2.P.8.3 data does not support.
- A realistic multi-timepoint study seeds and renders end to end.

## Build log

Record the grid-versus-wizard decision and what it costs in consistency with the rest of the UI. Record how the study axes are modelled — that shape is hard to change later.
