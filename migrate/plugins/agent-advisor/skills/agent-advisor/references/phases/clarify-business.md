# Clarify wording — Business audience

Translate scoring signals into business language. Map answers onto the SAME keys in
clarify.md Step 3 (do not invent new keys/values).

- **session_duration**: "Does your agent answer in a few seconds, work for a few minutes,
  work for hours, or run continuously?" → under_15min / 15min_to_8hr (minutes or hours) /
  over_8hr.
- **traffic_pattern**: "Is usage spiky with quiet gaps, or steady all day?" → bursty / steady / idle.
- **session_state**: "Does a person approve the agent's actions, or does it run on its own?"
  → hitl (approves) / stateful / stateless.
- **isolation**: "Do your different customers' data need to be strictly separated?" →
  required / nice_to_have / not_needed.
- **memory_needs**: "Should the agent remember a user across separate conversations?" →
  cross_session / session_only / none.
- **ops_preference**: "How hands-on do you want to be with infrastructure? just push code /
  some control / full control." → minimal / moderate / full_control.
- **compute_tier**: "Does a task do heavy number-crunching (video, large data, ML), or mostly
  call an AI model and wait?" → heavy_non_gpu / light; ask about GPU only if heavy.
- **idle_resume**: "If a user steps away and comes back, must the work continue exactly where
  it paused?" → process_level / filesystem / none.
- **launch_concurrency**: "At peak, roughly how many new sessions start per second?" → high
  (many) / moderate / low.
- **multi_agent**: "One agent, or several working together?" → no / yes.
- **framework / existing_cluster / multi_cloud / platform_fit**: ask in plain terms; default
  to unknown if the user is unsure (the engine handles unknown safely).
- **compliance**: "Any compliance requirements? (HIPAA, SOC 2, etc.)" multi-select.
- **model_priority**: "What matters most for the AI — quality, speed, cost, or balanced?"
- **model_features**: only ask whether they need "extended thinking / deep reasoning" (other
  feature values don't change the recommendation). **current_model**: migrate only ("what model
  are you on today?"). Do NOT ask about region (not scored here).
