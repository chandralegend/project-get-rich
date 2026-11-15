# News features versus forward returns (exploratory event study)

GDELT daily features 2020-01-01 to 2026-11-15. 96 tests (feature x symbol x horizon); 3 have a 95% block-bootstrap interval that excludes zero, against about 4.8 expected by chance alone. This is exploratory and not a trading claim; the pre-registered experiment is the confirmatory test.

| feature | symbol | horizon | n | rank IC | 95% interval | excludes 0 |
|---|---|---:|---:|---:|---|---|
| news_etf_vz | ETHUSDT | 20d | 2490 | +0.087 | +0.011 to +0.165 | yes |
| news_inflation_vz | BTCUSDT | 20d | 2490 | -0.084 | -0.149 to -0.012 | yes |
| news_eth_tz | ETHUSDT | 20d | 2490 | +0.073 | -0.001 to +0.146 | no |
| news_inflation_vz | ETHUSDT | 20d | 2490 | -0.068 | -0.139 to +0.002 | no |
| news_inflation_tz | BTCUSDT | 20d | 2490 | -0.058 | -0.137 to +0.025 | no |
| news_btc_vz | ETHUSDT | 20d | 2490 | +0.053 | -0.043 to +0.133 | no |
| news_crypto_vz | BTCUSDT | 20d | 2490 | -0.051 | -0.131 to +0.023 | no |
| news_inflation_vz | BTCUSDT | 5d | 2505 | -0.051 | -0.105 to +0.003 | no |
| news_hack_tz | BTCUSDT | 20d | 2490 | -0.050 | -0.116 to +0.005 | no |
| news_eth_vz | ETHUSDT | 20d | 2490 | +0.050 | -0.043 to +0.134 | no |
| news_crypto_tz | BTCUSDT | 20d | 2490 | -0.049 | -0.121 to +0.017 | no |
| news_eth_tz | BTCUSDT | 20d | 2490 | +0.048 | -0.023 to +0.109 | no |
| news_crypto_vz | BTCUSDT | 5d | 2505 | -0.046 | -0.106 to +0.000 | no |
| news_btc_tz | BTCUSDT | 20d | 2490 | -0.045 | -0.114 to +0.022 | no |
| news_regulation_vz | ETHUSDT | 20d | 2490 | +0.045 | -0.026 to +0.108 | no |
| news_eth_vz | ETHUSDT | 1d | 2509 | +0.044 | +0.012 to +0.080 | yes |
| news_inflation_vz | ETHUSDT | 5d | 2505 | -0.042 | -0.095 to +0.006 | no |
| news_etf_vz | BTCUSDT | 20d | 2490 | +0.042 | -0.030 to +0.105 | no |
| news_inflation_tz | BTCUSDT | 5d | 2505 | -0.042 | -0.097 to +0.017 | no |
| news_regulation_tz | BTCUSDT | 20d | 2490 | -0.038 | -0.103 to +0.028 | no |
| news_fed_vz | BTCUSDT | 20d | 2490 | -0.036 | -0.086 to +0.020 | no |
| news_etf_vz | ETHUSDT | 1d | 2509 | +0.035 | -0.006 to +0.076 | no |
| news_hack_vz | ETHUSDT | 5d | 2505 | -0.034 | -0.086 to +0.015 | no |
| news_hack_tz | ETHUSDT | 5d | 2505 | +0.033 | -0.017 to +0.079 | no |
| news_btc_vz | ETHUSDT | 1d | 2509 | +0.033 | -0.000 to +0.067 | no |

Top 25 by absolute IC shown; the full set is what the count above is taken over.
