# Bedrock Model Defaults (forward selection only)

This plugin does NOT reproduce source-model pricing/TCO tables. Detailed pricing and
source→target migration mapping live in the **migration-to-aws** plugin (canonical source).

## Forward default (requirement → model)
| Priority | Model |
| --- | --- |
| Quality / Balanced / unknown | Claude Sonnet 4.6 |
| Speed / Cost | Claude Haiku 4.5 |
| Extended thinking (feature override) | Claude Sonnet 4.6 with extended thinking |

Used only to fill the cost estimate and the scaffold's `modelId`.

## Migrate path
Give a coarse family-level mapping only (e.g. "GPT-4o → Claude Sonnet 4.6 family").
For dollar figures and TCO, direct the user to migration-to-aws. Never put prices here.
