# Upstream IVM input provenance

Source: Feldera's `do_join_test`, revision
`ae84fbb9fdb66d1d9e88154ccd9deeac12185007`, accessed 2026-10-24:
[input declarations and join test](https://github.com/feldera/feldera/blob/ae84fbb9fdb66d1d9e88154ccd9deeac12185007/crates/dbsp/src/operator/dynamic/join.rs#L2062-L2101).
The retained Rust excerpt is read as data only. No upstream package or test
binary is installed or executed.

The five paired input batches are retained without changing keys, string
payloads or signed weights. The adapter maps one-letter payloads to zero-based
alphabet indices, retaining keys 1 and 2 only. Keys 3 and 4 are excluded from
the admitted workload because the upstream signed-ZSet regression retains
negative base multiplicities there; the complete upstream stream is separately
checked as an out-of-domain control, never silently made positive. All five
batch boundaries and the zero-weight fifth-batch update are preserved.
The upstream join concatenates payload strings; the supported image retains
the separate integer payload coordinates. On this one-letter vocabulary this
is injective. Even-payload selection and grouped counts are additional owned
views, not claimed as upstream outputs. A source-parser regression binds the
input arrays to the excerpt.

The recovery cuts, an added join-weight residual, absent-summary checker
configuration and publication/reentry schedule are constructed by this project.
This is an upstream IVM regression-input replay through the owned finite model,
not a Feldera checkpoint experiment, observed corruption event or evidence that
Feldera lacks integrity checks. Official context:
[checkpoint and fault-tolerance documentation](https://docs.feldera.com/pipelines/fault-tolerance/),
read 2026-10-24, describes checkpoint restore and input replay, including the
need for fault-tolerant connectors. It motivates a recovery endpoint but does
not establish operational demand for this exact no-synopsis interface.

## License

Upstream open-source code is MIT licensed; enterprise code is separately
licensed. This excerpt is from the open-source DBSP join regression.
[License at the pinned revision](https://github.com/feldera/feldera/blob/ae84fbb9fdb66d1d9e88154ccd9deeac12185007/LICENSE).

Feldera
Copyright 2023-2026 Feldera, Inc.

Database Stream Processor
Copyright 2023 Feldera, Inc.
Copyright 2021-2023 VMware, Inc.

MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
