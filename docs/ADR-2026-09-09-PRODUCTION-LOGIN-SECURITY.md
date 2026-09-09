# ADR：正式登录防护、代理信任与 MFA 边界

日期：2026-09-09  
状态：M14 当前决策；应用内限流、可信来源适配、分布式服务适配、会话轮换与摘要密钥轮换已实现，外部服务部署和 MFA 尚未实现。

## 背景

M14 已有正式账号凭据与不透明会话，但仅验证密码并不足以开放真实商业登录。登录滥用防护、网络来源信任、最小安全事实、会话轮换和 MFA 必须分别定义，不能依赖浏览器字段、模型判断或部署人员的隐含约定。

## 决策

1. `AccountLoginProtection` 是独立于 `AccountIdentity` 的深模块 Interface。身份模块只判断凭据；防护模块在验证前做限流，并在验证后只记录 `succeeded`、`failed` 或 `throttled`。
2. 防护存储只保存带独立密钥的 principal/network HMAC、枚举结果和服务端时间。不得保存邮箱、原始 IP、密码、Cookie、session token、请求正文、User-Agent 或业务内容。默认保留 168 小时，过期安全事件在下一次评估时删除。
3. 应用层同时限制单一账号线索和单一网络来源。阈值与窗口由受控部署配置提供，默认分别为 5 次、30 次和 15 分钟。返回统一 `LOGIN_RATE_LIMITED`，不得说明命中了账号还是网络规则。
4. 本地 `direct` 只使用 ASGI 连接的 `request.client.host` 并忽略转发头；生产 `trusted_proxy` 只接受显式 CIDR 白名单 peer，并要求边缘把 `X-Forwarded-For` 覆盖为单一规范 IP。生产同时要求 `distributed_http` 适配器；完整协议与失败关闭规则见 [`ADR-2026-09-09-TRUSTED-LOGIN-EDGE.md`](ADR-2026-09-09-TRUSTED-LOGIN-EDGE.md)。
5. 成功登录签发新 token 后，服务端撤销同一浏览器已有的正式会话 token。防护事件写入失败时，新 token 立即撤销且登录 fail closed。密码重置和账号停用仍撤销该账号全部会话。
6. 正式身份启用时必须另配至少 32 字符的登录防护密钥；不得复用模型 API Key、Agent M2M token、Beta 摘要密钥或会话 token。缺失时登录和 `/ready` 均明确不可用。

## MFA 决策

- 当前过渡 adapter 不提供 MFA，也不允许因此开启公共注册、找回密码或商业发布；正式身份开关继续默认关闭。
- 面向个人教师的真实商业登录前，必须实现 WebAuthn/passkey 优先的第二因素、一次性恢复码和最近重新认证；修改凭据、恢复账号等敏感动作必须 step-up。
- 未来任何组织 owner、管理员或支持代操作角色必须强制 MFA，且 Agent、客服或后台任务不能绕过。
- TOTP 只可作为兼容回退；短信不得成为特权角色的唯一第二因素。恢复码必须只存不可逆摘要、单次使用并产生安全审计事实。

## 明确未解决

- 当前 SQLite 只证明 Interface、限流语义和隐私字段；HTTP adapter 已固定摘要化协议，但外部分布式原子服务、边缘抗压、设备管理、地理异常判断和生产告警仍需部署。
- 登录安全事实不是完整账号审计。密钥版本与轮换见 [`ADR-2026-09-09-HMAC-KEY-ROTATION.md`](ADR-2026-09-09-HMAC-KEY-ROTATION.md)；审计导出/访问控制和不可抵赖存储仍需后续切片。
- 尚未实现 MFA 注册、验证、恢复或 step-up API；任何 UI 占位都不能宣称已经支持 MFA。
