"""所有 Prompt 集中在此目录管理（版本化，禁止散落在业务代码里）。

每个 system prompt 第一行带 [[task:xxx]] 标记：Mock LLM Provider
据此生成对应结构的离线内容，测试与无密钥开发都依赖它。
"""
