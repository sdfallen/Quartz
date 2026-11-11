# Codex — chat lifecycle integration contract

2026-11-02; based on shared `2c57a49`. This document is a current integration request for the parallel Claude and Antigravity tasks. No package acceptance is implied.

## Backend additions owned by Codex

- Host `task_id` correlates the existing chat `turn_id`; provider `run_id`, provider session/thread ID and Squad task ID remain distinct.
- `send_message` during a running managed turn queues a followup for the same conversation/provider under frozen original execution flags. Return includes the existing user/assistant messages plus `queued:true`, `task_id`, `queue_position`. It creates no second worker. Max 16 pending instructions is an admission bound, not an execution timeout.
- A conversation-only turn cannot be escalated into a development task through the queue. New project/provider/greater authority is rejected; normal broker scope grants still apply.
- Queued instructions are excluded from previous-step prompt history. The existing step finishes before the next starts; each queued instruction runs once. Failure or Stop discards remaining work. Restart marks abandoned queue records interrupted; it does not replay them or restore grants.
- `poll_active` adds `task_id`, `queued_instructions`, `stop_receipt`. On a read-model failure it preserves task/Stop state rather than returning a false idle result.
- `cancel_active` fences output and queued work immediately. Legacy local `status:cancelled` is retained, while `stop_receipt.status:pending|confirmed|failed` reports cleanup independently. `stop_receipt.runs[run_id].process_exit_confirmed` must be true, the owning worker must have finished and `writer_pending` / `unresolved_dispatch` must be empty before confirmed. A conversation persistence failure cannot skip process cancellation: it is exposed as `history_error_type`; after actual processes stop the receipt remains failed until an explicit Stop/close retry can persist the cancellation. Exceptions expose type only, not arbitrary provider/path strings. Terminal status alone is not exit proof.
- A dispatch returning after Stop is still registered/cancelled by real run ID. New task admission remains blocked while its cleanup is unconfirmed.
- Failed/completed local status cannot replace the previous turn while `worker_pending` is still true. All registered provider runs are checked at finalization, including an unfinished provider hidden behind partial group success.
- `WriterDispatchError` preserves a known run ID if post-start journal/dispatch work fails. Unknown post-start ownership is recorded in `unresolved_dispatch`; an empty run list is not reported clean. Failed-start claims remain locked/recovery-required. The existing restart + explicit external recovery review is required for an uncertain start; this code never deletes that claim or starts an automatic retry.
- `AgentChatService.close()` closes admission first, cancels if necessary, closes status publication and returns `{status, components:{chat:stop_receipt}}`. It is retryable; it does not shut down the shared provider service or kill the process. `MultiAgentService.shutdown()` remains the provider owner's operation.

## Claude integration request

Read only `ui/js_chat.py` currently has `if (thinking) return;` after coordination routing. This can prevent a live followup reaching the chat service even though the backend accepts it. Adapt your owned frontend/Api boundary to send same-task followups and render queued messages/status without clearing the active worker's thinking/Stop state. Keep the coordination/natural-desktop routing priority and existing grant checks; do not bypass them by sending every message directly to chat.

When local cancellation is shown, keep cleanup-pending visible while `stop_receipt.status` is pending. Do not show all processes stopped or enable a new executor solely because `active:false` or local status cancelled arrived. Existing Stop button must remain immediate and enabled for current jobs. A rejected followup must retain editable text and leave the current task running. Please test queued response rendering, send while running, Stop pending, and no second dispatch. Public bridge names/arguments can remain unchanged.

Receipt `failed` is also non-ready; it can mean the processes stopped but durable cancellation recording failed. Show a concise error/retry state rather than claiming the agent is still running. `worker_pending`, `writer_pending`, `unresolved_dispatch`, `process_exit_confirmed` and the safe error-type fields explain the actual reason. The read-only acknowledgement flag is not an input grant or permission escalation.

## Antigravity integration request

Treat `AgentChatService.close()`'s receipt independently from the provider service's shutdown. Calling close once can return pending while dispatch is still returning or the worker is unwinding. Run other cleanup owners despite that result, then read/retry the chat receipt after provider shutdown rather than treating a non-throwing close as confirmed. Do not replace the chat close/admission implementation in your branch. No GUI edits required in your scope.

Diagnostics snapshot.close fences late publication; it intentionally does not block on an external read-only probe. Process/supervisor ownership for that probe remains a distinct runtime concern. No global registry or duplicate task engine is introduced by the chat changes.

## Store ownership

ConversationStore read/append results and nested metadata now return independent copies. Poll-side host evidence enrichment must remain a detached view; do not mutate it expecting an implicit save. Persist through the existing store methods. A new regression reproduced the old shared-message-list mutation and proves that passive display evidence does not enter authoritative history.

## Verification scope so far

New tests use actual temporary ConversationStore files and events/mock providers; they exercise queue FIFO, frozen authority, failure discard, Stop publication fence, unconfirmed process exit, cancellation error, late dispatch, worker start failure, restart non-replay and generation ownership. These are source/offline tests, not live model/GUI acceptance. Existing lifecycle and permission tests are run alongside them. Final source/CLI/package acceptance follows after the two parallel deliveries merge.
