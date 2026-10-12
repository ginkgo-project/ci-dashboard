# Ginkgo CI dashboard

A static page that shows what Ginkgo's CI covers (toolchain versions, build
options, hardware) and which jobs fail on `develop`. It covers the GitLab jobs
(TUM, HoreKa, CSCS) and the GitHub Actions jobs.

- `python -m extract` reads a Ginkgo checkout's CI files into `site/coverage.json`.
- `python -m status` reads the GitLab and GitHub APIs into `site/status.json`.
- `site/` is the page. It only reads these two files.

A GitHub Actions workflow (`.github/workflows/update.yml`) does all three
every 30 minutes and deploys `site/` to GitHub Pages.

## Running it locally

```bash
python3 -m venv .venv && .venv/bin/pip install pyyaml pytest
.venv/bin/python -m pytest && node --test tests/js/
.venv/bin/python -m extract /path/to/ginkgo site/coverage.json
GITHUB_TOKEN=$(gh auth token) .venv/bin/python -m status site/coverage.json site/status.json
.venv/bin/python -m http.server 8000 --directory site   # http://localhost:8000
```

Without `GITHUB_TOKEN`, GitHub allows 60 API calls per hour, which is enough for
about two runs.

`GINKGO_DIR=/path/to/ginkgo .venv/bin/python -m pytest tests/test_real_ginkgo.py -s`
runs the extractor on a real checkout and prints its warnings.

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

## Deployment

1. Create the repository `ginkgo-project/ci-dashboard` and push.
2. In Settings → Pages, set the source to "GitHub Actions".
3. Run the workflow once by hand (Actions → Update and deploy → Run workflow).
4. For `ci.gko-project.org`:
   1. In Cloudflare (DNS for gko-project.org), add a record: type `CNAME`,
      name `ci`, target `ginkgo-project.github.io`, proxy status
      "DNS only".
   2. In Settings → Pages, set the custom domain to `ci.gko-project.org`.
   3. Tick "Enforce HTTPS" once the certificate is issued.

   The domain is already verified for the ginkgo-project organisation.

GitHub turns off scheduled workflows after 60 days without commits to the
repository. The page then shows a red banner, because its data is more than
a day old. Re-enable the workflow under Actions.
