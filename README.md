# 森林烟火二次识别 Flask API

该项目提供森林烟火图像的二次识别 API 服务：接收 1~2 张图像、过滤热成像图片、调度阿里云通义（DashScope）大模型进行烟火风险识别，并返回分析结果及带标注的图像（Base64 编码）。

## 环境要求

- Python 3.10+
- Linux / macOS（推荐使用 Gunicorn 部署）或 Windows（推荐使用 Waitress 部署）
- 可联网访问阿里云 DashScope API 的网络环境

## 安装步骤

1. **克隆仓库并进入目录**
   ```bash
   git clone <your-repo-url>
   cd project
   ```

2. **创建虚拟环境并激活**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置阿里云 DashScope API Key**
   - 建议在环境变量中设置：
     ```bash
     export DASHSCOPE_API_KEY="your_api_key"
     export DASHSCOPE_MODEL="qwen-vl-max"  # 可选，默认 qwen-vl-max
     ```
   - 或复制 `config.example.py` 为 `config.py` 并填写 `CONFIG` 字典，`python app.py` 会自动加载该文件。

## 启动方式

### 开发模式（Flask 内置服务器）
```bash
python app.py --host 0.0.0.0 --port 6000 --debug
```
常用参数：
- `--host`：监听地址，默认 `0.0.0.0`
- `--port`：端口，默认 `6000`
- `--debug`：开启调试模式（仅限开发环境）

### 生产模式（推荐）

#### Linux / macOS — Gunicorn + gevent
```bash
./start.sh
```
或手动执行：
```bash
gunicorn -w 4 -k gevent --worker-connections 1000 \
  --bind 0.0.0.0:6000 --timeout 180 \
  --access-logfile logs/access.log \
  --error-logfile logs/error.log \
  app:app
```
- 建议 worker 数量：`2 * CPU 核心数 + 1`
- `--worker-connections` 控制每个 gevent worker 的并发连接数

#### Windows — Waitress
```batch
start.bat
```
或手动执行：
```batch
waitress-serve --host=0.0.0.0 --port=6000 --threads=8 app:app
```
- 根据硬件环境调整 `--threads` 数量

## API 文档

- **URL**：`POST /ai_enhanced_fire_detect`
- **请求格式**：`multipart/form-data`
  - 字段 `images`：1~2 张图像（JPEG/PNG/WebP）
- **响应格式**：`application/json`

### 响应示例
```json
{
  "status": "success",
  "request_id": "f3b0c620c9a548f0a8296eb8a7a71513",
  "results": [
    {
      "filename": "sample.jpg",
      "width": 1920,
      "height": 1080,
      "fire_detected": true,
      "confidence": 0.82,
      "analysis_summary": "Detected smoke rising from the treeline...",
      "local_fire_probability": 0.67,
      "is_thermal": false,
      "dashscope_model": "qwen-vl-max",
      "latency_ms": 865.24,
      "source": "dashscope",
      "raw_response": {"choices": [...]} 
    }
  ],
  "annotated_images": [
    {
      "filename": "sample.jpg",
      "image_base64": "...base64 data..."
    }
  ],
  "duration_ms": 1021.87
}
```

### cURL 示例
```bash
curl -X POST http://localhost:6000/ai_enhanced_fire_detect \
  -F "images=@samples/fire_1.jpg" \
  -F "images=@samples/fire_2.jpg"
```

### Python 示例
```python
import requests

files = [
    ("images", ("fire.jpg", open("fire.jpg", "rb"), "image/jpeg")),
]
response = requests.post("http://localhost:6000/ai_enhanced_fire_detect", files=files, timeout=180)
print(response.json())
```

## 配置说明

| 配置项 | 方式 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `DASHSCOPE_API_KEY` | 环境变量 | 无 | 必填，阿里云通义 API Key |
| `DASHSCOPE_MODEL` | 环境变量 / config.py | `qwen-vl-max` | 大模型名称 |
| `DASHSCOPE_ENDPOINT` | 环境变量 / config.py | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` | API 端点 |
| `MAX_CONTENT_LENGTH` | 环境变量 / config.py | `10485760` | 上传文件大小限制（字节） |
| `ALLOWED_MIME_TYPES` | 环境变量 / config.py | `image/jpeg,image/png,image/jpg,image/webp` | 允许的图片类型 |
| `HTTP_POOL_CONNECTIONS` | 环境变量 / config.py | `10` | HTTP 连接池大小 |
| `HTTP_POOL_MAXSIZE` | 环境变量 / config.py | `20` | HTTP 最大连接数 |
| `HTTP_MAX_RETRIES` | 环境变量 / config.py | `3` | API 请求重试次数 |
| `HTTP_BACKOFF_FACTOR` | 环境变量 / config.py | `1.0` | 重试指数退避系数 |
| `LOG_DIR` / `LOG_FILE` | 环境变量 / config.py | `logs` / `app.log` | 异步日志目录与文件 |

> 复制 `config.example.py` 为 `config.py` 并修改 `CONFIG` 字典可快速覆盖上述默认值。

## 测试方法

1. **健康检查**
   ```bash
   curl http://localhost:6000/health
   ```

2. **功能测试脚本**
   ```bash
   python test_client.py samples/fire_1.jpg --pretty
   ```

## 故障排查

| 问题 | 可能原因 | 解决方案 |
| --- | --- | --- |
| 返回 `invalid_request` | 参数或文件不符合要求 | 确认 `images` 字段传入 1~2 张支持的图片 |
| 返回 `external_service_error` | 通义 API 网络异常、Key 无效 | 检查 API Key、网络及 DashScope 额度 |
| 超时 (`504`/`timeout`) | 图片过大或模型响应慢 | 增大 `DASHSCOPE_READ_TIMEOUT`，或优化并发配置 |
| 日志为空 | 未创建日志目录 | 确保 `LOG_DIR` 存在或使用 `start.sh`/`start.bat` 预先创建 |

## 性能调优建议

- 根据 CPU 核数设置 `gunicorn` worker：`workers = 2 * CPU + 1`
- 使用 `-k gevent` 或 `--threads` 提升单 worker 并发能力
- 调整 `HTTP_POOL_MAXSIZE` 与 `DASHSCOPE_READ_TIMEOUT`，匹配模型响应时间
- 可使用 `ab`/`wrk` 进行压测，例如：
  ```bash
  ab -n 100 -c 5 -p payload.txt -T 'multipart/form-data' http://localhost:6000/ai_enhanced_fire_detect
  ```
- 监控 `logs/` 下的 access / error 日志，结合异步队列日志快速定位问题

## 日志系统说明

- 使用 `logging.handlers.QueueHandler` + `QueueListener` 实现异步日志
- 默认输出到控制台与 `logs/app.log`（10MB 轮转，保留 5 个备份）
- 请求开始、图像判定、模型调用、异常堆栈及请求耗时均已记录

## 目录结构

```
├── app.py                # Flask 入口，加载配置、启动应用
├── forest_fire_api
│   ├── __init__.py       # Application factory & 全局初始化
│   ├── config.py         # 配置加载与 Settings 数据类
│   ├── dashscope_client.py # DashScope API 封装 & 重试逻辑
│   ├── http_client.py    # requests.Session 全局连接池
│   ├── image_processing.py # 图像预处理、热成像过滤、标注
│   ├── logging_utils.py  # 异步日志配置
│   └── routes.py         # API 蓝图与主业务逻辑
├── requirements.txt
├── start.sh / start.bat  # 生产启动示例脚本
├── test_client.py        # 功能测试脚本
└── config.example.py     # 配置示例
```
