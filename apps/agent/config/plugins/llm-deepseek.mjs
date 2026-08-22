import {
  apply,
  Config,
  inject,
  name,
} from "@deepseek-ai/dsh-llm-deepseek";

// Cordis loader unwraps the default export before registration. Keep the
// official plugin metadata on that default object so ctx.llm is injected.
export default { apply, Config, inject, name };
