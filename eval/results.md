Threshold 0.5, lock after 3 suspicious windows of 10 s.

| data | model | users | genuine_windows | impostor_windows | FAR@thr | FRR@thr | EER | detect_rate | mean_delay_s | owner_sessions_falsely_locked |
|---|---|---|---|---|---|---|---|---|---|---|
| keys | iforest | 2 | 13 | 130 | 0.192 | 0.692 | 0.319 | 0.778 | 37.143 | 1 |
| keys | ocsvm | 2 | 13 | 130 | 0.154 | 0.769 | 0.369 | 1.000 | 45.556 | 2 |
| keys | lof | 2 | 13 | 130 | 0.131 | 0.769 | 0.431 | 0.889 | 40.000 | 2 |
| mouse | iforest | 2 | 4 | 75 | 0.813 | 0.500 | 0.530 | 0.111 | 30.000 | 0 |
| mouse | ocsvm | 2 | 4 | 75 | 0.773 | 0.500 | 0.728 | 0.222 | 60.000 | 0 |
| mouse | lof | 2 | 4 | 75 | 0.973 | 0.000 | 0.543 | 0.000 | nan | 0 |
| both | iforest | 2 | 16 | 195 | 0.415 | 0.688 | 0.488 | 0.778 | 38.571 | 1 |
| both | ocsvm | 2 | 16 | 195 | 0.385 | 0.750 | 0.499 | 1.000 | 48.889 | 2 |
| both | lof | 2 | 16 | 195 | 0.426 | 0.625 | 0.499 | 0.889 | 42.500 | 2 |
