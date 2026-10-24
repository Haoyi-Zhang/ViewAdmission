// Extract of do_join_test inputs from Feldera, revision
// ae84fbb9fdb66d1d9e88154ccd9deeac12185007,
// crates/dbsp/src/operator/dynamic/join.rs, lines 2062-2101.
// Copyright 2023-2026 Feldera, Inc.; Copyright 2021-2023 VMware, Inc.
// MIT licensed: see NOTICE-feldera.md. Retained as data; never compiled/run.
    fn do_join_test(workers: usize, transaction: bool, balanced: bool) {
        let mut input1 = vec![
            vec![
                Tup2(Tup2(1, "a".to_string()), 1i64),
                Tup2(Tup2(1, "b".to_string()), 2),
                Tup2(Tup2(2, "c".to_string()), 3),
                Tup2(Tup2(2, "d".to_string()), 4),
                Tup2(Tup2(3, "e".to_string()), 5),
                Tup2(Tup2(3, "f".to_string()), -2),
            ],
            vec![Tup2(Tup2(1, "a".to_string()), 1)],
            vec![Tup2(Tup2(1, "a".to_string()), 1)],
            vec![Tup2(Tup2(4, "n".to_string()), 2)],
            vec![Tup2(Tup2(1, "a".to_string()), 0)],
        ]
        .into_iter();
        let mut input2 = vec![
            vec![
                Tup2(Tup2(2, "g".to_string()), 3i64),
                Tup2(Tup2(2, "h".to_string()), 4),
                Tup2(Tup2(3, "i".to_string()), 5),
                Tup2(Tup2(3, "j".to_string()), -2),
                Tup2(Tup2(4, "k".to_string()), 5),
                Tup2(Tup2(4, "l".to_string()), -2),
            ],
            vec![Tup2(Tup2(1, "b".to_string()), 1)],
            vec![Tup2(Tup2(4, "m".to_string()), 1)],
            vec![],
            vec![],
        ]
        .into_iter();
