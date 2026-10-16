"""A small Ginkgo source tree with the CI files the extractor reads. It copies
the patterns of the real files: templates in included files, cmake lines with
-D flags, MODULE_LOAD, HoreKa's EXTRA_CMAKE_FLAGS and CSCS's remote templates."""

from pathlib import Path

GITLAB_CI = """
include:
  - local: '.gitlab/variables.yml'
  - local: '.gitlab/rules.yml'
  - local: '.gitlab/horeka.yml'

stages:
  - sync
  - build
  - code_quality

.build_and_test_template:
  stage: build
  script:
    - cmake .. -DCMAKE_BUILD_TYPE=${BUILD_TYPE} -DBUILD_SHARED_LIBS=${BUILD_SHARED_LIBS}
        ${EXTRA_CMAKE_FLAGS} -DGINKGO_BUILD_OMP=${BUILD_OMP} -DGINKGO_BUILD_CUDA=${BUILD_CUDA}
        -DGINKGO_BUILD_MPI=${BUILD_MPI} -DGINKGO_MIXED_PRECISION=${MIXED_PRECISION}
    - ninja install
    - bash ${CI_PROJECT_DIR}/.gitlab/run-ctest.sh

.build_template:
  stage: build
  script:
    - cmake .. -DCMAKE_BUILD_TYPE=${BUILD_TYPE} -DGINKGO_BUILD_OMP=${BUILD_OMP}
    - ninja install

.use_tum-nvidia:
  image: rocky_tum
  tags:
    - nvidia-gpus
    - tum

.use_gko-nocuda-nompi-gnu9-llvm8:
  image: ginkgohub/cpu:openmpi-gnu9-llvm8
  tags:
    - cpu
    - tum

sync:
  stage: sync
  tags:
    - status-jobs
  script:
    - git push
  only:
    - develop

build/cuda120/openmpi/gcc/cuda/release/static:
  extends:
    - .build_and_test_template
    - .default_variables
    - .full_test_condition
    - .use_tum-nvidia
  variables:
    BUILD_CUDA: "ON"
    BUILD_MPI: "ON"
    BUILD_SHARED_LIBS: "OFF"
    BUILD_TYPE: "Release"
    MODULE_LOAD: "cmake/3.18.6 cuda/12.0.1 gcc/12.4.0 openmpi/4.1.8"

build/cuda124/mpich/gcc/cuda/release/shared:
  extends: [.build_and_test_template, .default_variables, .full_test_condition, .use_tum-nvidia]
  variables:
    BUILD_CUDA: "ON"
    BUILD_MPI: "ON"
    BUILD_TYPE: "Release"
    MODULE_LOAD: "cmake/3.30.8 cuda/12.6.3 gcc/13.3.0 mpich"

build/nocuda/openmpi/clang/omp/debug/shared:
  extends: [.build_template, .default_variables, .quick_test_condition, .use_gko-nocuda-nompi-gnu9-llvm8]
  variables:
    CXX_COMPILER: "clang++"
    BUILD_OMP: "ON"

build/dpcpp/gpu/release/shared:
  extends: [.build_and_test_template, .default_variables, .disable_job_condition, .use_gko-nocuda-nompi-gnu9-llvm8]

clang-tidy:
  stage: code_quality
  extends: [.build_template, .default_variables, .full_test_condition, .use_gko-nocuda-nompi-gnu9-llvm8]

broken:
  extends: [.build_and_test_template, .default_variables, .full_test_condition, .use_missing-template]
  tags: [no-such-tag]
"""

VARIABLES = """
.default_variables:
  variables:
    CXX_COMPILER: "g++"
    BUILD_TYPE: "Debug"
    BUILD_SHARED_LIBS: "ON"
    BUILD_OMP: "OFF"
    BUILD_CUDA: "OFF"
    BUILD_MPI: "OFF"
    MIXED_PRECISION: "ON"
    EXTRA_CMAKE_FLAGS: ""
"""

RULES = """
.full_test_condition:
  rules:
    - if: $RUN_CI_TAG
.quick_test_condition:
  rules:
    - if: $RUN_CI_TAG
.disable_job_condition:
  rules:
    - when: never
"""

