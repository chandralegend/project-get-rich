# syntax=docker/dockerfile:1
# SPIKE: can the three foundation forecasters (and later LightGBM for the PI-Net) run inside Docker on Linux arm64, CPU only?
# Versions are the ones the host runs resolved (chronos-forecasting 2.3.2, timesfm 3.0.2 which includes the 2.5 class). One environment first;
# if the pins conflict, split it into one environment per worker, as forecast/runner.py does on the host.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy VIRTUAL_ENV=/opt/env PATH=/opt/env/bin:$PATH \
    HF_HOME=/hf HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# LightGBM needs the OpenMP runtime, which the slim base image does not have.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
# CPU-only torch from PyTorch's own index: the default PyPI wheel on arm64 carries the CUDA libraries and made the image 18.8 GB.
RUN uv venv /opt/env --python 3.13 \
 && uv pip install --python /opt/env/bin/python --index-url https://download.pytorch.org/whl/cpu torch \
 && uv pip install --python /opt/env/bin/python numpy pandas einops huggingface_hub safetensors tqdm \
        "chronos-forecasting==2.3.2" "timesfm[torch]==3.0.2" lightgbm duckdb pytz
RUN python -c "import torch, chronos, timesfm, lightgbm; print('torch', torch.__version__, 'lightgbm', lightgbm.__version__)" \
 && pip list 2>/dev/null | head -0 ; uv pip list --python /opt/env/bin/python | grep -iE "^(torch|numpy|pandas|chronos|timesfm|lightgbm|transformers|einops|huggingface)" 
