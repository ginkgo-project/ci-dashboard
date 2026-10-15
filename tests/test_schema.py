import pytest

from extract import schema


def coverage(jobs):
    return {"generated_at": "t", "ginkgo_commit": None, "warnings": [], "columns": ["compile-only"],
            "machines": {"m": {"column": "compile-only"}}, "supported": {}, "jobs": jobs}


def job(key, **extra):
    return {"key": key, "ci": "gitlab", "name": key, "kind": "check", "pipelines": [],
            "machines": [], "dispatched_to": [], "compile_only": False, "disabled": False,
            "build_type": None, **extra}


def test_check_coverage_accepts_a_valid_document():
    schema.check_coverage(coverage([job("a", machines=["m"])]))


def test_check_coverage_rejects_problems():
    with pytest.raises(ValueError, match="coverage: missing warnings"):
        schema.check_coverage({"generated_at": "t"})
    with pytest.raises(ValueError, match="duplicate job key a"):
        schema.check_coverage(coverage([job("a"), job("a")]))
    with pytest.raises(ValueError, match="unknown machine x"):
        schema.check_coverage(coverage([job("a", machines=["x"])]))
    with pytest.raises(ValueError, match="build job b has no build_type"):
        schema.check_coverage(coverage([job("b", kind="build")]))


def test_check_status():
    result = {"status": "success", "url": "https://x"}
    pull = {"number": 7, "title": "t", "url": "https://x/pull/7", "sha": "s", "updated_at": "t",
            "result": result, "findings": [{"path": "a.cpp", "line": 1, "check": "c", "message": "m"}]}
    good = {"generated_at": "t", "commits": [{"sha": "a"}],
            "jobs": {"k": {"history": [result], "elsewhere": None}}, "unmatched": [],
            "clang_tidy": {"check": "clang-tidy", "pulls": [pull]}}
    schema.check_status(good)
    bad = {**good, "jobs": {"k": {"history": [], "elsewhere": None}}}
    with pytest.raises(ValueError, match="k: history has 0 entries for 1 commits"):
        schema.check_status(bad)
    with pytest.raises(ValueError, match="k: missing url"):
        schema.check_status({**good, "jobs": {"k": {"history": [None], "elsewhere": {"status": "x"}}}})
    with pytest.raises(ValueError, match="pull request 7: line should be a int"):
        schema.check_status({**good, "clang_tidy": {"check": "clang-tidy", "pulls": [
            {**pull, "findings": [{"path": "a.cpp", "line": "1", "check": "c", "message": "m"}]}]}})
