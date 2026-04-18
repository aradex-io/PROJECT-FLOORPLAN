# CI Pipeline — Critical Review

**Date**: 24 MAR 2026
**Author**: Jay (d0sf3t)
**Status**: final

## Objective

Challenge the CI pipeline plan before execution.

## Review Notes

### What's solid

- Three parallel jobs is the right call — fast feedback, clear failure attribution
- Python matrix (3.10–3.12) covers the support range without bloat
- Using `pip install -e ".[dev]"` keeps CI in sync with what developers run locally
- No over-engineering (no codecov, no deploy steps, no frontend yet)

### Concerns raised and resolved

1. **Should we add `ruff format --check`?**
   Yes — format enforcement from day one prevents style drift. Added to plan.

2. **Should lint/typecheck run on the matrix too?**
   No — ruff and mypy results don't vary across Python patch versions. Run once on
   3.12 (latest) to save CI minutes. Only tests need the matrix.

3. **Do we need `permissions:` blocks?**
   Not for this workflow — we only read code, no write operations. Default read
   permissions are sufficient.

4. **Should we pin action versions to SHA?**
   For a private/small project, pinning to major version (`@v5`) is acceptable.
   SHA pinning is overkill at this stage.

5. **What if mypy or ruff fails on existing code?**
   Run both locally before committing the workflow. Fix any issues in the same PR
   so CI is green from the first run.

6. **`continue-on-error` on any job?**
   No. All three jobs are hard gates. A type error or lint violation should block merge.

## Conclusion

Plan is sound. One refinement: lint and type-check should run on a single Python
version (3.12), not the full matrix. Tests run on the matrix. Proceed to execution.
