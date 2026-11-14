"""Pretrained time-series forecasters (Kronos, Chronos-2, TimesFM 2.5, TinyTimeMixer) as a causal, cached, evaluated feature channel.

Rules that apply to everything here:
  * every forecast at origin day t sees only bars up to and including t (generation slices the history; tests prove it);
  * forecasts are walk-forward and cached, so a feature is never recomputed with newer data than it had at the time;
  * a model is judged on forecast skill against a random walk and a volatility benchmark BEFORE it is allowed into any
    trading model, on origins after its public release date (it cannot have seen later data) as well as on all of history,
    where any contamination would only inflate its skill;
  * models run in their own subprocess and environment (dependency pins, and third-party code stays away from the database).
"""
