# 学科词性校订库

学科词性校订库用于处理本地合成教研文本，保存来源版本、文本片段和处理记录，供校内复核使用。

## 环境

需要 Python 3.11 或更新版本，不依赖外部服务或第三方包。

## 运行

执行 `PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli ingest fixtures/records.json` 导入演练记录，再执行 `PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli list` 查看当前文本处理结果。运行数据保存在 `var/records.json`。

## 测试

执行 `PYTHONPATH=src python -m unittest discover -s tests -v` 检查文本规范化、记录处理、状态读取及本地持久化。
