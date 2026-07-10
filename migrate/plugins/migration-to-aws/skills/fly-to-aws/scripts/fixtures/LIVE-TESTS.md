# fly-to-aws live-test matrix (run with the skill installed, one session each)

For each fixture: point the skill at the fixture dir, answer Clarify per the
"answers" column, then diff `$MIGRATION_DIR/aws-design.json` against "expected".

| Fixture                            | Clarify answers                                 | Expected aws-design.json assertions                                                                           |
| ---------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| scale-to-zero-default              | s2z=deliberate, function-model=no, stateful=yes | web → lambda_microvms, layer_fired=5                                                                          |
| scale-to-zero-default              | s2z=inherited default                           | web → fargate_ecs_express, layer_fired=4, idle-cost note present                                              |
| multi-group                        | worker=always-on requirement; nightly=job yes   | worker → fargate_ecs_express layer 4; nightly → batch/ecs_scheduled_task layer 2 (NOT layer 5)                |
| multi-group + eks_reuse=yes        | same                                            | worker → eks (layer 3 flavor), nightly STILL batch (layer 2 beat layer 3)                                     |
| stateful-legacy-pg                 | defaults                                        | databases[] has managed:false entry; volume → de-volume or EFS decision recorded; NO process group for pg app |
| agent-langgraph                    | confirm agent=yes, accept handoff               | agent group → decided_by=agent-advisor, layer_fired=0, embed dir under $MIGRATION_DIR/agent-advisor/agent/    |
| agent-langgraph                    | confirm agent=yes, DECLINE handoff              | agent group routed by layers 1–5 with declined note                                                           |
| agent-langgraph (advisor-injected) | pre-write preferences.agent_groups.agent        | layer G: no class questions asked for that group, verdict preserved                                           |
