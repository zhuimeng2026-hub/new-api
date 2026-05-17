#!/usr/bin/env python3
"""
对比 volcengine 与 xiaomimimo 接口响应，重点对比 usage/token 消耗字段。
将原始响应 dump 为 JSON，方便排查提供商是否返回了真实的 token 消耗量。

配置方式:
    在项目根目录的 .env 文件中写入以下变量（变量名大小写不敏感）:

    volcengine_url=https://ark.cn-beijing.volces.com/api/v3/chat/completions
    volcengine_key=sk-xxxx
    mimo_url=https://api.xiaomimimo.com/v1/chat/completions
    mimi_key=sk-yyyy
    model_name=doubao-1-5-pro-32k-250115

    如果 model_name 包含多个模型（如 kimi-k2.6;glm-5.1），脚本会取第一个。

用法示例:
    # 非流式对比（所有参数从 .env 读取）
    python3 compare_volcengine_mimo.py

    # 流式对比
    python3 compare_volcengine_mimo.py --stream

    # 覆盖部分参数
    python3 compare_volcengine_mimo.py --stream --model glm-5.1 --prompt "你好"
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

import requests


def load_env(dotenv_path: str = ".env") -> Dict[str, str]:
    """手动解析 .env 文件并注入 os.environ，返回解析后的字典。"""
    env: Dict[str, str] = {}
    if not os.path.exists(dotenv_path):
        return env
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            env[key] = value
            if key not in os.environ:
                os.environ[key] = value
    return env


def get_env(keys: list, env_dict: Dict[str, str]) -> Optional[str]:
    """按优先级从 os.environ 和 .env 字典中取值。"""
    for k in keys:
        v = os.environ.get(k)
        if v:
            return v
        v = env_dict.get(k)
        if v:
            return v
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对比 volcengine 与 mimo 接口响应及 usage 信息")
    parser.add_argument("--stream", action="store_true", help="是否使用流式请求 (SSE)")
    parser.add_argument("--model", default=None, help="模型名称 (默认从 .env 的 MODEL_NAME 读取)")
    parser.add_argument("--prompt", default="你好，请简单介绍一下自己", help="用户输入 prompt (默认: 你好，请简单介绍一下自己)")
    parser.add_argument("--max-tokens", type=int, default=256, help="max_tokens (默认: 256)")
    parser.add_argument("--temperature", type=float, default=0.7, help="temperature (默认: 0.7)")
    parser.add_argument("--output-dir", default=".", help="JSON 输出目录 (默认: 当前目录)")
    return parser.parse_args()


def build_payload(model: str, prompt: str, max_tokens: int, temperature: float, stream: bool) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}
    return payload


def call_api(name: str, url: str, api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """调用单个 API，返回包含原始响应、耗时、提取到的 usage 等信息的字典。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    result = {
        "provider": name,
        "url": url,
        "request": payload,
        "request_headers": {k: (v[:8] + "..." if k.lower() == "authorization" else v) for k, v in headers.items()},
        "success": False,
        "status_code": None,
        "latency_ms": None,
        "raw_response": None,
        "extracted_usage": None,
        "extracted_content": None,
        "error": None,
    }

    try:
        start = time.time()
        resp = requests.post(url, headers=headers, json=payload, timeout=120, stream=payload.get("stream", False))
        latency_ms = int((time.time() - start) * 1000)
        result["latency_ms"] = latency_ms
        result["status_code"] = resp.status_code

        if payload.get("stream"):
            chunks = []
            content_parts = []
            usage_chunk = None
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    chunks.append(chunk)
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            content_parts.append(delta["content"])
                    if chunk.get("usage"):
                        usage_chunk = chunk["usage"]
            result["raw_response"] = chunks
            result["extracted_content"] = "".join(content_parts)
            result["extracted_usage"] = usage_chunk
        else:
            try:
                data = resp.json()
            except Exception:
                data = {"_non_json_body": resp.text}
            result["raw_response"] = data
            result["extracted_content"] = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            result["extracted_usage"] = data.get("usage")

        if resp.status_code == 200:
            result["success"] = True
        else:
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:500]}"

    except Exception as e:
        result["error"] = str(e)

    return result


def extract_usage_fields(usage: Any) -> Dict[str, Any]:
    """尽可能多地提取 usage 中的字段。"""
    if usage is None:
        return {"_present": False}
    if not isinstance(usage, dict):
        return {"_present": True, "_raw": usage}

    fields = {"_present": True}
    for key in [
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    ]:
        fields[key] = usage.get(key)

    for detail_key in ["prompt_tokens_details", "completion_tokens_details", "input_tokens_details"]:
        if detail_key in usage and isinstance(usage[detail_key], dict):
            fields[detail_key] = usage[detail_key]

    return fields


