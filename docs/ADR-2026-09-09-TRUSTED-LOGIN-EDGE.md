# ADR：可信登录来源与分布式限流服务边界

日期：2026-09-09  
状态：M14 当前决策；应用适配器已实现，外部分布式服务与边缘配置仍需部署方提供。

## 背景

单进程 SQLite 可以验证登录限流语义，但多副本生产环境必须共享原子计数。反向代理后的应用也不能直接相信浏览器可伪造的 `X-Forwarded-For`。来源解析、账号验证和限流存储必须是三个独立边界。

## 决策

1. `LoginNetworkOrigin` 只从 ASGI 的直接连接 peer 与一个受控转发头解析登录来源。浏览器、请求正文、Agent 和模型都不能选择来源。
2. 本地开发使用 `direct`：只读直接 peer，忽略所有转发头。`environment=production` 时 `direct` 明确不可用。
3. 生产使用 `trusted_proxy`：直接 peer 必须属于显式 CIDR 白名单；边缘必须**覆盖** `X-Forwarded-For` 为一个规范 IP。缺头、多值链、非法 IP、非白名单 peer 或空白名单全部失败关闭。这里不猜测链中“第几个”地址可信。
4. `HttpDistributedAccountLoginProtection` 是外部分布式原子限流服务的同步适配器。邮箱和规范网络来源在 FastAPI 进程内完成版本化 HMAC；外部服务只接收当前/旧摘要候选、非敏感 key tag、窗口/阈值/保留策略和枚举结果。
5. 外部服务固定使用 `m14.login-protection.v1` 契约：`POST /v1/assess` 返回 `allow` 或有界 `throttle`，`POST /v1/record` 确认写入，`GET /ready` 报告契约就绪。错误状态、重定向、超大/非 JSON/错误版本响应或网络异常都失败关闭。
6. 适配器使用独立至少 32 字符的 bearer token，不继承工作站代理、不跟随重定向。生产 URL 必须为 HTTPS；只有非生产环境允许 HTTP loopback。
7. 实际生产部署必须显式设置 `MATH_AI_ENVIRONMENT=production`，并同时选择 `trusted_proxy` 与 `distributed_http`。SQLite 与 direct 仍保留为本地/测试 adapter，但不能形成生产就绪状态。

## 外部服务必须保证

- 多实例之间对账号摘要与网络摘要做原子判断和写入；不能先查后写造成竞态。
- 按 API 提供的窗口、阈值与保留期执行，并跨当前/旧摘要候选计数。
- 持续核对 `accepted_key_tags`；保留期内出现未识别版本摘要时拒绝服务，不能借换钥清零限流。
- 只保存契约字段，不记录邮箱、IP、Authorization、请求正文日志或其他可识别信息。
- 部署独立访问控制、TLS、可用性监控和容量告警；`/ready` 不返回计数、摘要、token、地址或内部错误。

## 明确未完成

- 仓库未捆绑 Redis/云限流服务，也没有伪造一个单进程实现来声称“已分布式”。部署方仍需实现或选定满足上述契约的服务。
- 边缘 WAF、DDoS 防护、告警、MFA、设备风险判断和不可抵赖安全审计仍是独立后续工作。
- 本切片不改变账号、tenant、owner、内容权利或产品工作流。
