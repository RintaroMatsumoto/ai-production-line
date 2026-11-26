// @ts-nocheck
// OpenCode plugin example: add a "decision" variant to one model and let a
// System One decision model choose the reasoning effort.
//
// Configure in opencode.json(c):
//
//   "plugins": [{
//     "package": "./samples/opencode-auto-effort",
//     "options": {
//       "deciderURL": "http://127.0.0.1:8001",
//       "providerID": "opencode-go",
//       "modelID": "deepseek-v4.1-flash",
//       "logFile": ""
//     }
//   }]
//
// Default / Low / High / Max selections are never touched.

import { Plugin } from "@opencode/plugin"
import { appendFileSync } from "node:fs"

const DEFAULTS = {
  variant: "decision",
  timeoutMs: 900,
  lowMaxChars: 500,
  // choice -> [effort, minimum confidence, minimum margin]
  policy: {
    trivial: ["low", 0.65, 0.5],
    complex: ["max", 0.6, 0.25],
  },
}

const QUESTIONS = {
  complexity: {
    type: "choice",
    instructions: "この依頼に必要な推論の深さは？",
    criteria: {
      trivial: "挨拶・定型質問・単純な変換・短い事実確認",
      normal: "通常のコーディング・調査・要約・説明",
      complex: "設計・難しいデバッグ・多段の推論・長い計画",
    },
  },
}

function clone(value) {
  try {
    return JSON.parse(JSON.stringify(value))
  } catch {
    return value
  }
}

async function decide(endpoint, state, model, timeoutMs) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const url = endpoint.replace(/\/+$/, "") + "/v1/systemone"
    const response = await fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({ model, state, questions: QUESTIONS }),
    })
    if (!response.ok) return undefined
    const payload = await response.json()
    const answer = payload?.answers?.complexity
    if (!answer) return undefined

    const probabilities = answer.probabilities ?? {}
    const values = Object.values(probabilities)
      .map(Number)
      .sort((a, b) => b - a)
    return {
      choice: String(answer.choice ?? ""),
      confidence: Number(answer.confidence ?? probabilities[answer.choice] ?? 0),
      margin: (values[0] ?? 0) - (values[1] ?? 0),
    }
  } catch {
    return undefined
  } finally {
    clearTimeout(timer)
  }
}

export default Plugin.define({
  id: "auto-effort-example",
  async setup(ctx) {
    const options = ctx.options ?? {}
    const providerID = String(options.providerID ?? "opencode-go")
    const modelID = String(options.modelID ?? "deepseek-v4.1-flash")
    const variant = String(options.variant ?? DEFAULTS.variant)
    const endpoint = String(options.deciderURL ?? "http://127.0.0.1:8001")
    const timeoutMs = Number(options.timeoutMs ?? DEFAULTS.timeoutMs)
    const lowMaxChars = Number(options.lowMaxChars ?? DEFAULTS.lowMaxChars)
    const policy = options.policy ?? DEFAULTS.policy
    const logFile = String(options.logFile ?? "")

    const log = (entry) => {
      if (!logFile) return
      try {
        appendFileSync(logFile, JSON.stringify({ t: new Date().toISOString(), ...entry }) + "\n")
      } catch {}
    }

    // 1) expose the variant in the picker
    await ctx.model.transform((editor) => {
      const model = editor.get(providerID, modelID)
      if (!model || model.variants?.some((item) => item.id === variant)) return
      const fallback =
        model.variants?.find((item) => item.id === "high") ??
        model.variants?.[model.variants.length - 1]
      model.variants.push({
        id: variant,
        settings: clone(fallback?.settings ?? {}),
        headers: fallback?.headers,
      })
    })

    // 2) remember the last user prompt and reuse one decision per turn
    const lastPrompt = new Map()
    const decisions = new Map()

    await ctx.session.hook("prompt", (event) => {
      lastPrompt.set(event.sessionID, String(event.prompt?.text ?? ""))
      decisions.delete(event.sessionID)
    })

    await ctx.session.hook(
      "experimental.model.resolve",
      async (event) => {
        if (event.model?.providerID !== providerID) return
        if (event.model?.id !== modelID) return
        if (event.model?.variant !== variant) return
        if (event.kind !== "primary") return

        const state = lastPrompt.get(event.sessionID)
        if (!state?.trim()) return

        let decision = decisions.get(event.sessionID)
        if (!decision) {
          decision = await decide(endpoint, state.slice(0, 6000), modelID, timeoutMs)
          decisions.set(event.sessionID, decision)
        }

        const rule = decision ? policy[decision.choice] : undefined
        let effort
        if (rule) {
          const [candidate, minConfidence, minMargin] = rule
          if (decision.confidence >= minConfidence && decision.margin >= minMargin) {
            effort = candidate
          }
        }

        // A long request is not a trivial one.
        if (effort === "low" && state.length > lowMaxChars) effort = undefined

        log({
          event: "route",
          choice: decision?.choice ?? null,
          confidence: decision?.confidence ?? null,
          margin: decision?.margin ?? null,
          effort: effort ?? null,
        })

        if (effort) event.model = { ...event.model, variant: effort }
      },
      { providerID },
    )
  },
})