HOREKA = """
.horeka_build_and_test:
  stage: build
  tags:
    - horeka
  variables:
    MODULES: "compiler/gnu/13 devel/cuda/12.4 devel/cmake/3.30"
    BUILD_TYPE: Release
    EXTRA_CMAKE_FLAGS: ""
  script:
    - bash .gitlab/sbatch-wait.sh --nodes=1 .gitlab/build-and-test.sh
  rules:
    - if: $RUN_CI_TAG
      when: manual

horeka/a100/cuda124/nompi/gcc/nondefault-stream/release/shared-reduced:
  extends: .horeka_build_and_test
  variables:
    EXTRA_CMAKE_FLAGS: -DGINKGO_BUILD_CUDA=ON -DGINKGO_BUILD_MPI=OFF
      -DGINKGO_TEST_NONDEFAULT_STREAM=ON -DGINKGO_BUILD_OMP=OFF
"""

CSCS = """
include:
  - remote: 'https://gitlab.com/cscs-ci/recipes/-/raw/master/templates/v2/.ci-ext.yml'

stages:
  - test

variables:
  UENV: prgenv-gnu/25.11:v1

.daint_build_and_test:
  extends: .baremetal-runner-daint-gh200
  stage: test
  variables:
    CXX: g++
    BUILD_TYPE: Release
    EXTRA_CMAKE_FLAGS: ""
  script:
    - uenv run ${UENV} -- cmake -S . -B build -DCMAKE_BUILD_TYPE=${BUILD_TYPE}
        -DGINKGO_BUILD_CUDA=ON -DGINKGO_BUILD_OMP=ON ${EXTRA_CMAKE_FLAGS}
    - uenv run ${UENV} -- bash ../.gitlab/run-ctest.sh

.daint_mpi:
  variables:
    MPI_CMAKE_FLAGS: -DGINKGO_BUILD_MPI=ON

daint/cuda129/cray-mpich/gcc/omp/release/static:
  extends: [.daint_build_and_test, .daint_mpi]
  variables:
    EXTRA_CMAKE_FLAGS: -DBUILD_SHARED_LIBS=OFF ${MPI_CMAKE_FLAGS}
"""

CI = """
name: CI
on:
  push:
    branches: [develop]
jobs:
  arm:
    if: &run >-
      ${{ !contains(github.event.pull_request.labels.*.name, '1:ST:SKIP_ALL_CI') }}
    uses: ./.github/workflows/arm.yml
    with: &with
      full: false
  windows-msvc:
    if: *run
    uses: ./.github/workflows/windows-msvc.yml
    with: *with
  linux-gcc-cuda:
    uses: ./.github/workflows/linux-gcc-cuda.yml
  clang-tidy:
    if: >-
      ${{ github.event_name == 'pull_request' && !contains(github.event.pull_request.labels.*.name, '1:ST:SKIP_ALL_CI') }}
    uses: ./.github/workflows/clang-tidy.yml
  coverage:
    if: ${{ github.event_name != 'pull_request' }}
    uses: ./.github/workflows/coverage.yml
"""

# configures for the compilation database only, and runs on pull requests only
CLANG_TIDY = """
on:
  workflow_call:
jobs:
  clang-tidy:
    name: clang-tidy on changed lines
    runs-on: [ubuntu-24.04]
    steps:
      - run: sudo apt-get install -y ninja-build clang-tidy-18
      - run: cmake -S . -B build -G Ninja -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DGINKGO_BUILD_TESTS=OFF
      - run: git diff -U0 HEAD^1 HEAD | clang-tidy-diff-18.py -p1 -path build
"""

# CI runs it on pushes only, CI-Extra on pull requests
COVERAGE = """
on:
  workflow_call:
jobs:
  coverage:
    name: coverage of the reference, OpenMP and MPI code
    runs-on: [ubuntu-24.04]
    steps:
      - run: cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Debug -DGINKGO_BUILD_OMP=ON -DGINKGO_BUILD_MPI=ON
      - run: cmake --build build -j4
      - run: ctest --test-dir build -j4
"""

CI_EXTRA = """
name: CI-Extra
on:
  pull_request:
jobs:
  arm:
    uses: ./.github/workflows/arm.yml
    with:
      full: true
  windows-msvc:
    uses: ./.github/workflows/windows-msvc.yml
    with:
      full: true
  coverage:
    uses: ./.github/workflows/coverage.yml
"""

