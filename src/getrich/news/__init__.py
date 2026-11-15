"""News as a causal, historical stream the PI-Net can learn from.

GDELT's timeline API gives, for any query, a daily series of article volume (as a share of all monitored articles) and average
tone, back to 2020 and beyond, in one small request. Both are assigned by GDELT when it ingests an article, so they carry no
hindsight, unlike a language model reading old headlines that already know how the story ended. The same API serves yesterday's
value, so the stream that trains the model is the stream it will run on.
"""
