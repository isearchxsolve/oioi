# Single-node laptop fallback

Set `OIOI_SINGLE_NODE_MODE=true` while OiiOii runs on one laptop. This does not
change the film pipeline's durable database artifacts, compression, storage quota,
provider contract, or quality gate. It only makes execution deliberately narrow:

- one in-process film scheduler tick at a time;
- one provider submission at a time;
- one local materialization at a time;
- one local fallback/FFmpeg operation at a time.

Run exactly one Uvicorn worker in this profile. A concurrent `/tick` call receives
HTTP 409 and can retry safely because the job graph is durable. Disable the setting
when moving to a properly sized multi-worker host.

For EmergentSH, set `EMERGENT_SINGLE_NODE_MODE=true`; it forces the durable worker
loop to execute one app-generation job at a time without changing its authentication,
archive, or consumer-provider contracts.
