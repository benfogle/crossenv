# Changelog

## [1.4.0] - 2022-12-11

### Added
- Support for Python 3.11

## [1.3.0] - 2022-06-14

### Added
- Support for setuptools >= 61 (#94)
- Support for Pypy (#95)

### Fixed
- Fixed typo in `mac_ver` (#91)
- `sysconfig.get_platform()` for ppc64le (#92)

## [1.2.0] - 2022-01-04

### Added
- Some support for pypy (#82, #85)
- Crossenv will optimistically continue if it cannot query the compiler. (QNX,
  etc.)

## [1.1.4] - 2021-08-27

### Added
- `--machine` argument to fine-tune apparent value of `os.uname().machine`

### Fixed
- Fixed build failure when pip runs from a zip file.
- Fixed CI build due to master -> main branch switch in CPython.

## [1.1.3]- 2021-08-21

### Fixed
- Correctly set up crossenv environment with Python 3.10

## [1.1.2]- 2021-04-03

### Fixed
- Correctly handle the case where host-python was natively built on another
  architecture.
- Get uname machine info from `HOST_GNU_TYPE` instead of the platform name. The
  latter usually uses a generic name that can cause trouble when naming wheels.

## [1.1.1] - 2021-03-28

### Added
- `--manylinux` option to opt-in to manylinux wheels, for those that actually
  wanted them.

### Fixed
- Pip shebang line was broken due to incorrectly importing site module.
- `LIBRARY_PATH` and `CPATH` environment variable can be overriden.

## [1.1.0] - 2021-03-14

### Added
- A changelog :)
- Documented the crossenv environment.
- Tests can be run in parallel using pytest-xdist.
- Test improvments: run tests where build-python == host-python, as a null
  test/corner case.
- Test improvments: Code coverage is collected as part of testing.
- Weekly tests against CPython master branch.

### Changed
- Reworked site.py and patching. Makes the code more maintainable, and fixes a
  couple of long outstanding issues.

### Fixed
- Fix machine for ppc64le.
- Many test fixes.
- Fixed an issue where shebang lines in generated scripts could exceed the
  maximum allowed in Linux.
- Disable manylinux tagging, now that it has started to appear for arm
  architectures.

[1.1.0]: https://github.com/benfogle/crossenv/compare/v1.0...v1.1.0
