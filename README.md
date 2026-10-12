# Ginkgo CI dashboard

A static page that shows what Ginkgo's CI covers and which jobs fail on
`develop`. It covers the GitLab jobs (TUM, HoreKa, CSCS) and the GitHub
Actions jobs.

## Goals

The page answers two questions for Ginkgo maintainers:

1. **What does the CI cover?** Toolchain versions, debug or release, shared
   or static, MPI, OpenMP and precision options, and the hardware
   architecture and generation each job runs on. It also compares the tested
   versions with the versions Ginkgo claims to support.
2. **What is failing on `develop`?** Which jobs fail, on which machine,
   whether a job is flaky or consistently broken, and the likely reason.

So when someone changes the CI, the page shows what coverage was gained or
lost. When `develop` is red, it lists the failing jobs and their reasons,
without opening GitLab job by job.

All the data is public: the page needs no server and no token with write
access. It does not start, retry or cancel jobs. It doesn't keep per-test
history either; CDash already has that for the sanitizer jobs.

## How it works

```
Ginkgo checkout (develop) --+
hardware.yml               -+--> extract --> site/coverage.json --+
environments.yml           -+                                     +--> site/ (static page)
supported.yml              -+                                     |
GitLab API, GitHub API -------> status ----> site/status.json ----+
```

- **`python -m extract`** reads a Ginkgo checkout's CI configuration into
  `site/coverage.json`, with one entry per job.
  - **GitLab:** it resolves `.gitlab-ci.yml` with its local includes,
    `extends` and variables, and maps each job's rules to the pipelines it
    runs in.
  - **GitHub:** it expands the matrices of the workflows in
    `.github/workflows/`.
  - **Build options:** come from the CMake flags in each job's script.
  - **Toolchain versions:** come from module loads, image and job names, and
    `environments.yml`.
  - **Machines:** `hardware.yml` says which machines can run each job and
    which one it is sent to.
- **`python -m status`** reads the job results into `site/status.json`.
  - **Sources:** the GitLab API (the ginkgo-public-ci project and the CSCS
    project) and the GitHub API.
  - **History:** each job's results for the last 10 commits pushed to
    `develop`.
  - **Jobs that don't run on `develop`:** their latest result from a pull
    request.
  - **Failure reasons:** classified from the job log, e.g. build, tests,
    timeout, disk, runner or the Slurm time limit.
- **`site/`** is the page: `index.html`, `style.css`, `app.js`, and
  `logic.js`, which holds the pure functions the tests cover. It only reads
  the two JSON files and makes no API calls. It has three views:
  - **Status:** the jobs on `develop`, failing ones first, with their recent
    history.
  - **Coverage:** a grid of toolchains against hardware.
  - **Supported vs. tested:** for each toolchain, the tested versions against
    the supported range.

  All three views can be filtered by CI, site, machine, pipeline, build
  options and result.

`.github/workflows/update.yml` runs the tests, both scripts and the deployment
to GitHub Pages every 30 minutes, on pushes to `main` and by hand.
- **Failed steps:** a failed step deploys nothing, so the page keeps the last
  good data and shows how old it is.
- **Stale data:** data more than a day old gets a red banner. That happens,
  for example, when GitHub turns off the schedule after 60 days without
  commits to this repository; re-enable the workflow under Actions.
- **Why the workflow fetches the data:** anonymous GitHub API calls are
  limited to 60 per hour per IP address, which colleagues on one university
  network would share.

## Repository layout

```
extract/            coverage extractor (GitLab, GitHub, CMake flags, toolchains, hardware)
status/             result fetcher (GitLab, GitHub, failure reasons, merging)
site/               the static page; coverage.json and status.json are generated
hardware.yml        machines, runners and their tags
environments.yml    versions of images, uenvs and runner images
supported.yml       Ginkgo's supported version range per toolchain
tests/              pytest tests and tests/js/ for the page logic
```

## Hand-kept files

- `hardware.yml`: the machines behind the runners.
  - **TUM runners:** their tags are copied from the gitlab-meta-runner
    config, without tokens. Update them when the runners change.
  - **Which runner gets a job:** the meta-runner sends it to the matching
    runner with the fewest tags.
- `environments.yml`: the versions of environments whose names don't
  contain them, such as Rocky images, CSCS uenvs and GitHub runner images.
  Quote every version.
- `supported.yml`: Ginkgo's supported version range per toolchain. `max` is
  optional.

Fix the extractor's warnings, which are listed at the top of the page, by
adding entries to these files.

## Running it locally

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pytest
.venv/bin/python -m pytest && node --test tests/js/*.test.js
.venv/bin/python -m extract /path/to/ginkgo site/coverage.json
GITHUB_TOKEN=$(gh auth token) .venv/bin/python -m status site/coverage.json site/status.json
.venv/bin/python -m http.server 8000 --directory site   # http://localhost:8000
```

Without `GITHUB_TOKEN`, GitHub allows 60 API calls per hour, which is enough for
about two runs.

`GINKGO_DIR=/path/to/ginkgo .venv/bin/python -m pytest tests/test_real_ginkgo.py -s`
runs the extractor on a real checkout and prints its warnings.
