from __future__ import annotations

import os
from typing import Any, Dict

import yaml


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    递归深度合并两个字典。
    将 override 字典中的键值对深度合并到 base 字典中。
    如果 base 和 override 中的值都是字典，则递归合并它们；否则，用 override 的值覆盖 base 的值。
    """
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            # 如果值为字典且存在于 base 中，递归合并
            result[key] = _deep_merge_dict(result[key], value)
        else:
            # 否则直接覆盖或新增键值对
            result[key] = value
    return result


def _set_nested(config: Dict[str, Any], path: str, value: Any) -> None:
    """
    根据双下划线分割的路径，在嵌套字典中设置对应的值。
    例如将 path="fetch__query__categories", value=["cs.AI"] 
    转换为 config["fetch"]["query"]["categories"] = ["cs.AI"]。
    """
    parts = [p for p in path.split("__") if p]
    cur: Dict[str, Any] = config
    for part in parts[:-1]:
        nxt = cur.get(part)
        # 如果当前路径部分不存在或者不是字典，则初始化为空字典
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if parts:
        # 在最深层级设置具体的值
        cur[parts[-1]] = value


def _parse_env_value(raw: str) -> Any:
    """
    将环境变量收集到的字符串值解析为具体的 Python 类型。
    支持的类型推断包括：布尔值 (true/false)、整数、浮点数以及通过 YAML 语法解析的列表或字典。
    """
    v = raw.strip()
    lower = v.lower()
    
    # 1. 尝试解析布尔值
    if lower in {"true", "false"}:
        return lower == "true"

    # 2. 尝试解析整数
    try:
        # 防止将类似于 "0755" 这种可能含有特殊意义的字符串强制解析为普通十进制整数
        if lower.startswith("0") and len(lower) > 1 and lower[1].isdigit():
            raise ValueError
        return int(v)
    except ValueError:
        pass

    # 3. 尝试解析浮点数
    try:
        return float(v)
    except ValueError:
        pass

    # 4. 尝试解析数组或字典（JSON / YAML 内联格式）
    if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
        try:
            loaded = yaml.safe_load(v)
            return loaded
        except Exception:
            return v

    # 如果无法转换为任何复杂类型，则保持原来的字符串格式返回
    return v


def load_config(base_dir: str) -> Dict[str, Any]:
    """
    加载项目全局配置。
    优先读取 base_dir 目录下的 config.yaml 文件，随后通过环境变量进行覆盖。

    Env override (环境变量覆盖) 格式:
      - 前缀: ARXIV_AGENT__
      - 嵌套键名使用双下划线分开 (__)
    示例:
      ARXIV_AGENT__fetch__arxiv_api__max_results=200
      ARXIV_AGENT__fetch__query__categories=["cs.AI","cs.CL"]
    """

    config_path = os.path.join(base_dir, "config.yaml")

    # 1. 读取基础的 YAML 配置文件
    file_config: Dict[str, Any] = {}
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                file_config = loaded

    # 2. 从环境变量中读取具有特定前缀配置项并处理
    env_override: Dict[str, Any] = {}
    prefix = "ARXIV_AGENT__"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        # 将前缀剔除并使用双下划线分割路径
        path = key[len(prefix) :]
        # 把路径全部转化为小写以符合 yaml 文件中全小写的惯例
        path = "__".join([p.lower() for p in path.split("__") if p])
        # 根据路径构建多级字典结构并填入解析后的值
        _set_nested(env_override, path, _parse_env_value(value))

    # 3. 将环境变量的配置作为 override 深层合并到由文件加载的配置上
    return _deep_merge_dict(file_config, env_override)


def get_config_value(config: Dict[str, Any], dotted_path: str, default: Any = None) -> Any:
    """
    通过点分路径（例如 "fetch.query.keywords"）安全地从配置字典中查询并获取值。
    如果路径中任何一个层级不存在或不为字典类型，则返回默认值 fallback (default)。
    """
    cur: Any = config
    for part in dotted_path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
