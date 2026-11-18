# 学科词性校订库

学科词性校订库用于处理本地合成教研文本，保存来源版本、文本片段和处理记录，供校内复核使用。同一个字词在古文与现代说明文中可能承担不同词性，词典版本、上下文标注、人工决定与句法查询共用同一套口径。

## 口径约定

- **语境**：文本记录的 `context`（如“古文”“现代说明文”）经统一规范化后，同时用于词典义项的适用范围、人工校订的生效范围和句法查询的筛选条件。
- **词典版本**：词典按版本发布，版本不可变；撤回词项或义项即发布一个去掉对应内容的新版本，旧版本保留。词典更新只影响之后产生的标注，旧语料仍按原词性检索。
- **解析顺序**：人工校订 > 校本义项 > 通用义项；语境特定义项优先于通配义项。仍有多个候选词性时标记为 `ambiguous`，不擅自定夺，留待教师校订。
- **标注快照**：每次标注生成不可变快照，记录所用词典版本；每个词性判断都带来源（词典自动 / 人工校订编号），可按词典版本复现旧查询。
- **过期**：词典条目撤回或解析结果变化、人工校订被撤销或取代后，依赖它的判断标记为 `stale`，默认不参与检索，也不会再被当成已确认标注。

## 环境

需要 Python 3.11 或更新版本。应用运行不依赖第三方包；运行测试和构建前，安装固定版本的开发工具：`python -m pip install -r requirements-dev.txt`。

## 运行

以下命令均可加 `--state` 指定运行数据文件（默认 `var/records.json`），为简洁起见省略：

```bash
# 发布词典版本（只影响之后标注的文本）
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli publish-dict fixtures/dictionary.json --note 初版
# 导入文本记录并按最新词典标注
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli ingest fixtures/records_genre.json
# 查看各记录的标注状态汇总
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli list
# 教师校订：之 在古文中定为助词，随后只重处理含“之”的记录
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli override 之 助词 --context 古文 --teacher 王老师
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli reprocess --term 之
# 句法检索：默认排除过期标注；可按词典版本复现旧查询
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli query --pos 助词
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli query --pos 副词 --dictionary-version 1 --include-stale
# 撤回校本义项，依赖它的自动标注显露过期，再选择性重处理
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli retract 其 --pos 副词
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli reprocess --stale-only
# 溯源：查看词性判断来自哪版词典、哪个义项、哪条人工校订
PYTHONPATH=src python -m nlp_teacher_glossary_pos.cli explain lesson-classical-1 --token 之
```

其他命令：`show-dict [--version N]` 查看词典版本与词条；`revoke-override ID` 撤销人工校订；`list-overrides` 查看校订记录；`reprocess` 支持 `--record-id/--source/--context/--term/--stale-only/--all` 组合选择范围，并可用 `--dictionary-version` 指定版本（含旧版本，用于复现或回退）。

## 测试

执行 `python -m pytest -q` 检查文本规范化、记录处理、词典版本与撤回、人工校订的语境绑定、选择性重处理、过期判定、旧查询复现及本地持久化。
