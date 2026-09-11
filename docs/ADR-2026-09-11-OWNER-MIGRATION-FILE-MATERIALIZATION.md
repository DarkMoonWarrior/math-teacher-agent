# ADR：owner 迁移文件流式物化

日期：2026-09-11
状态：已采纳，M14 PostgreSQL tenant adapter 的内部存储切片

## 决策

新增内部 `OwnerMigrationSourceFiles` Module，统一负责从固定数据库目录解析当前
source owner 的文件引用、解析受控路径并以流式 SHA-256 和字节长度检查内容。
Planner 和 `OwnerMigrationFileMaterializer` 通过同一 Interface 使用它，不再各自维护
文件名、试卷 asset 或 owner 关系规则。

文件物化器先验证完整计划、目标 owner/tenant 绑定、文件域集合、对象集合及计划内
内容指纹，再返回不暴露路径和引用名的 `OwnerMigrationFileBatch`。每个文件的
`copy_to` 在真正读取时再次拒绝链接并重新核对 SHA-256 与长度，防止计划、物化与
目标暂存之间替换内容。

## Interface 不变量

- source owner、target owner 和 tenant 必须与不可变计划一致，错误目标在读取源文件
  之前拒绝。
- 只解析固定四类文件目录及其数据库引用；调用方不能提交路径、文件名、owner 或
  任意查询。
- 每次检查与复制都使用有界块流，不把整份 PDF 或图片加载进内存。
- 目标 adapter 只能把流写入其事务拥有、失败可丢弃的 staging sink；只有
  `copy_to` 成功返回后，目标才可记录该文件已暂存。短写、链接、I/O 错误或 EOF
  指纹不符均不得发布。
- 批次和文件对象关闭私密字段的 `repr`；报告、异常和回执不出现 owner、tenant、
  路径、文件名或正文。

## 当前限制

本切片本身没有复制或发布真实文件，没有连接真实 PostgreSQL，也没有 HTTP、浏览器、
Agent、模型或 CLI 入口。自动测试只使用临时 SQLite、临时文件和内存 staging sink。
后续具体 PostgreSQL 目标事务 adapter 已复用该 Interface，并通过合成 staging 证明
“暂存、对账、可逆发布、数据库提交”的普通失败回滚；生产 staging 和跨系统崩溃补偿
仍未实现。
