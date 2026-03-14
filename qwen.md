# Qwen Development Guide

This guide provides essential information for working with Qwen models in the GeoVision Lab project.

## Qwen Model Overview

We use the Qwen 2.5 series (tagged as `qwen3.5` in our environment for internal versioning logic) to provide high-quality reasoning and analysis capabilities.

### Model Roles

| Role | Model Name | Description |
| :--- | :--- | :--- |
| **Main LLM** | `qwen3.5:4b` | Handling general application requests and transformations. |
| **Reasoning LLM** | `qwen3.5:4b` | Dedicated to complex reasoning tasks. Switchable to `9b` or `0.8b`. |
| **Reviewer LLM** | `qwen3.5:0.8b` | Efficient model used for QA and validation steps. |

### Available Reasoning Models
- `qwen3.5:9b`: Highest quality, requires more VRAM.
- `qwen3.5:4b`: Balanced performance and speed (Default).
- `qwen3.5:0.8b`: Lightest version, useful for low-resource environments.

---

## Docker Operations

The project relies on Docker to manage the model lifecycle via Ollama.

### Basic Commands

- **Start all services:**
  ```bash
  docker compose up -d
  ```

- **View service logs (including Ollama model loading):**
  ```bash
  docker compose logs -f ollama
  ```

- **Check loaded models in Ollama:**
  ```bash
  docker exec -it geovision-ollama ollama list
  ```

- **Pull models manually (if not pulled by compose):**
  ```bash
  docker exec -it geovision-ollama ollama pull qwen3.5:4b
  ```

---

## Testing with Docker

To ensure the models are integrating correctly with the application logic, run the test suite within the application container.

### Run All Tests
```bash
docker exec geovision-app pytest
```

### Run Specific Test File
```bash
docker exec geovision-app pytest tests/test_rag.py
```

### Run with Coverage
```bash
docker exec geovision-app pytest --cov=app tests/
```

---

## Development Tips

1. **Model Switching**: You can change the reasoning model at runtime using the `set_reasoning_model` method in `app/core/config.py` or by updating the `REASONING_LLM_MODEL_NAME` environment variable.
2. **GPU Acceleration**: Ensure you have the `nvidia-container-toolkit` installed if you want to use GPU acceleration with the `ollama` service. Check the `deploy` section in `docker-compose.yml`.
3. **Resource Monitoring**: Use **Dozzle** at [http://localhost:9999](http://localhost:9999) to monitor container logs and resource usage (CPU/Memory) when models are running.
