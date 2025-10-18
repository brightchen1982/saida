@echo off
setlocal enabledelayedexpansion

set DASHSCOPE_API_KEY=your_api_key_here
set DASHSCOPE_MODEL=qwen-vl-max

if not exist logs (
    mkdir logs
)

waitress-serve --host=0.0.0.0 --port=6000 --threads=8 app:app