ARM = """
on:
  workflow_call:
    inputs:
      full:
        type: boolean
jobs:
  arm-omp:
    if: ${{ !inputs.full }}
    strategy:
      matrix:
        config:
          - {shared: "ON", build_type: "Release", name: "arm/omp/release/shared-16bit", mixed: "ON", half: "ON", bfloat16: "ON"}
    name: ${{ matrix.config.name }}
    runs-on: [ubuntu-24.04-arm]
    steps:
      - uses: actions/checkout@v4
      - name: build and test
        run: |
          mkdir build && cd build
          cmake .. -DBUILD_SHARED_LIBS=${{ matrix.config.shared }} -DCMAKE_BUILD_TYPE=${{ matrix.config.build_type }} -DGINKGO_MIXED_PRECISION=${{ matrix.config.mixed }} -DGINKGO_ENABLE_HALF=${{ matrix.config.half }} -DGINKGO_ENABLE_BFLOAT16=${{ matrix.config.bfloat16 }}
          make -j4
          ctest --output-on-failure
  arm-omp-full:
    if: inputs.full
    strategy:
      matrix:
        config:
          - {shared: "OFF", build_type: "Release", name: "arm/omp/release/static", mixed: "ON", half: "ON", bfloat16: "OFF"}
    name: ${{ matrix.config.name }}
    runs-on: [ubuntu-24.04-arm]
    steps:
      - run: |
          cmake .. -DBUILD_SHARED_LIBS=${{ matrix.config.shared }} -DCMAKE_BUILD_TYPE=${{ matrix.config.build_type }}
          ctest
"""

WINDOWS = """
on:
  workflow_call:
    inputs:
      full:
        type: boolean
jobs:
  windows:
    strategy:
      matrix:
        os: ${{ fromJSON(inputs.full && '["windows-2022", "windows-latest"]' || '["windows-latest"]') }}
    name: msvc/${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    steps:
      - run: |
          cmake -DGINKGO_BUILD_OMP=OFF -DGINKGO_ENABLE_HALF=OFF -DGINKGO_ENABLE_BFLOAT16=OFF ..
          cmake --build . --config Release
          ctest -C Release
"""

LINUX_CUDA = """
on:
  workflow_call:
jobs:
  linux_cuda:
    strategy:
      matrix:
        config:
          - {version: "13.3.1", name: "cuda-13.3/release/shared", arch: "80"}
    name: gcc/${{ matrix.config.name }} (only compile)
    runs-on: [ubuntu-24.04]
    steps:
      - run: |
          docker run nvidia/cuda:${{ matrix.config.version }}-devel-ubuntu24.04 bash -c "cmake .. -DGINKGO_BUILD_CUDA=ON -DGINKGO_CUDA_ARCHITECTURES=${{ matrix.config.arch }} -DGINKGO_BUILD_OMP=ON -DCMAKE_BUILD_TYPE=Release && make"
"""

# like the real files: mirror-develop.yml mirrors the other branches, and
# mirror-major.yml develop; both produce the check run "mirror / to_gitlab"
MIRROR_DEVELOP = """
on:
  push:
    branches-ignore: [develop]
jobs:
  mirror:
    uses: ./.github/workflows/mirror.yml
"""

MIRROR_MAJOR = """
on:
  push:
    branches: [develop]
jobs:
  mirror:
    uses: ./.github/workflows/mirror.yml
"""

MIRROR = """
on:
  workflow_call:
jobs:
  to_gitlab:
    runs-on: ubuntu-latest
    steps:
      - run: git push
"""

FORMATTING = """
on: pull_request
jobs:
  formatting:
    name: check-format
    runs-on: ubuntu-latest
    steps:
      - run: pre-commit run
"""

FILES = {
    ".gitlab-ci.yml": GITLAB_CI,
    ".gitlab/variables.yml": VARIABLES,
    ".gitlab/rules.yml": RULES,
    ".gitlab/horeka.yml": HOREKA,
    ".gitlab/cscs.yml": CSCS,
    ".github/workflows/ci.yml": CI,
    ".github/workflows/ci-extra.yml": CI_EXTRA,
    ".github/workflows/arm.yml": ARM,
    ".github/workflows/windows-msvc.yml": WINDOWS,
    ".github/workflows/linux-gcc-cuda.yml": LINUX_CUDA,
    ".github/workflows/clang-tidy.yml": CLANG_TIDY,
    ".github/workflows/coverage.yml": COVERAGE,
    ".github/workflows/mirror-develop.yml": MIRROR_DEVELOP,
    ".github/workflows/mirror-major.yml": MIRROR_MAJOR,
    ".github/workflows/mirror.yml": MIRROR,
    ".github/workflows/check-formatting.yml": FORMATTING,
}


def write(root: Path, files: dict[str, str] = FILES) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root