def print_comparison(volc_result: Dict[str, Any], mimo_result: Dict[str, Any]) -> None:
    print("\n" + "=" * 70)
    print("对比结果")
    print("=" * 70)

    for r in (volc_result, mimo_result):
        name = r["provider"]
        ok = "成功" if r["success"] else "失败"
        print(f"\n[{name}] {ok} | HTTP {r['status_code']} | 耗时 {r['latency_ms']} ms")
        if r["error"]:
            print(f"  错误: {r['error']}")
            continue

        usage = extract_usage_fields(r["extracted_usage"])
        print(f"  内容摘要: {r['extracted_content'][:120]!r}...")
        print(f"  usage 返回情况:")
        if not usage.get("_present"):
            print(f"    警告: 响应中 **没有** usage 字段 (提供商未返回 token 消耗)")
        else:
            for k, v in usage.items():
                if k.startswith("_"):
                    continue
                if v is not None:
                    print(f"    [OK] {k}: {v}")
                else:
                    print(f"    [MISSING] {k}: 未返回")

    print("\n" + "-" * 70)
    print("核心 usage 字段对比")
    print("-" * 70)
    core_keys = ["prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"]
    volc_usage = extract_usage_fields(volc_result.get("extracted_usage"))
    mimo_usage = extract_usage_fields(mimo_result.get("extracted_usage"))
    print(f"{'字段':<25} {'Volcengine':<20} {'Mimo':<20}")
    for k in core_keys:
        v1 = volc_usage.get(k)
        v2 = mimo_usage.get(k)
        s1 = str(v1) if v1 is not None else "N/A"
        s2 = str(v2) if v2 is not None else "N/A"
        print(f"{k:<25} {s1:<20} {s2:<20}")
    print("-" * 70)


def save_results(output_dir: str, volc_result: Dict[str, Any], mimo_result: Dict[str, Any]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"compare_volcengine_mimo_{timestamp}.json")

    payload = {
        "meta": {
            "created_at": timestamp,
            "description": "对比 volcengine 与 mimo 接口原始响应及 usage 信息",
        },
        "results": [volc_result, mimo_result],
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return filename


def main() -> int:
    args = parse_args()
    env = load_env()

    # 从 .env / 环境变量读取配置（支持大小写混写）
    volc_url = get_env(["VOLCENGINE_URL", "volcengine_url"], env)
    volc_key = get_env(["VOLCENGINE_KEY", "volcengine_key"], env)
    mimo_url = get_env(["MIMO_URL", "mimo_url"], env)
    # mimo key 在 .env 中可能叫 mimi_key，做兼容
    mimo_key = get_env(["MIMO_KEY", "mimo_key", "MIMI_KEY", "mimi_key"], env)

    model = args.model
    if not model:
        model_env = get_env(["MODEL_NAME", "model_name"], env)
        if model_env:
            model = model_env.split(";")[0].strip()
        else:
            model = ""

    # 校验必填
    missing = []
    if not volc_url:
        missing.append("VOLCENGINE_URL / volcengine_url")
    if not volc_key:
        missing.append("VOLCENGINE_KEY / volcengine_key")
    if not mimo_url:
        missing.append("MIMO_URL / mimo_url")
    if not mimo_key:
        missing.append("MIMO_KEY / mimi_key")
    if not model:
        missing.append("MODEL_NAME / model_name")
    if missing:
        print("错误: 缺少以下必需配置，请在 .env 中设置:")
        for item in missing:
            print(f"  - {item}")
        return 1

    payload = build_payload(model, args.prompt, args.max_tokens, args.temperature, args.stream)
    # 清理 None 值
    payload = {k: v for k, v in payload.items() if v is not None}

    print(f"请求模型: {model}")
    print(f"Prompt: {args.prompt!r}")
    print(f"Stream: {args.stream}")
    print(f"Volcengine URL: {volc_url}")
    print(f"Mimo URL: {mimo_url}")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    print("\n开始请求...")

    volc_result = call_api("volcengine", volc_url, volc_key, payload)
    mimo_result = call_api("mimo", mimo_url, mimo_key, payload)

    print_comparison(volc_result, mimo_result)

    out_file = save_results(args.output_dir, volc_result, mimo_result)
    print(f"\n原始记录已保存到: {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
